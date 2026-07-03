"""
Agent 2 — JD Generation

Second node in the LangGraph pipeline.

What it does:
  1. RAG query — pulls past JDs for the same role from knowledge_base
     (doc_type=past_jd) to use as reference.
  2. Uses hiring_strategy from Agent 1 as additional context.
  3. Groq LLM — generates a complete, structured Job Description with:
       title, responsibilities, required skills, preferred skills,
       eligibility, stipend, selection process, timeline, outreach message.
  4. On revision_requested: injects hr_feedback into the prompt and regenerates.
  5. Updates state["job_description"] and state["current_stage"].

Checkpoint after this node: CP1 — JD Approval (handled by graph builder).
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.state import HireFlowState
from app.services.llm import call_llm_json
from app.services.rag import query_knowledge_base

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = """You are HireFlow's JD Generation Agent — an expert technical
recruiter and content writer specialising in Indian campus recruitment.

Your job is to generate professional, detailed, and compelling Job Descriptions
that attract the best talent from engineering colleges across India.

Guidelines:
- Be specific about technical requirements (not vague)
- Use clear, professional language suitable for college students
- Make responsibilities realistic for interns/freshers
- Include all details students need to make informed decisions
- Always respond with a valid JSON object."""


def jd_generation_node(state: HireFlowState, db: Session = None) -> HireFlowState:
    """
    LangGraph node function for JD Generation Agent.

    On revision_requested: re-runs with hr_feedback injected into prompt.
    On normal run: generates fresh JD from RAG context + hiring_strategy.
    """
    campaign_id = state.get("campaign_id", "unknown")
    company_id = state.get("company_id", "unknown")
    workflow_config = state.get("workflow_config", {})
    hiring_strategy = state.get("hiring_strategy", {})
    hr_feedback = state.get("hr_feedback")
    checkpoint_status = state.get("checkpoint_status", "")

    is_revision = checkpoint_status == "revision_requested" and hr_feedback
    logger.info(
        f"[Agent2:JDGeneration] Starting — campaign={campaign_id}, "
        f"revision={is_revision}"
    )

    # ── Get DB session ────────────────────────────────────────────────────────
    _own_db = False
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal()
        _own_db = True

    try:
        # ── Step 1: RAG — pull past JDs for this role ─────────────────────────
        role = workflow_config.get("role", state.get("role", "Software Engineer Intern"))
        rag_results = []

        try:
            # Query with role_tag for precise match first
            rag_results = query_knowledge_base(
                db=db,
                company_id=company_id,
                query=f"job description responsibilities skills {role}",
                role_tag=role,
                n_results=3,
            )
            # Fallback: broad JD search if role-specific returns nothing
            if not rag_results:
                rag_results = query_knowledge_base(
                    db=db,
                    company_id=company_id,
                    query=f"job description responsibilities required skills eligibility",
                    n_results=4,
                )
        except Exception as rag_err:
            logger.warning(f"[Agent2] RAG query failed: {rag_err}")

        past_jds_context = ""
        if rag_results:
            past_jds_context = "\n\n".join(
                f"[Past JD #{i+1}]\n{r['content']}"
                for i, r in enumerate(rag_results)
            )
        else:
            past_jds_context = "No past JDs available — generate from scratch."

        logger.info(f"[Agent2:JDGeneration] RAG returned {len(rag_results)} past JDs")

        # ── Step 2: Extract campaign details ─────────────────────────────────
        openings = workflow_config.get("openings", 10)
        skills_required = workflow_config.get("skills_required", [])
        skills_preferred = workflow_config.get("skills_preferred", [])
        stipend = workflow_config.get("stipend", "As per company standards")
        location = workflow_config.get("location", "India")
        work_mode = workflow_config.get("work_mode", "hybrid")
        batch_year = workflow_config.get("batch_year", datetime.now().year + 1)

        # From hiring strategy (Agent 1 output)
        salary_benchmark = hiring_strategy.get("salary_benchmark", {})
        suggested_rounds = hiring_strategy.get("suggested_rounds", {})
        role_analysis = hiring_strategy.get("role_analysis", {})
        timeline = hiring_strategy.get("timeline", {})

        # ── Step 3: Build prompt ──────────────────────────────────────────────
        revision_section = ""
        if is_revision:
            revision_section = f"""
## ⚠️ REVISION REQUESTED BY HR
The previous JD was rejected. HR feedback:
\"{hr_feedback}\"

