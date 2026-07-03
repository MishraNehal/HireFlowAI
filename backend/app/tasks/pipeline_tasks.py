"""
Pipeline Tasks — Celery tasks that run the LangGraph pipeline asynchronously.

Why Celery?
  - FastAPI request returns campaign_id immediately (non-blocking)
  - Pipeline runs in background (can take minutes to hours)
  - Celery handles retries on transient failures
  - NodeInterrupt (checkpoint pause) is handled gracefully — not a failure

Task flow:
  POST /campaigns → save to DB → queue run_pipeline task → return campaign_id
  run_pipeline → build graph → invoke → NodeInterrupt (checkpoint) → task ends
  HR approves → queue resume_pipeline task → graph resumes from checkpoint
  → NodeInterrupt again (next checkpoint) → task ends
  ... repeat until pipeline completes or fails
"""

import logging
from datetime import datetime

from celery import Task
from langgraph.errors import NodeInterrupt

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.services.websocket import ws_manager
from app.graph.builder import build_graph
from app.graph.rollback import RollbackService
from app.models.campaign import Campaign, CampaignStatus, Checkpoint, CheckpointStatus

logger = logging.getLogger(__name__)


def _save_checkpoint_from_graph_state(db, graph, config, campaign_id, company_id):
    """
    Called right after a NodeInterrupt is caught.

    LangGraph has already paused BEFORE the checkpoint node executes
    (interrupt_before=[...]), so graph.get_state() gives us the state
    as it stood after the LAST completed agent node — which is exactly
    what we need to snapshot.

    Determines which checkpoint stage we're paused at from the graph's
    'next' node (the checkpoint node about to run), creates a Checkpoint
    row with status=pending, and fires the checkpoint.pending WS event.
    """
    from app.graph.checkpoint_manager import _stage_order, _serialise_state

    snapshot = graph.get_state(config)
    next_nodes = snapshot.next  # tuple of node names about to execute
    if not next_nodes:
        logger.warning(f"[Pipeline] No next node found in graph state for {campaign_id}")
        return None

    stage_name = next_nodes[0]  # the checkpoint node we're paused before
    state_values = dict(snapshot.values)
    state_dict = _serialise_state(state_values)

    checkpoint = Checkpoint(
        campaign_id=campaign_id,
        stage_name=stage_name,
        stage_order=_stage_order(stage_name),
        status=CheckpointStatus.pending,
        state_snapshot=state_dict,
    )
    db.add(checkpoint)
    db.commit()
    db.refresh(checkpoint)

    logger.info(
        f"[Pipeline] Checkpoint saved — campaign={campaign_id}, "
        f"stage={stage_name}, checkpoint_id={checkpoint.id}"
    )

    _send_ws_event(
        company_id=company_id,
        campaign_id=campaign_id,
        event="checkpoint.pending",
        payload={
            "checkpoint_id": str(checkpoint.id),
            "stage_name": stage_name,
            "stage_order": checkpoint.stage_order,
            "campaign_id": campaign_id,
        },
    )
    return checkpoint


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 — Start pipeline from scratch
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="tasks.run_pipeline",
)
def run_pipeline(self, campaign_id: str, company_id: str):
    """
    Start the LangGraph pipeline for a newly created campaign.

    Called immediately after POST /campaigns.
    Runs until first NodeInterrupt (checkpoint) or completion.
    """
    logger.info(f"[Pipeline] Starting — campaign={campaign_id}")
    db = SessionLocal()

    try:
        # Load campaign from DB
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            logger.error(f"[Pipeline] Campaign {campaign_id} not found")
            return {"status": "error", "reason": "campaign_not_found"}

        # Update campaign status to running
        campaign.status = CampaignStatus.active
        db.commit()

        # Send WebSocket event — pipeline started
        _send_ws_event(
            company_id=company_id,
            campaign_id=campaign_id,
            event="pipeline.started",
            payload={
                "campaign_id": campaign_id,
                "message": "Pipeline started — Hiring Intelligence Agent running",
            },
        )

        # Build graph from campaign workflow config
        workflow_config = campaign.workflow_config or {}
        graph = build_graph(workflow_config)

        # Build initial state
        initial_state = {
            "company_id": company_id,
            "campaign_id": campaign_id,
            "workflow_config": {
                **workflow_config,
                "role": campaign.role,
                "openings": campaign.openings,
                "skills_required": campaign.skills_required or [],
                "stipend": campaign.stipend,
                "location": campaign.location,
                "work_mode": campaign.work_mode,
                "batch_year": campaign.batch_year,
            },
            "hiring_strategy": {},
            "job_description": {},
            "selected_colleges": [],
            "candidates": [],
            "shortlisted": [],
            "assessment_results": [],
            "interview_sessions": [],
            "final_selected": [],
            "offers": [],
            "current_stage": "hiring_intelligence",
            "checkpoint_status": "",
            "hr_feedback": None,
            "rollback_to": None,
            "error": None,
        }

        # LangGraph thread config — thread_id = campaign_id for persistence
        config = {"configurable": {"thread_id": campaign_id}}

        logger.info(f"[Pipeline] Invoking graph — campaign={campaign_id}")

        try:
            graph.invoke(initial_state, config=config)

            # LangGraph's interrupt_before does NOT always raise NodeInterrupt as
            # an exception — with a checkpointer, invoke() returns normally and
            # pauses internally. We must check graph state to know if we're
            # paused at a checkpoint or actually finished.
            snapshot = graph.get_state(config)
            if snapshot.next:
                # Paused at a checkpoint node
                logger.info(f"[Pipeline] Paused at checkpoint — next={snapshot.next}")
                _save_checkpoint_from_graph_state(db, graph, config, campaign_id, company_id)
            else:
                # Graph fully completed — no more nodes to run
                _on_pipeline_complete(db, campaign, company_id, campaign_id)

        except NodeInterrupt as ni:
            # Some LangGraph versions DO raise this — handle both cases
            logger.info(f"[Pipeline] Paused at checkpoint (exception) — {ni}")
            _save_checkpoint_from_graph_state(db, graph, config, campaign_id, company_id)

        return {"status": "ok", "campaign_id": campaign_id}

    except Exception as e:
        logger.error(f"[Pipeline] Unexpected error — campaign={campaign_id}: {e}", exc_info=True)

        # Notify HR of error via WebSocket
        _send_ws_event(
            company_id=company_id,
            campaign_id=campaign_id,
            event="pipeline.error",
            payload={
                "campaign_id": campaign_id,
                "error": str(e),
                "message": "Pipeline encountered an error. Team has been notified.",
            },
        )

        # Update campaign status
        try:
            campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
            if campaign:
                campaign.status = CampaignStatus.paused
                db.commit()
        except Exception:
            pass

        # Retry on transient errors
        raise self.retry(exc=e, countdown=30)

    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 — Resume pipeline after HR approval
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="tasks.resume_pipeline",
)
def resume_pipeline(
    self,
    campaign_id: str,
    company_id: str,
    checkpoint_id: str,
    decision: str,      # "approved" | "rejected" | "revision_requested"
    hr_notes: str = "",
    decided_by: str = None,
):
    """
    Resume the LangGraph pipeline after an HR checkpoint decision.

    Called from POST /checkpoints/{id}/respond.

    - approved           → resume graph from next node
    - rejected           → rollback to previous approved checkpoint, re-run agent
    - revision_requested → re-run current agent with hr_feedback
    """
    logger.info(
        f"[Pipeline:Resume] campaign={campaign_id}, decision={decision}, "
        f"checkpoint={checkpoint_id}"
    )
    db = SessionLocal()

    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            logger.error(f"[Pipeline:Resume] Campaign {campaign_id} not found")
            return {"status": "error", "reason": "campaign_not_found"}

        workflow_config = campaign.workflow_config or {}
        graph = build_graph(workflow_config)
        config = {"configurable": {"thread_id": campaign_id}}

        if decision == "approved":
            result = _handle_approved(
                db=db,
                graph=graph,
                config=config,
                checkpoint_id=checkpoint_id,
                company_id=company_id,
                campaign_id=campaign_id,
                hr_notes=hr_notes,
                decided_by=decided_by,
            )

        elif decision == "rejected":
            result = _handle_rejected(
                db=db,
                graph=graph,
                config=config,
                checkpoint_id=checkpoint_id,
                company_id=company_id,
                campaign_id=campaign_id,
                hr_notes=hr_notes,
                decided_by=decided_by,
            )

        elif decision == "revision_requested":
            result = _handle_revision(
                db=db,
                graph=graph,
                config=config,
                checkpoint_id=checkpoint_id,
                company_id=company_id,
                campaign_id=campaign_id,
                hr_notes=hr_notes,
                decided_by=decided_by,
            )
        else:
            return {"status": "error", "reason": f"Unknown decision: {decision}"}

        return result

    except Exception as e:
        logger.error(
            f"[Pipeline:Resume] Error — campaign={campaign_id}: {e}", exc_info=True
        )
        _send_ws_event(
            company_id=company_id,
            campaign_id=campaign_id,
            event="pipeline.error",
            payload={"campaign_id": campaign_id, "error": str(e)},
        )
        raise self.retry(exc=e, countdown=30)

    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Decision handlers
