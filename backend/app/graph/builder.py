"""
Dynamic Graph Builder — builds a compiled LangGraph StateGraph for a campaign.

Fixed backbone (always present):
  hiring_intelligence → jd_generation → checkpoint_jd
  → campus_discovery → checkpoint_campus
  → outreach → registration → resume_intelligence
  → checkpoint_shortlist → [dynamic assessment rounds]
  → checkpoint_assessment → scheduling
  → checkpoint_schedule → [dynamic interview rounds]
  → interview_evaluation → checkpoint_interview
  → decision → checkpoint_final
  → offer → checkpoint_offer
  → onboarding → END

Dynamic nodes added from workflow_config["rounds_selected"]:
  - aptitude_test   → AptitudeTestAgent   (assessment phase)
  - coding_test     → CodingTestAgent     (assessment phase)
  - group_discussion → GDAgent            (assessment phase)
  - technical_interview → TechnicalInterviewAgent  (interview phase)
  - hr_interview    → HRInterviewAgent    (interview phase)

Checkpoint interrupts: all 8 checkpoint nodes pause for HR approval.
"""

import logging
from typing import Any

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agents.state import HireFlowState

logger = logging.getLogger(__name__)

# ── Interrupt nodes (pipeline pauses here for HR) ────────────────────────────
CHECKPOINT_NODES = {
    "checkpoint_jd",
    "checkpoint_campus",
    "checkpoint_shortlist",
    "checkpoint_assessment",
    "checkpoint_schedule",
    "checkpoint_interview",
    "checkpoint_final",
    "checkpoint_offer",
}

# ── Node → handler function mapping (populated lazily to avoid circular imports)
_NODE_REGISTRY: dict[str, Any] = {}


def _get_node_registry() -> dict[str, Any]:
    """
    Import agent functions lazily so the graph builder can be imported
    without requiring every agent module to be present yet.
    Missing agents get a safe placeholder that logs and passes state through.
    """
    global _NODE_REGISTRY
    if _NODE_REGISTRY:
        return _NODE_REGISTRY

    def _placeholder(name: str):
        def _node(state: HireFlowState) -> HireFlowState:
            logger.warning(f"[graph] Placeholder node '{name}' called — agent not yet implemented")
            return {**state, "current_stage": name}
        _node.__name__ = name
        return _node

    # Try to import real agents; fall back to placeholder if not built yet
    def _try_import(module_path: str, func_name: str, node_name: str):
        try:
            import importlib
            mod = importlib.import_module(module_path)
            return getattr(mod, func_name)
        except (ImportError, AttributeError):
            logger.debug(f"[graph] Agent '{node_name}' not found — using placeholder")
            return _placeholder(node_name)

    _NODE_REGISTRY = {
        # ── Core pipeline agents ─────────────────────────────────────────
        "hiring_intelligence": _try_import(
            "app.agents.hiring_intelligence", "hiring_intelligence_node", "hiring_intelligence"
        ),
        "jd_generation": _try_import(
            "app.agents.jd_generation", "jd_generation_node", "jd_generation"
        ),
        "campus_discovery": _try_import(
            "app.agents.campus_discovery", "campus_discovery_node", "campus_discovery"
        ),
        "outreach": _try_import(
            "app.agents.outreach", "outreach_node", "outreach"
        ),
        "registration": _try_import(
            "app.agents.registration", "registration_node", "registration"
        ),
        "resume_intelligence": _try_import(
            "app.agents.resume_intelligence", "resume_intelligence_node", "resume_intelligence"
        ),
        "evaluation": _try_import(
            "app.agents.evaluation", "evaluation_node", "evaluation"
        ),
        "scheduling": _try_import(
            "app.agents.scheduling", "scheduling_node", "scheduling"
        ),
        "interview_session": _try_import(
            "app.agents.interview_session", "interview_session_node", "interview_session"
        ),
        "interview_evaluation": _try_import(
            "app.agents.interview_evaluation", "interview_evaluation_node", "interview_evaluation"
        ),
        "decision": _try_import(
            "app.agents.decision", "decision_node", "decision"
        ),
        "offer": _try_import(
            "app.agents.offer", "offer_node", "offer"
        ),
        "onboarding": _try_import(
            "app.agents.onboarding", "onboarding_node", "onboarding"
        ),
        "error_handler": _try_import(
            "app.agents.error_handler", "error_handler_node", "error_handler"
        ),

        # ── Checkpoint nodes (pause for HR approval) ─────────────────────
        "checkpoint_jd":          _make_checkpoint_node("checkpoint_jd"),
        "checkpoint_campus":      _make_checkpoint_node("checkpoint_campus"),
        "checkpoint_shortlist":   _make_checkpoint_node("checkpoint_shortlist"),
        "checkpoint_assessment":  _make_checkpoint_node("checkpoint_assessment"),
        "checkpoint_schedule":    _make_checkpoint_node("checkpoint_schedule"),
        "checkpoint_interview":   _make_checkpoint_node("checkpoint_interview"),
        "checkpoint_final":       _make_checkpoint_node("checkpoint_final"),
        "checkpoint_offer":       _make_checkpoint_node("checkpoint_offer"),

        # ── Dynamic round agents ──────────────────────────────────────────
        "aptitude_test": _try_import(
            "app.agents.aptitude_test", "aptitude_test_node", "aptitude_test"
        ),
        "coding_test": _try_import(
            "app.agents.coding_test", "coding_test_node", "coding_test"
        ),
        "group_discussion": _try_import(
            "app.agents.group_discussion", "group_discussion_node", "group_discussion"
        ),
        "technical_interview": _try_import(
            "app.agents.technical_interview", "technical_interview_node", "technical_interview"
        ),
        "hr_interview": _try_import(
            "app.agents.hr_interview", "hr_interview_node", "hr_interview"
        ),
    }
    return _NODE_REGISTRY


