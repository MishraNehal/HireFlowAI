"""
Agent 3 — Campus Discovery

Fourth node in the LangGraph pipeline (after checkpoint_jd approval).

What it does:
  1. RAG query — pulls college performance history from knowledge_base
     (doc_type=college_performance) to understand past placement quality.
  2. PostgreSQL query — fetches all colleges from the colleges table,
     filtered/sorted by tier and historical_rating.
  3. Groq LLM — ranks and recommends colleges with detailed reasoning,
     matching them against the role requirements and hiring strategy.
  4. Updates state["selected_colleges"] with ranked + reasoned list.

Checkpoint after this node: CP2 — Campus Selection Approval.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.agents.state import HireFlowState
from app.services.llm import call_llm_json
from app.services.rag import query_knowledge_base
from app.models.campaign import College, CollegeTier

logger = logging.getLogger(__name__)

_SYSTEM = """You are HireFlow's Campus Discovery Agent — an expert in Indian
engineering college rankings, placement statistics, and campus recruitment
strategy.

Your job is to analyse college performance data and recommend the best colleges
for a specific hiring campaign, providing clear reasoning for each selection.

Consider: college tier, historical placement ratings, location, relevant
branch availability, and fit for the specific role being hired for.
Always respond with a valid JSON object."""


def campus_discovery_node(state: HireFlowState, db: Session = None) -> HireFlowState:
    """
    LangGraph node function for Campus Discovery Agent.
    """
    campaign_id = state.get("campaign_id", "unknown")
    company_id = state.get("company_id", "unknown")
    workflow_config = state.get("workflow_config", {})
    hiring_strategy = state.get("hiring_strategy", {})
    job_description = state.get("job_description", {})
    hr_feedback = state.get("hr_feedback")
    checkpoint_status = state.get("checkpoint_status", "")

    is_revision = checkpoint_status == "revision_requested" and hr_feedback
    logger.info(
        f"[Agent3:CampusDiscovery] Starting — campaign={campaign_id}, "
        f"revision={is_revision}"
    )

    _own_db = False
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal()
        _own_db = True

    try:
        # ── Step 1: RAG — college performance history ─────────────────────────
        rag_context = ""
        try:
            rag_results = query_knowledge_base(
                db=db,
                company_id=company_id,
                query="college performance placement history student quality tier ranking",
                n_results=5,
            )
            if rag_results:
                rag_context = "\n\n".join(
                    f"[College Performance #{i+1}]\n{r['content']}"
                    for i, r in enumerate(rag_results)
                )
        except Exception as rag_err:
            logger.warning(f"[Agent3] RAG query failed: {rag_err}")

        if not rag_context:
            rag_context = "No historical college performance data available."

        # ── Step 2: PostgreSQL — fetch all colleges ───────────────────────────
        colleges_db = (
            db.query(College)
            .order_by(
                College.tier.asc(),                        # tier1 first
                desc(College.historical_rating),           # highest rating first
            )
            .all()
        )

        colleges_list = [
            {
                "id": str(c.id),
                "name": c.name,
                "city": c.city,
                "state": c.state,
                "tier": c.tier.value if c.tier else "tier2",
                "historical_rating": c.historical_rating,
                "tpo_name": c.tpo_name,
                "placement_email": c.placement_email,
            }
            for c in colleges_db
        ]

        logger.info(f"[Agent3:CampusDiscovery] Fetched {len(colleges_list)} colleges from DB")

        # ── Step 3: Build LLM prompt ──────────────────────────────────────────
        role = workflow_config.get("role", job_description.get("title", "Software Engineer Intern"))
        openings = workflow_config.get("openings", 10)
        location = workflow_config.get("location", "India")
        skills_required = workflow_config.get("skills_required", [])

        # How many colleges per tier from hiring strategy
        recommended_tiers = hiring_strategy.get("recommended_colleges", [
            {"tier": "tier1", "count": 2, "reasoning": "Quality candidates"},
            {"tier": "tier2", "count": 5, "reasoning": "Good volume"},
            {"tier": "tier3", "count": 3, "reasoning": "Diversity"},
        ])

        revision_section = ""
        if is_revision:
            revision_section = f"""