# ─────────────────────────────────────────────────────────────────────────────

def _handle_approved(db, graph, config, checkpoint_id, company_id, campaign_id, hr_notes, decided_by):
    """Mark checkpoint approved and resume graph."""
    cp = db.query(Checkpoint).filter(Checkpoint.id == checkpoint_id).first()
    if not cp:
        return {"status": "error", "reason": "checkpoint_not_found"}

    cp.status = CheckpointStatus.approved
    cp.hr_notes = hr_notes
    cp.decided_by = decided_by
    cp.decided_at = datetime.utcnow()
    db.commit()

    _send_ws_event(
        company_id=company_id,
        campaign_id=campaign_id,
        event="checkpoint.approved",
        payload={
            "checkpoint_id": checkpoint_id,
            "stage_name": cp.stage_name,
            "message": f"{cp.stage_name} approved — pipeline resuming",
        },
    )

    # Resume graph — LangGraph continues from where it paused.
    # Standard interrupt-resume pattern: merge the HR decision into the
    # checkpointed state via update_state(), then invoke(None) to continue
    # from exactly where the graph paused.
    try:
        graph.update_state(
            config,
            {"checkpoint_status": "approved", "hr_feedback": hr_notes or None},
            # No as_node here — the graph is paused BEFORE checkpoint_jd has
            # run (interrupt_before), so invoke(None) must actually execute
            # checkpoint_jd itself, which then routes via its conditional
            # edge (_orchestrator_router). Passing as_node here tricks
            # LangGraph into thinking checkpoint_jd already ran, which skips
            # it entirely and returns an empty `next` (no edges resolved).
        )

        # Verify routing decision before invoking
        pre_invoke_snapshot = graph.get_state(config)
        logger.info(
            f"[Pipeline:Approved] State before resume — "
            f"next={pre_invoke_snapshot.next}, "
            f"checkpoint_status={pre_invoke_snapshot.values.get('checkpoint_status')}"
        )

        graph.invoke(None, config=config)

        snapshot = graph.get_state(config)
        if snapshot.next:
            logger.info(f"[Pipeline:Approved] Paused at next checkpoint — next={snapshot.next}")
            _save_checkpoint_from_graph_state(db, graph, config, campaign_id, company_id)
        else:
            _on_pipeline_complete_by_id(db, campaign_id, company_id)

    except NodeInterrupt as ni:
        logger.info(f"[Pipeline:Approved] Paused at next checkpoint (exception) — {ni}")
        _save_checkpoint_from_graph_state(db, graph, config, campaign_id, company_id)

    return {"status": "ok", "decision": "approved", "campaign_id": campaign_id}


