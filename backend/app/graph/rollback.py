"""
RollbackService — finds the most recent approved checkpoint before a rejected
stage and restores the pipeline to that point.

Design:
  - On rejection, we do NOT restart from scratch.
  - We find the LAST approved checkpoint before the rejected stage.
  - We restore HireFlowState from that checkpoint's state_snapshot.
  - We inject hr_feedback so the agent knows what to fix.
  - We return the target node name so the pipeline task can resume from there.

Example:
  Stages: hiring_intelligence → jd_generation → [CP1 approved]
           → campus_discovery → [CP2 pending → REJECTED]

  Rollback finds: CP1 (last approved before CP2)
  Restores state from CP1's snapshot
  Injects hr_feedback
  Resumes from: campus_discovery (the node AFTER CP1)
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.campaign import Checkpoint, CheckpointStatus, Campaign, CampaignStatus
from app.graph.checkpoint_manager import CHECKPOINT_STAGES

logger = logging.getLogger(__name__)


# Maps each checkpoint stage → the agent node that runs AFTER it resumes
CHECKPOINT_TO_NEXT_NODE = {
    "checkpoint_jd":          "campus_discovery",
    "checkpoint_campus":      "outreach",
    "checkpoint_shortlist":   "evaluation",
    "checkpoint_assessment":  "scheduling",
    "checkpoint_schedule":    "interview_session",
    "checkpoint_interview":   "decision",
    "checkpoint_final":       "offer",
    "checkpoint_offer":       "onboarding",
}

# Maps each checkpoint stage → the agent node that PRODUCES its output
# (used to re-run the agent on revision_requested)
CHECKPOINT_TO_AGENT_NODE = {
    "checkpoint_jd":          "jd_generation",
    "checkpoint_campus":      "campus_discovery",
    "checkpoint_shortlist":   "resume_intelligence",
    "checkpoint_assessment":  "evaluation",
    "checkpoint_schedule":    "scheduling",
    "checkpoint_interview":   "interview_evaluation",
    "checkpoint_final":       "decision",
    "checkpoint_offer":       "offer",
}


class RollbackService:
    def __init__(self, db: Session):
        self.db = db

    # ─────────────────────────────────────────────────────────────────────────
    # Public methods
    # ─────────────────────────────────────────────────────────────────────────

    def execute_rollback(
        self,
        rejected_checkpoint_id: str,
        hr_feedback: str,
        decided_by_user_id: Optional[str] = None,
    ) -> dict:
        """
        Main entry point — called when HR rejects a checkpoint.

        Returns:
            {
              "state_snapshot":    dict,   # restored HireFlowState
              "resume_node":       str,    # node to resume pipeline from
              "rollback_target_id": str,   # checkpoint we rolled back TO
              "campaign_id":       str,
            }
        """
        rejected_cp = self._get_checkpoint(rejected_checkpoint_id)

        # Mark the rejected checkpoint
        rejected_cp.status = CheckpointStatus.rejected
        rejected_cp.hr_notes = hr_feedback
        rejected_cp.decided_by = decided_by_user_id
        rejected_cp.decided_at = datetime.utcnow()
        self.db.commit()

        # Find the last approved checkpoint before the rejected stage
        rollback_target = self._find_rollback_target(
            campaign_id=str(rejected_cp.campaign_id),
            rejected_stage_order=rejected_cp.stage_order,
        )

        if rollback_target is None:
            # No previous approved checkpoint — restart from the agent
            # that feeds the rejected checkpoint
            logger.warning(
                f"[rollback] No approved checkpoint found before "
                f"{rejected_cp.stage_name} — re-running its agent"
            )
            return self._rerun_agent_for_checkpoint(rejected_cp, hr_feedback)

        # Mark all checkpoints AFTER rollback target as rolled_back
        self._invalidate_checkpoints_after(
            campaign_id=str(rejected_cp.campaign_id),
            after_stage_order=rollback_target.stage_order,
        )

        # Restore state from the rollback target's snapshot
        restored_state = dict(rollback_target.state_snapshot)
        restored_state["checkpoint_status"] = "approved"
        restored_state["hr_feedback"] = hr_feedback
        restored_state["rollback_to"] = rollback_target.stage_name

        # Resume from the node that runs AFTER the rollback target checkpoint
        resume_node = CHECKPOINT_TO_NEXT_NODE.get(
            rollback_target.stage_name,
            rollback_target.stage_name,  # fallback
        )

        logger.info(
            f"[rollback] Rolling back campaign {rejected_cp.campaign_id} "
            f"from {rejected_cp.stage_name} → target={rollback_target.stage_name} "
            f"→ resuming at {resume_node}"
        )

        return {
            "state_snapshot": restored_state,
            "resume_node": resume_node,
            "rollback_target_id": str(rollback_target.id),
            "campaign_id": str(rejected_cp.campaign_id),
        }

    def execute_revision(
        self,
        checkpoint_id: str,
        hr_feedback: str,
        decided_by_user_id: Optional[str] = None,
    ) -> dict:
        """
        Called when HR requests revision (not full rejection).
        Re-runs the SAME agent that produced the checkpoint output,
        with hr_feedback injected.

        Returns same shape as execute_rollback.
        """
        cp = self._get_checkpoint(checkpoint_id)

        cp.status = CheckpointStatus.revision_requested
        cp.hr_notes = hr_feedback
        cp.decided_by = decided_by_user_id
        cp.decided_at = datetime.utcnow()
        self.db.commit()

        return self._rerun_agent_for_checkpoint(cp, hr_feedback)

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_checkpoint(self, checkpoint_id: str) -> Checkpoint:
        cp = self.db.query(Checkpoint).filter(Checkpoint.id == checkpoint_id).first()
        if not cp:
            raise ValueError(f"Checkpoint {checkpoint_id} not found")
        return cp

    def _find_rollback_target(
        self,
        campaign_id: str,
        rejected_stage_order: int,
    ) -> Optional[Checkpoint]:
        """
        Find the most recent APPROVED checkpoint BEFORE the rejected one.
        """
        return (
            self.db.query(Checkpoint)
            .filter(
                Checkpoint.campaign_id == campaign_id,
                Checkpoint.status == CheckpointStatus.approved,
                Checkpoint.stage_order < rejected_stage_order,
            )
            .order_by(Checkpoint.stage_order.desc())
            .first()
        )

    def _invalidate_checkpoints_after(
        self,
        campaign_id: str,
        after_stage_order: int,
    ) -> None:
        """
        Mark all checkpoints with stage_order > after_stage_order as rolled_back.
        This clears the 'future' that is now being redone.
        """
        checkpoints_to_invalidate = (
            self.db.query(Checkpoint)
            .filter(
                Checkpoint.campaign_id == campaign_id,
                Checkpoint.stage_order > after_stage_order,
            )
            .all()
        )
        for cp in checkpoints_to_invalidate:
            cp.status = CheckpointStatus.rolled_back
            logger.debug(f"[rollback] Invalidated checkpoint {cp.stage_name} (order={cp.stage_order})")

        self.db.commit()

    def _rerun_agent_for_checkpoint(
        self,
        checkpoint: Checkpoint,
        hr_feedback: str,
    ) -> dict:
        """
        When there's no earlier checkpoint to roll back to,
        re-run the agent that produced this checkpoint's data.
        """
        restored_state = dict(checkpoint.state_snapshot)
        restored_state["checkpoint_status"] = "revision_requested"
        restored_state["hr_feedback"] = hr_feedback
        restored_state["rollback_to"] = checkpoint.stage_name

        resume_node = CHECKPOINT_TO_AGENT_NODE.get(
            checkpoint.stage_name,
            checkpoint.stage_name,
        )

        return {
            "state_snapshot": restored_state,
            "resume_node": resume_node,
            "rollback_target_id": None,
            "campaign_id": str(checkpoint.campaign_id),
        }
