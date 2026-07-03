"""
Agent 1 — Hiring Intelligence

First node in the LangGraph pipeline. Runs before any human checkpoint.

What it does:
  1. RAG query — pulls company history, past JDs, salary data, and college
     performance records from the knowledge_base table.
  2. Groq LLM — synthesises all context into a structured hiring_strategy
     with recommended colleges, salary benchmark, suggested rounds, and timeline.
  3. Updates state["hiring_strategy"] and state["current_stage"].

No checkpoint after this node — pipeline flows directly into jd_generation.
"""

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.state import HireFlowState
from app.services.llm import call_llm_json
from app.services.rag import query_knowledge_base

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """You are HireFlow's Hiring Intelligence Agent — an expert campus
recruitment strategist with deep knowledge of Indian engineering colleges,
placement trends, and hiring best practices.

Your job is to analyse a company's past hiring data and produce a structured
hiring strategy for the current campaign. Be specific, data-driven, and
actionable. Always respond with a valid JSON object."""

# ── RAG queries to run ────────────────────────────────────────────────────────

_RAG_QUERIES = [
    ("company history and past hiring campaigns", None),
    ("job descriptions and required skills for previous roles", None),
    ("salary benchmarks and stipend data for interns and freshers", None),
    ("college performance placement history tier ranking", None),
    ("candidate quality assessment scores from past drives", None),
]


def hiring_intelligence_node(state: HireFlowState, db: Session = None) -> HireFlowState:
    """
    LangGraph node function for Hiring Intelligence Agent.

    Accepts db as an optional injected dependency. When running inside
    Celery (pipeline_tasks.py), db is passed explicitly. When LangGraph
    calls this node directly during testing, it falls back to creating
    its own session.
    """
    campaign_id = state.get("campaign_id", "unknown")
    company_id = state.get("company_id", "unknown")
    workflow_config = state.get("workflow_config", {})

    logger.info(f"[Agent1:HiringIntelligence] Starting — campaign={campaign_id}")

    # ── Step 1: Get DB session if not injected ────────────────────────────────
    _own_db = False
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal()
        _own_db = True

    try:
        # ── Step 2: RAG — pull all relevant context ───────────────────────────
        rag_context_parts = []

        for query_text, role_tag in _RAG_QUERIES:
            try:
                results = query_knowledge_base(
                    db=db,
                    company_id=company_id,
                    query=query_text,
                    role_tag=role_tag,
                    n_results=3,
                )
                if results:
                    combined = "\n".join(
                        f"[{r['doc_type']}] {r['content']}" for r in results
                    )
                    rag_context_parts.append(f"### {query_text.title()}\n{combined}")
            except Exception as rag_err:
                logger.warning(f"[Agent1] RAG query failed for '{query_text}': {rag_err}")

        rag_context = "\n\n".join(rag_context_parts) if rag_context_parts else "No historical data available."

        logger.info(f"[Agent1:HiringIntelligence] RAG pulled {len(rag_context_parts)} context sections")

        # ── Step 3: Build LLM prompt ──────────────────────────────────────────
        role = workflow_config.get("role", state.get("role", "Software Engineer Intern"))
        openings = workflow_config.get("openings", 10)
        skills_required = workflow_config.get("skills_required", [])
        location = workflow_config.get("location", "India")
        batch_year = workflow_config.get("batch_year", datetime.now().year + 1)

        prompt = f"""Analyse the following company knowledge base data and generate a comprehensive
hiring strategy for this campaign.

## Campaign Details
- Role: {role}
- Openings: {openings}
- Required Skills: {', '.join(skills_required) if skills_required else 'To be determined'}
- Location: {location}
- Target Batch Year: {batch_year}

## Company Knowledge Base Context
{rag_context}

## Instructions
Generate a hiring strategy JSON with exactly these fields:

{{
  "role_analysis": {{
    "role": "string — role being hired for",
    "seniority": "intern | fresher | experienced",
    "key_skills": ["list of top 5-8 required technical skills"],
    "nice_to_have": ["list of 3-5 preferred skills"]
  }},
  "salary_benchmark": {{
    "recommended_stipend": "string — e.g. '25,000 - 30,000 per month'",
    "market_range": "string — e.g. '20,000 - 35,000 per month'",
    "basis": "string — reasoning based on historical data"
  }},
  "recommended_colleges": [
    {{
      "tier": "tier1 | tier2 | tier3",
      "count": "number of colleges to target in this tier",
      "reasoning": "string — why this tier for this role"
    }}
  ],
  "suggested_rounds": {{
    "aptitude_test": true,
    "coding_test": true,
    "group_discussion": false,
    "technical_interview": true,
    "hr_interview": true,
    "reasoning": "string — why these rounds for this role"
  }},
  "timeline": {{
    "total_weeks": "number — estimated weeks for full drive",
    "phase_breakdown": {{
      "outreach_days": 7,
      "registration_days": 14,
      "assessment_days": 7,
      "interview_days": 7,
      "offer_days": 3
    }}
  }},
  "strategy_summary": "string — 3-4 sentence executive summary of the hiring strategy",
  "confidence_score": "number between 0-1 — how confident based on available data",
  "data_source": "rag_historical | defaults"
}}

Base your recommendations on the historical data provided. If data is limited,
use sensible defaults for Indian campus recruitment and set data_source to 'defaults'."""

        # ── Step 4: Call Groq ─────────────────────────────────────────────────
        hiring_strategy = call_llm_json(
            prompt=prompt,
            system=_SYSTEM,
            temperature=0.3,
            max_tokens=2000,
        )

        # Inject metadata
        hiring_strategy["generated_at"] = datetime.utcnow().isoformat()
        hiring_strategy["campaign_id"] = campaign_id
        hiring_strategy["rag_sections_used"] = len(rag_context_parts)

        logger.info(
            f"[Agent1:HiringIntelligence] Strategy generated — "
            f"confidence={hiring_strategy.get('confidence_score', 'N/A')}, "
            f"rag_sections={len(rag_context_parts)}"
        )

        return {
            **state,
            "hiring_strategy": hiring_strategy,
            "current_stage": "hiring_intelligence",
            "error": None,
        }

    except Exception as e:
        logger.error(f"[Agent1:HiringIntelligence] Failed: {e}", exc_info=True)
        return {
            **state,
            "hiring_strategy": {},
            "current_stage": "hiring_intelligence",
            "error": f"HiringIntelligenceAgent failed: {str(e)}",
        }

    finally:
        if _own_db:
            db.close()
