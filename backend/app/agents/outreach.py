"""
Agent 4 — Outreach

Sixth node in the LangGraph pipeline (after checkpoint_campus approval).

What it does:
  1. Takes state["selected_colleges"] (approved by HR in CP2).
  2. Groq LLM — generates a personalised outreach email per college,
     using the job_description's outreach_email as a base template
     but customising it per college (name, tier, location).
  3. SendGrid — sends the email to each college's placement_email.
  4. Logs every send attempt to email_logs table.
  5. If SendGrid fails for any college — logs error, continues pipeline.
     Outreach failure is non-blocking by design.
  6. Updates state with outreach results.

No checkpoint after this node — flows directly into registration.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.state import HireFlowState
from app.services.llm import call_llm_json
from app.services.email import send_email
from app.models.campaign import (
    College, CampaignCollege, CampaignCollegeStatus,
    EmailRecipientType,
)

logger = logging.getLogger(__name__)

_SYSTEM = """You are HireFlow's Outreach Agent — an expert at writing
professional, compelling outreach emails to Training and Placement Officers
(TPOs) at engineering colleges in India.

Your emails should be:
- Professional and respectful
- Specific to the college being addressed
- Clear about the opportunity and next steps
- Concise but complete (250-350 words)
Always respond with a valid JSON object."""


def outreach_node(state: HireFlowState, db: Session = None) -> HireFlowState:
    """
    LangGraph node function for Outreach Agent.
    """
    campaign_id = state.get("campaign_id", "unknown")
    company_id = state.get("company_id", "unknown")
    selected_colleges = state.get("selected_colleges", [])
    job_description = state.get("job_description", {})
    workflow_config = state.get("workflow_config", {})

    logger.info(
        f"[Agent4:Outreach] Starting — campaign={campaign_id}, "
        f"colleges={len(selected_colleges)}"
    )

    if not selected_colleges:
        logger.warning("[Agent4:Outreach] No colleges selected — skipping outreach")
        return {
            **state,
            "current_stage": "outreach",
            "error": None,
        }

    _own_db = False
    if db is None:
        from app.database import SessionLocal
        db = SessionLocal()
        _own_db = True

    outreach_results = []

    try:
        role = job_description.get("title", workflow_config.get("role", "Software Engineer Intern"))
        base_outreach = job_description.get("outreach_email", {})
        base_subject = base_outreach.get("subject", f"Campus Recruitment Drive — {role}")
        base_body = base_outreach.get("body", "")

        # Fetch full college details from DB for placement emails
        college_ids = [c.get("id") for c in selected_colleges if c.get("id")]
        db_colleges = {}
        if college_ids:
            colleges_from_db = (
                db.query(College)
                .filter(College.id.in_(college_ids))
                .all()
            )
            db_colleges = {str(c.id): c for c in colleges_from_db}

        for college_data in selected_colleges:
            college_id = college_data.get("id")
            college_name = college_data.get("name", "Your Institution")
            college_city = college_data.get("city", "")

            # Get placement email from DB record
            db_college = db_colleges.get(college_id)
            placement_email = db_college.placement_email if db_college else None
            tpo_name = db_college.tpo_name if db_college else "Placement Officer"

            if not placement_email:
                logger.warning(
                    f"[Agent4:Outreach] No placement email for {college_name} — skipping"
                )
                outreach_results.append({
                    "college_id": college_id,
                    "college_name": college_name,
                    "status": "skipped",
                    "reason": "no_placement_email",
                })
                continue

            # ── Generate personalised email via Groq ──────────────────────────
            try:
                personalised = _generate_personalised_email(
                    college_name=college_name,
                    college_city=college_city,
                    tpo_name=tpo_name,
                    role=role,
                    base_subject=base_subject,
                    base_body=base_body,
                    job_description=job_description,
                    workflow_config=workflow_config,
                )
                subject = personalised.get("subject", base_subject)
                body = personalised.get("body", base_body)
            except Exception as llm_err:
                logger.warning(
                    f"[Agent4:Outreach] LLM personalisation failed for {college_name}: {llm_err} "
                    f"— falling back to base template"
                )
                subject = base_subject
                body = base_body.replace("{college}", college_name).replace("{name}", tpo_name)

            # ── Send email via SendGrid ───────────────────────────────────────
            try:
                email_log = send_email(
                    db=db,
                    to_email=placement_email,
                    subject=subject,
                    body=body,
                    company_id=company_id,
                    campaign_id=campaign_id,
                    recipient_type=EmailRecipientType.college,
                    email_type="college_outreach",
                )

                # Update CampaignCollege status to contacted
                _update_campaign_college_status(
                    db=db,
                    campaign_id=campaign_id,
                    college_id=college_id,
                    status=CampaignCollegeStatus.contacted,
                )

                outreach_results.append({
                    "college_id": college_id,
                    "college_name": college_name,
                    "placement_email": placement_email,
                    "status": email_log.status.value,
                    "email_log_id": str(email_log.id),
                    "sent_at": email_log.sent_at.isoformat() if email_log.sent_at else None,
                })

                logger.info(
                    f"[Agent4:Outreach] Email to {college_name} — "
                    f"status={email_log.status.value}"
                )

            except Exception as email_err:
                # Non-blocking — log and continue to next college
                logger.error(
                    f"[Agent4:Outreach] Email send failed for {college_name}: {email_err}"
                )
                outreach_results.append({
                    "college_id": college_id,
                    "college_name": college_name,
                    "status": "failed",
                    "reason": str(email_err),
                })

        sent_count = sum(1 for r in outreach_results if r.get("status") == "sent")
        logger.info(
            f"[Agent4:Outreach] Complete — {sent_count}/{len(selected_colleges)} emails sent"
        )

        # Store outreach results in workflow_config for reference
        updated_config = {
            **workflow_config,
            "outreach_results": outreach_results,
            "outreach_completed_at": datetime.utcnow().isoformat(),
        }

        return {
            **state,
            "workflow_config": updated_config,
            "current_stage": "outreach",
            "error": None,
        }

    except Exception as e:
        logger.error(f"[Agent4:Outreach] Failed: {e}", exc_info=True)
        # Outreach failure should NOT stop the pipeline
        return {
            **state,
            "current_stage": "outreach",
            "error": None,  # intentionally not setting error — outreach is non-blocking
        }

    finally:
        if _own_db:
            db.close()


def _generate_personalised_email(
    college_name: str,
    college_city: str,
    tpo_name: str,
    role: str,
    base_subject: str,
    base_body: str,
    job_description: dict,
    workflow_config: dict,
) -> dict:
    """Generate a college-specific outreach email via Groq."""

    stipend = (
        job_description.get("compensation", {}).get("stipend")
        or workflow_config.get("stipend", "As per company standards")
    )
    openings = workflow_config.get("openings", 10)
    skills = ", ".join(job_description.get("required_skills", [])[:4])
    eligibility = job_description.get("eligibility", {})
    batch = eligibility.get("batch", "2025/2026 passing out")

    prompt = f"""Personalise this outreach email for a specific college's Placement Officer.