def _make_checkpoint_node(stage_name: str):
    """
    Returns a node function for a checkpoint stage.
    The actual pause logic (NodeInterrupt) is in checkpoint_manager.reach_checkpoint().
    The graph builder wires the interrupt; this node just updates current_stage.
    """
    def _checkpoint_node(state: HireFlowState) -> HireFlowState:
        return {**state, "current_stage": stage_name, "checkpoint_status": "pending"}
    _checkpoint_node.__name__ = stage_name
    return _checkpoint_node


# ─────────────────────────────────────────────────────────────────────────────
# Router — decides next node based on checkpoint_status
# ─────────────────────────────────────────────────────────────────────────────

def _orchestrator_router(state: HireFlowState) -> str:
    """
    Called after checkpoint nodes to decide what happens next.
    LangGraph will have already paused at the checkpoint via interrupt_before;
    this router runs AFTER the HR decision is injected and graph is resumed.
    """
    status = state.get("checkpoint_status", "pending")
    stage = state.get("current_stage", "")
    error = state.get("error")

    if error:
        return "error_handler"

    if status == "approved":
        # Map checkpoint → next node
        _next = {
            "checkpoint_jd":         "campus_discovery",
            "checkpoint_campus":     "outreach",
            "checkpoint_shortlist":  "evaluation",
            "checkpoint_assessment": "scheduling",
            "checkpoint_schedule":   "interview_session",
            "checkpoint_interview":  "interview_evaluation",
            "checkpoint_final":      "offer",
            "checkpoint_offer":      "onboarding",
        }
        return _next.get(stage, END)

    elif status in ("rejected", "revision_requested"):
        # Rollback service handles state restoration before graph resumes
        # Graph re-enters the agent that produced this checkpoint's data
        _rerun = {
            "checkpoint_jd":         "jd_generation",
            "checkpoint_campus":     "campus_discovery",
            "checkpoint_shortlist":  "resume_intelligence",
            "checkpoint_assessment": "evaluation",
            "checkpoint_schedule":   "scheduling",
            "checkpoint_interview":  "interview_evaluation",
            "checkpoint_final":      "decision",
            "checkpoint_offer":      "offer",
        }
        return _rerun.get(stage, stage)

    # Still pending — should not happen after resume, but safe fallback
    return END


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_graph(workflow_config: dict | None = None) -> Any:
    """
    Build and compile a LangGraph StateGraph for the given workflow_config.

    workflow_config["rounds_selected"] controls which dynamic rounds are added:
        {
          "aptitude_test": true,
          "coding_test": true,
          "group_discussion": false,
          "technical_interview": true,
          "hr_interview": true
        }

    Returns a compiled LangGraph graph with:
      - All fixed backbone nodes wired
      - Dynamic round nodes inserted between checkpoint_shortlist and checkpoint_assessment
      - Dynamic interview nodes inserted between checkpoint_schedule and interview_evaluation
      - interrupt_before set on all 8 checkpoint nodes
    """
    registry = _get_node_registry()
    rounds = workflow_config.get("rounds_selected", {}) if workflow_config else {}

    # ── Build assessment rounds (between shortlist CP and assessment CP) ──────
    assessment_rounds = []
    for round_name in ["aptitude_test", "coding_test", "group_discussion"]:
        if rounds.get(round_name, False):
            assessment_rounds.append(round_name)

    # ── Build interview rounds (between schedule CP and interview evaluation) ──
    interview_rounds = []
    for round_name in ["technical_interview", "hr_interview"]:
        if rounds.get(round_name, False):
            interview_rounds.append(round_name)

    # ── Create StateGraph ─────────────────────────────────────────────────────
    graph = StateGraph(HireFlowState)

    # Register all fixed backbone nodes
    fixed_nodes = [
        "hiring_intelligence", "jd_generation",
        "checkpoint_jd", "campus_discovery",
        "checkpoint_campus", "outreach",
        "registration", "resume_intelligence",
        "checkpoint_shortlist", "evaluation",
        "checkpoint_assessment", "scheduling",
        "checkpoint_schedule", "interview_session",
        "interview_evaluation", "checkpoint_interview",
        "decision", "checkpoint_final",
        "offer", "checkpoint_offer",
        "onboarding", "error_handler",
    ]
    for node in fixed_nodes:
        graph.add_node(node, registry[node])

    # Register dynamic round nodes
    for round_name in assessment_rounds + interview_rounds:
        graph.add_node(round_name, registry[round_name])

    # ── Wire fixed backbone edges ─────────────────────────────────────────────
    graph.set_entry_point("hiring_intelligence")
    graph.add_edge("hiring_intelligence", "jd_generation")
    graph.add_edge("jd_generation", "checkpoint_jd")

    # After checkpoint_jd — conditional on HR decision
    graph.add_conditional_edges("checkpoint_jd", _orchestrator_router)

    graph.add_edge("campus_discovery", "checkpoint_campus")
    graph.add_conditional_edges("checkpoint_campus", _orchestrator_router)

    graph.add_edge("outreach", "registration")
    graph.add_edge("registration", "resume_intelligence")
    graph.add_edge("resume_intelligence", "checkpoint_shortlist")
    graph.add_conditional_edges("checkpoint_shortlist", _orchestrator_router)

    # ── Wire assessment rounds dynamically ────────────────────────────────────
    if assessment_rounds:
        # evaluation → first assessment round
        graph.add_edge("evaluation", assessment_rounds[0])
        # chain assessment rounds
        for i in range(len(assessment_rounds) - 1):
            graph.add_edge(assessment_rounds[i], assessment_rounds[i + 1])
        # last assessment round → checkpoint_assessment
        graph.add_edge(assessment_rounds[-1], "checkpoint_assessment")
    else:
        # No assessment rounds — evaluation goes straight to checkpoint
        graph.add_edge("evaluation", "checkpoint_assessment")

    graph.add_conditional_edges("checkpoint_assessment", _orchestrator_router)

    graph.add_edge("scheduling", "checkpoint_schedule")
    graph.add_conditional_edges("checkpoint_schedule", _orchestrator_router)

    # ── Wire interview rounds dynamically ─────────────────────────────────────
    if interview_rounds:
        graph.add_edge("interview_session", interview_rounds[0])
        for i in range(len(interview_rounds) - 1):
            graph.add_edge(interview_rounds[i], interview_rounds[i + 1])
        graph.add_edge(interview_rounds[-1], "interview_evaluation")
    else:
        graph.add_edge("interview_session", "interview_evaluation")

    graph.add_edge("interview_evaluation", "checkpoint_interview")
    graph.add_conditional_edges("checkpoint_interview", _orchestrator_router)

    graph.add_edge("decision", "checkpoint_final")
    graph.add_conditional_edges("checkpoint_final", _orchestrator_router)

    graph.add_edge("offer", "checkpoint_offer")
    graph.add_conditional_edges("checkpoint_offer", _orchestrator_router)

    graph.add_edge("onboarding", END)
    graph.add_edge("error_handler", END)

    # ── Compile with interrupt_before all checkpoint nodes ────────────────────
    checkpointer = MemorySaver()
    compiled = graph.compile(
        checkpointer=checkpointer,
        interrupt_before=list(CHECKPOINT_NODES),
    )

    logger.info(
        f"[graph] Compiled graph — assessment_rounds={assessment_rounds}, "
        f"interview_rounds={interview_rounds}"
    )
    return compiled


