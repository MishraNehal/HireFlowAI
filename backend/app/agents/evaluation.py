"""
Agent 6 -- Evaluation

LangGraph node. Per the graph wiring in app/graph/builder.py, this runs
AFTER checkpoint_shortlist is approved by HR (resume_intelligence has
already scored every candidate by this point via Task 4.3's Celery flow;
checkpoint_shortlist is HR's gate to proceed with ranking/shortlisting).
Its own output feeds straight into the assessment rounds / checkpoint_assessment
-- there is no separate approval gate for the shortlist itself in the
current graph, so this node does not call reach_checkpoint().

What it does:
    1. Pulls every scored candidate for this campaign directly from the DB
       (Candidate JOIN Score) -- not from state["candidates"], since the
       real resume pipeline (Task 4.3/4.6) writes to relational tables,
       not into LangGraph's in-memory state.
    2. Ranks by total_score DESC.
    3. Shortlists anyone in the top N% OR at/above the cutoff score
       (whichever is more inclusive) -- avoids starving the shortlist when
       scores cluster low, and avoids being too lax when many candidates
       clear the bar.
    4. Updates Candidate.status to shortlisted/rejected in the DB, and
       writes a lightweight ranked summary into state["shortlisted"] for
       the checkpoint snapshot / dashboard.

Idempotent by design: filters on "has a Score row for this campaign" (via
the JOIN) rather than "status == screened", so it can safely re-run if the
graph re-enters this node after a checkpoint_assessment rejection.
"""
import logging

from sqlalchemy.orm import Session

from app.agents.state import HireFlowState
from app.models.candidate import Candidate, CandidateStatus, Score

logger = logging.getLogger(__name__)

DEFAULT_CUTOFF_SCORE = 60.0
DEFAULT_TOP_PERCENT = 0.30


def evaluation_node(state: HireFlowState, db: Session = None) -> HireFlowState:
    """
    LangGraph node function for the Evaluation Agent.

    Accepts db as an optional injected dependency, matching the pattern
    used by hiring_intelligence_node / jd_generation_node: when running
    inside Celery (pipeline_tasks.py), db is passed explicitly; when
    LangGraph calls this node directly, it falls back to its own session.
    """
    campaign_id = state.get("campaign_id", "unknown")
    workflow_config = state.get("workflow_config", {})
    cutoff_score = workflow_config.get("shortlist_cutoff_score", DEFAULT_CUTOFF_SCORE)
    top_percent = workflow_config.get("shortlist_top_percent", DEFAULT_TOP_PERCENT)

    logger.info(
        f"[Agent6:Evaluation] Starting -- campaign={campaign_id}, "
        f"cutoff_score={cutoff_score}, top_percent={top_percent}"
    )

    # -- Get DB session if not injected ----------------------------------------
    _own_db = False
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal()
        _own_db = True

    try:
        # -- Step 1: Pull every scored candidate for this campaign -------------
        scored_candidates = (
            db.query(Candidate)
            .join(Score, Score.candidate_id == Candidate.id)
            .filter(Candidate.campaign_id == campaign_id)
            .all()
        )

        if not scored_candidates:
            logger.warning(
                f"[Agent6:Evaluation] No scored candidates found for campaign={campaign_id} "
                f"-- nothing to shortlist yet."
            )
            return {
                **state,
                "shortlisted": [],
                "current_stage": "evaluation",
                "error": None,
            }

        # -- Step 2: Rank by total_score DESC -----------------------------------
        ranked = sorted(
            scored_candidates,
            key=lambda c: c.score.total_score if c.score and c.score.total_score is not None else 0.0,
            reverse=True,
        )
        total = len(ranked)
        top_n = max(1, round(total * top_percent))

        # -- Step 3: Decide who's shortlisted ------------------------------------
        shortlisted_ids: set = set()
        for i, candidate in enumerate(ranked):
            score_value = candidate.score.total_score if candidate.score and candidate.score.total_score is not None else 0.0
            if i < top_n or score_value >= cutoff_score:
                shortlisted_ids.add(candidate.id)

        # -- Step 4: Persist status + build state summary ------------------------
        shortlisted_summaries = []
        for rank, candidate in enumerate(ranked, start=1):
            is_shortlisted = candidate.id in shortlisted_ids
            candidate.status = CandidateStatus.shortlisted if is_shortlisted else CandidateStatus.rejected

            if is_shortlisted:
                shortlisted_summaries.append({
                    "candidate_id": str(candidate.id),
                    "name": candidate.name,
                    "email": candidate.email,
                    "total_score": candidate.score.total_score,
                    "recommendation": candidate.score.recommendation.value if candidate.score.recommendation else None,
                    "rank": rank,
                })

        db.commit()

        logger.info(
            f"[Agent6:Evaluation] Shortlisted {len(shortlisted_summaries)}/{total} candidates "
            f"for campaign={campaign_id}"
        )

        return {
            **state,
            "shortlisted": shortlisted_summaries,
            "current_stage": "evaluation",
            "error": None,
        }

    except Exception as e:
        logger.error(f"[Agent6:Evaluation] Failed: {e}", exc_info=True)
        db.rollback()
        return {
            **state,
            "shortlisted": [],
            "current_stage": "evaluation",
            "error": f"EvaluationAgent failed: {str(e)}",
        }

    finally:
        if _own_db:
            db.close()