def _handle_rejected(db, graph, config, checkpoint_id, company_id, campaign_id, hr_notes, decided_by):
    """Execute rollback and re-run agent from previous approved checkpoint."""
    rollback_svc = RollbackService(db)
    rollback_result = rollback_svc.execute_rollback(
        rejected_checkpoint_id=checkpoint_id,
        hr_feedback=hr_notes,
        decided_by_user_id=decided_by,
    )

    _send_ws_event(
        company_id=company_id,
        campaign_id=campaign_id,
        event="checkpoint.rejected",
        payload={
            "checkpoint_id": checkpoint_id,
            "resume_node": rollback_result["resume_node"],
            "message": f"Rolled back to {rollback_result['resume_node']} — re-running with feedback",
        },
    )

    try:
        restored = rollback_result["state_snapshot"]
        resume_node = rollback_result["resume_node"]  # e.g. "campus_discovery"

        logger.info(f"[Pipeline:Rejected] Directly calling agent '{resume_node}' with hr_feedback")

        # Command(goto=...) does not reliably jump to mid-graph nodes in
        # LangGraph 0.2.59 with a live PostgresSaver thread.
        # Solution: call the target agent function directly in Python,
        # then persist result into graph state, then invoke(None) so the
        # graph continues from the NEXT checkpoint node after the agent.
        agent_module_map = {
            "campus_discovery":     ("app.agents.campus_discovery",    "campus_discovery_node"),
            "jd_generation":        ("app.agents.jd_generation",       "jd_generation_node"),
            "resume_intelligence":  ("app.agents.resume_intelligence",  "resume_intelligence_node"),
            "evaluation":           ("app.agents.evaluation",           "evaluation_node"),
            "scheduling":           ("app.agents.scheduling",           "scheduling_node"),
            "interview_evaluation": ("app.agents.interview_evaluation", "interview_evaluation_node"),
            "decision":             ("app.agents.decision",             "decision_node"),
            "offer":                ("app.agents.offer",                "offer_node"),
        }

        import importlib
        if resume_node in agent_module_map:
            mod_path, func_name = agent_module_map[resume_node]
            mod = importlib.import_module(mod_path)
            agent_fn = getattr(mod, func_name)
            updated_state = agent_fn(restored, db=db)
            logger.info(f"[Pipeline:Rejected] Agent '{resume_node}' completed — persisting state")
        else:
            logger.warning(f"[Pipeline:Rejected] No direct mapping for '{resume_node}' — using restored state")
            updated_state = restored

        # Persist agent output into graph thread, then continue
        graph.update_state(config, updated_state)
        graph.invoke(None, config=config)

        snapshot = graph.get_state(config)
        if snapshot.next:
            logger.info(f"[Pipeline:Rejected] Paused at checkpoint after rollback — next={snapshot.next}")
            _save_checkpoint_from_graph_state(db, graph, config, campaign_id, company_id)
        else:
            _on_pipeline_complete_by_id(db, campaign_id, company_id)

    except NodeInterrupt as ni:
        logger.info(f"[Pipeline:Rejected] Paused at checkpoint after rollback (exception) — {ni}")
        _save_checkpoint_from_graph_state(db, graph, config, campaign_id, company_id)

    return {"status": "ok", "decision": "rejected", "campaign_id": campaign_id}