def get_graph_preview(workflow_config: dict | None = None) -> dict:
    """
    Returns a human-readable preview of the pipeline stages
    without actually compiling the graph (for API responses).
    """
    rounds = workflow_config.get("rounds_selected", {}) if workflow_config else {}

    stages = [
        {"order": 1,  "node": "hiring_intelligence", "type": "agent",      "label": "Hiring Intelligence Analysis"},
        {"order": 2,  "node": "jd_generation",        "type": "agent",      "label": "Job Description Generation"},
        {"order": 3,  "node": "checkpoint_jd",         "type": "checkpoint", "label": "CP1: JD Approval"},
        {"order": 4,  "node": "campus_discovery",      "type": "agent",      "label": "Campus Discovery"},
        {"order": 5,  "node": "checkpoint_campus",     "type": "checkpoint", "label": "CP2: Campus Selection Approval"},
        {"order": 6,  "node": "outreach",              "type": "agent",      "label": "College Outreach"},
        {"order": 7,  "node": "registration",          "type": "agent",      "label": "Student Registration"},
        {"order": 8,  "node": "resume_intelligence",   "type": "agent",      "label": "Resume Screening"},
        {"order": 9,  "node": "checkpoint_shortlist",  "type": "checkpoint", "label": "CP3: Shortlist Approval"},
        {"order": 10, "node": "evaluation",            "type": "agent",      "label": "Candidate Evaluation"},
    ]

    order = 11
    for rnd in ["aptitude_test", "coding_test", "group_discussion"]:
        if rounds.get(rnd, False):
            stages.append({"order": order, "node": rnd, "type": "dynamic_round", "label": rnd.replace("_", " ").title()})
            order += 1

    stages += [
        {"order": order,   "node": "checkpoint_assessment", "type": "checkpoint", "label": "CP4: Assessment Approval"},
        {"order": order+1, "node": "scheduling",            "type": "agent",      "label": "Interview Scheduling"},
        {"order": order+2, "node": "checkpoint_schedule",   "type": "checkpoint", "label": "CP5: Schedule Approval"},
    ]
    order += 3

    for rnd in ["technical_interview", "hr_interview"]:
        if rounds.get(rnd, False):
            stages.append({"order": order, "node": rnd, "type": "dynamic_round", "label": rnd.replace("_", " ").title()})
            order += 1

    stages += [
        {"order": order,   "node": "interview_evaluation", "type": "agent",      "label": "Interview Evaluation"},
        {"order": order+1, "node": "checkpoint_interview",  "type": "checkpoint", "label": "CP6: Interview Results Approval"},
        {"order": order+2, "node": "decision",              "type": "agent",      "label": "Final Decision"},
        {"order": order+3, "node": "checkpoint_final",      "type": "checkpoint", "label": "CP7: Final Selection Approval"},
        {"order": order+4, "node": "offer",                 "type": "agent",      "label": "Offer Generation"},
        {"order": order+5, "node": "checkpoint_offer",      "type": "checkpoint", "label": "CP8: Offer Approval"},
        {"order": order+6, "node": "onboarding",            "type": "agent",      "label": "Onboarding"},
    ]

    return {
        "total_stages": len(stages),
        "checkpoint_count": sum(1 for s in stages if s["type"] == "checkpoint"),
        "dynamic_rounds": [s["node"] for s in stages if s["type"] == "dynamic_round"],
        "stages": stages,
    }