You MUST address all feedback points in this revised JD.
"""

        prompt = f"""Generate a complete, professional Job Description for campus recruitment.
{revision_section}
## Campaign Details
- Role/Title: {role}
- Number of Openings: {openings}
- Required Skills: {', '.join(skills_required) if skills_required else 'Python, SQL, Problem Solving'}
- Preferred Skills: {', '.join(skills_preferred) if skills_preferred else 'FastAPI, Git, REST APIs'}
- Stipend: {stipend}
- Recommended Stipend Range: {salary_benchmark.get('recommended_stipend', 'As per industry standards')}
- Location: {location}
- Work Mode: {work_mode}
- Target Batch Year: {batch_year}

## Hiring Strategy Context (from Agent 1)
- Seniority Level: {role_analysis.get('seniority', 'intern')}
- Key Skills Identified: {', '.join(role_analysis.get('key_skills', skills_required))}
- Suggested Selection Rounds: {', '.join(k for k, v in suggested_rounds.items() if v is True and k != 'reasoning')}
- Estimated Drive Timeline: {timeline.get('total_weeks', 6)} weeks

## Past JDs Reference
{past_jds_context}

## Instructions
Generate a complete JD as a JSON object with exactly these fields:

{{
  "title": "string — exact job title",
  "company_overview": "string — 2-3 sentences about the hiring company (generic but professional)",
  "role_summary": "string — 3-4 sentence overview of the role",
  "responsibilities": [
    "string — specific responsibility 1",
    "string — specific responsibility 2"
    // 6-8 responsibilities total
  ],
  "required_skills": [
    "string — must-have skill with brief context"
    // 5-7 skills
  ],
  "preferred_skills": [
    "string — good-to-have skill"
    // 3-5 skills
  ],
  "eligibility": {{
    "degree": "string — e.g. B.Tech/B.E in CS/IT/ECE or related",
    "batch": "string — e.g. 2025 / 2026 passing out",
    "cgpa": "string — e.g. 7.0 or above preferred",
    "backlogs": "string — e.g. No active backlogs"
  }},
  "compensation": {{
    "stipend": "string — monthly stipend amount",
    "duration": "string — internship/job duration",
    "benefits": ["string — benefit 1", "string — benefit 2"]
  }},
  "work_details": {{
    "location": "string",
    "work_mode": "remote | hybrid | onsite",
    "working_hours": "string — e.g. 9 AM - 6 PM IST"
  }},
  "selection_process": [
    "string — Round 1: name and brief description",
    "string — Round 2: name and brief description"
    // List all rounds
  ],
  "timeline": {{
    "application_deadline": "string — e.g. 2 weeks from announcement",
    "expected_joining": "string — e.g. June/July {batch_year}"
  }},
  "outreach_email": {{
    "subject": "string — email subject for TPO outreach",
    "body": "string — full professional email to Training & Placement Officer (300-400 words)"
  }},
  "keywords": ["string — ATS keywords for this role"]
}}

Make the JD compelling, specific, and realistic for Indian campus recruitment."""

        # ── Step 4: Call Groq ─────────────────────────────────────────────────
        job_description = call_llm_json(
            prompt=prompt,
            system=_SYSTEM,
            temperature=0.4,
            max_tokens=3000,
        )

        # Inject metadata
        job_description["generated_at"] = datetime.utcnow().isoformat()
        job_description["campaign_id"] = campaign_id
        job_description["is_revision"] = is_revision
        job_description["rag_jds_used"] = len(rag_results)
        if is_revision:
            job_description["revision_feedback"] = hr_feedback

        logger.info(
            f"[Agent2:JDGeneration] JD generated — "
            f"title='{job_description.get('title', 'N/A')}', "
            f"revision={is_revision}"
        )

        return {
            **state,
            "job_description": job_description,
            "current_stage": "jd_generation",
            "checkpoint_status": "pending",   # signals graph to hit checkpoint_jd next
            "hr_feedback": None,              # clear feedback after use
            "error": None,
        }

    except Exception as e:
        logger.error(f"[Agent2:JDGeneration] Failed: {e}", exc_info=True)
        return {
            **state,
            "job_description": {},
            "current_stage": "jd_generation",
            "error": f"JDGenerationAgent failed: {str(e)}",
        }

    finally:
        if _own_db:
            db.close()
