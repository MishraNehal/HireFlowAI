"""
HireFlowState — the single shared state object that flows through every node
in the LangGraph pipeline.

All 16 agents read from and write to this TypedDict. LangGraph serializes it
to JSON and persists it in the PostgreSQL checkpointer between node executions,
so every field must be JSON-serializable (str, int, float, bool, list, dict, None).
"""
from typing import TypedDict, Optional


class HireFlowState(TypedDict):
    # ── Core identifiers ──────────────────────────────────────────────────────
    company_id: str          # UUID of the company running this campaign
    campaign_id: str         # UUID of the campaign being processed

    # ── Configuration ─────────────────────────────────────────────────────────
    workflow_config: dict    # rounds_selected, approval_gates, timeline, etc.

    # ── Agent outputs (populated progressively as pipeline advances) ──────────
    hiring_strategy: dict    # Agent 1: recommended colleges, salary benchmark,
                             #          suggested rounds, timeline
    job_description: dict    # Agent 2: full JD with title, responsibilities,
                             #          skills, eligibility, stipend, outreach msg
    selected_colleges: list  # Agent 3: ranked + approved colleges with reasoning
    candidates: list         # Collected candidate profiles from all colleges
    shortlisted: list        # After resume intelligence screening
    assessment_results: list # After skill assessment rounds
    interview_sessions: list # Interview records (voice/video)
    final_selected: list     # Final selected candidates after all rounds
    offers: list             # Offer letters sent and their statuses

    # ── Pipeline control ──────────────────────────────────────────────────────
    current_stage: str       # Current node name (e.g. "jd_generation")
    checkpoint_status: str   # "pending" | "approved" | "rejected" | "revision_requested"
    hr_feedback: Optional[str]   # HR notes injected on rejection / revision
    rollback_to: Optional[str]   # Target node name for rollback execution
    error: Optional[str]         # Error message — triggers error_handler node