## ⚠️ REVISION REQUESTED BY HR
Previous college selection was rejected. HR feedback:
\"{hr_feedback}\"

You MUST address all feedback points in the revised selection.
"""

        prompt = f"""Analyse the available colleges and recommend the best ones for this campaign.
{revision_section}
## Campaign Details
- Role: {role}
- Openings: {openings}
- Location Preference: {location}
- Required Skills: {', '.join(skills_required) if skills_required else 'Engineering fundamentals'}

## Hiring Strategy Recommendation
{chr(10).join(f"- {t['tier']}: Target {t['count']} colleges — {t['reasoning']}" for t in recommended_tiers)}

## Available Colleges ({len(colleges_list)} total)
{_format_colleges_for_prompt(colleges_list)}

## Historical Performance Context
{rag_context}

## Instructions
Select and rank the best colleges for this campaign. Return a JSON object:

{{
  "selected_colleges": [
    {{
      "id": "string — college UUID from the list above",
      "name": "string — college name",
      "city": "string",
      "state": "string",
      "tier": "tier1 | tier2 | tier3",
      "historical_rating": "number or null",
      "rank": "number — 1 = top choice",
      "selection_reasoning": "string — specific reason this college was selected",
      "expected_candidates": "number — estimated students who will apply",
      "priority": "high | medium | low"
    }}
  ],
  "summary": {{
    "total_colleges_selected": "number",
    "tier1_count": "number",
    "tier2_count": "number",
    "tier3_count": "number",
    "total_expected_candidates": "number",
    "selection_strategy": "string — 2-3 sentences on the overall approach"
  }},
  "excluded_colleges": [
    {{
      "name": "string",
      "reason": "string — why excluded"
    }}
  ]
}}

Select 8-15 colleges total. Prioritise colleges with high historical_rating.
For roles requiring strong coding skills, prefer tier1 and top tier2 colleges."""

        # ── Step 4: Call Groq ─────────────────────────────────────────────────
        result = call_llm_json(
            prompt=prompt,
            system=_SYSTEM,
            temperature=0.3,
            max_tokens=3000,
        )

        selected_colleges = result.get("selected_colleges", [])

        # Inject metadata
        output = {
            "selected_colleges": selected_colleges,
            "summary": result.get("summary", {}),
            "excluded_colleges": result.get("excluded_colleges", []),
            "generated_at": datetime.utcnow().isoformat(),
            "campaign_id": campaign_id,
            "total_available": len(colleges_list),
            "is_revision": is_revision,
        }

        logger.info(
            f"[Agent3:CampusDiscovery] Selected {len(selected_colleges)} colleges, "
            f"revision={is_revision}"
        )

        return {
            **state,
            "selected_colleges": selected_colleges,
            "current_stage": "campus_discovery",
            "checkpoint_status": "pending",
            "hr_feedback": None,
            "error": None,
        }

    except Exception as e:
        logger.error(f"[Agent3:CampusDiscovery] Failed: {e}", exc_info=True)
        return {
            **state,
            "selected_colleges": [],
            "current_stage": "campus_discovery",
            "error": f"CampusDiscoveryAgent failed: {str(e)}",
        }

    finally:
        if _own_db:
            db.close()


def _format_colleges_for_prompt(colleges: list[dict]) -> str:
    """Format college list for LLM prompt — concise but complete."""
    if not colleges:
        return "No colleges available in database."

    lines = []
    for c in colleges:
        rating = f"{c['historical_rating']:.1f}" if c['historical_rating'] else "N/A"
        lines.append(
            f"- [{c['tier'].upper()}] {c['name']} | {c['city']}, {c['state']} "
            f"| Rating: {rating} | ID: {c['id']}"
        )
    return "\n".join(lines)