## Target College
- College Name: {college_name}
- City: {college_city}
- TPO Name: {tpo_name}

## Role Details
- Position: {role}
- Openings: {openings}
- Stipend: {stipend}
- Key Skills: {skills}
- Eligible Batch: {batch}

## Base Email Template
Subject: {base_subject}
Body:
{base_body}

## Instructions
Personalise the email for {college_name}. Return JSON:
{{
  "subject": "string — personalised subject line mentioning the college",
  "body": "string — personalised email body (250-350 words) addressing {tpo_name} at {college_name}"
}}

Keep the professional tone. Mention {college_name} naturally in the opening.
Do not change the core information about the role, just personalise the greeting and intro."""

    result = call_llm_json(
        prompt=prompt,
        system=_SYSTEM,
        temperature=0.5,
        max_tokens=800,
    )
    return result


def _update_campaign_college_status(
    db: Session,
    campaign_id: str,
    college_id: str,
    status: CampaignCollegeStatus,
) -> None:
    """Update or create CampaignCollege row with new status."""
    try:
        record = (
            db.query(CampaignCollege)
            .filter(
                CampaignCollege.campaign_id == campaign_id,
                CampaignCollege.college_id == college_id,
            )
            .first()
        )
        if record:
            record.status = status
            if status == CampaignCollegeStatus.contacted:
                record.outreach_sent_at = datetime.utcnow()
        else:
            record = CampaignCollege(
                campaign_id=campaign_id,
                college_id=college_id,
                status=status,
                outreach_sent_at=datetime.utcnow() if status == CampaignCollegeStatus.contacted else None,
            )
            db.add(record)
        db.commit()
    except Exception as e:
        logger.warning(f"[Agent4:Outreach] Failed to update CampaignCollege: {e}")
        db.rollback()