def _handle_revision(db, graph, config, checkpoint_id, company_id, campaign_id, hr_notes, decided_by):
    """Re-run the same agent with hr_feedback injected."""
    rollback_svc = RollbackService(db)
    revision_result = rollback_svc.execute_revision(
        checkpoint_id=checkpoint_id,
        hr_feedback=hr_notes,
        decided_by_user_id=decided_by,
    )

    _send_ws_event(
        company_id=company_id,
        campaign_id=campaign_id,
        event="checkpoint.revision",
        payload={
            "checkpoint_id": checkpoint_id,
            "resume_node": revision_result["resume_node"],
            "message": f"Revision requested — re-running {revision_result['resume_node']}",
        },
    )

    try:
        restored = revision_result["state_snapshot"]
        resume_node = revision_result["resume_node"]

        logger.info(f"[Pipeline:Revision] Directly calling agent '{resume_node}' with hr_feedback")

        agent_module_map = {
            "campus_discovery":     ("app.agents.campus_discovery",    "campus_discovery_node"),
            "jd_generation":        ("app.agents.jd_generation",       "jd_generation_node"),
            "resume_intelligence":  ("app.agents.resume_intelligence",  "resume_intelligence_node"),
            "evaluation":           ("app.agents.evaluation",           "evaluation_node"),
            "scheduling":           ("app.agents.scheduling",           "scheduling_node"),
            "interview_evaluation": ("app.agents.interview_evaluation", "interview_evaluation_node"),
            "decision":             ("app.agents.decision",             "decision_node"),
            "offer":                ("app.agents.offer",                "offer_node"),
        }

        import importlib
        if resume_node in agent_module_map:
            mod_path, func_name = agent_module_map[resume_node]
            mod = importlib.import_module(mod_path)
            agent_fn = getattr(mod, func_name)
            updated_state = agent_fn(restored, db=db)
            logger.info(f"[Pipeline:Revision] Agent '{resume_node}' completed — persisting state")
        else:
            logger.warning(f"[Pipeline:Revision] No direct mapping for '{resume_node}' — using restored state")
            updated_state = restored

        graph.update_state(config, updated_state)
        graph.invoke(None, config=config)

        snapshot = graph.get_state(config)
        if snapshot.next:
            logger.info(f"[Pipeline:Revision] Paused at checkpoint after revision — next={snapshot.next}")
            _save_checkpoint_from_graph_state(db, graph, config, campaign_id, company_id)
        else:
            _on_pipeline_complete_by_id(db, campaign_id, company_id)

    except NodeInterrupt as ni:
        logger.info(f"[Pipeline:Revision] Paused at checkpoint after revision (exception) — {ni}")
        _save_checkpoint_from_graph_state(db, graph, config, campaign_id, company_id)

    return {"status": "ok", "decision": "revision_requested", "campaign_id": campaign_id}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _on_pipeline_complete(db, campaign, company_id, campaign_id):
    """Mark campaign completed and notify HR."""
    campaign.status = CampaignStatus.completed
    db.commit()
    _send_ws_event(
        company_id=company_id,
        campaign_id=campaign_id,
        event="pipeline.completed",
        payload={
            "campaign_id": campaign_id,
            "message": "Pipeline completed successfully — all stages done!",
        },
    )
    logger.info(f"[Pipeline] Completed — campaign={campaign_id}")


def _on_pipeline_complete_by_id(db, campaign_id, company_id):
    """Same as above but fetches campaign from DB by ID."""
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if campaign:
        _on_pipeline_complete(db, campaign, company_id, campaign_id)


def _send_ws_event(company_id: str, campaign_id: str, event: str, payload: dict):
    """
    Send WebSocket event from Celery worker context.
    Uses asyncio.run() since Celery workers are synchronous.
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Inside async context — create task
            loop.create_task(
                ws_manager.send_event(company_id, campaign_id, event, payload)
            )
        else:
            loop.run_until_complete(
                ws_manager.send_event(company_id, campaign_id, event, payload)
            )
    except Exception as ws_err:
        # WebSocket failures must never crash the pipeline
        logger.warning(f"[Pipeline] WebSocket notify failed (non-fatal): {ws_err}")