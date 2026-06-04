import sys, os
sys.path.insert(0, r'd:\Projects\HireFlowAI\backend')
os.chdir(r'd:\Projects\HireFlowAI\backend')

from app.database.session import SessionLocal
from app.models.models import Candidate, CandidateScore, JobDescription, InterviewPipeline
from app.services.parser import parse_resume
from app.services.evaluator import evaluate_resume

db = SessionLocal()
try:
    # Clear all old flat scores and pipelines
    db.query(CandidateScore).delete()
    db.query(InterviewPipeline).delete()
    db.commit()
    print("Cleared old scores.")

    job = db.query(JobDescription).filter(JobDescription.id == 1).first()
    print(f"Evaluating for JD: {job.role_name} | skills: {job.skills_required}")
    print()

    for cand in db.query(Candidate).all():
        if not cand.resume_path or not os.path.exists(cand.resume_path):
            print(f"  SKIP {cand.name} - resume file missing")
            continue
        try:
            parsed = parse_resume(cand.resume_path)
            resume_text = parsed.get("resume_text", "")
        except Exception as e:
            print(f"  SKIP {cand.name} - parse error: {e}")
            continue

        ev = evaluate_resume(
            resume_text=resume_text,
            jd_role=job.role_name,
            jd_skills=job.skills_required,
            jd_responsibilities=job.responsibilities or ""
        )

        score = CandidateScore(
            candidate_id=cand.id,
            job_id=job.id,
            total_score=ev["total_score"],
            skills_score=ev["skills_score"],
            experience_score=ev["experience_score"],
            projects_score=ev["projects_score"],
            jd_match_score=ev["jd_match_score"],
            breakdown_notes=ev["breakdown_notes"]
        )
        db.add(score)

        passed = ev["total_score"] >= 60.0
        pipeline = InterviewPipeline(
            candidate_id=cand.id,
            job_id=job.id,
            status="Interviewing" if passed else "Rejected",
            current_gate="Interview_AI" if passed else "Screening_AI",
            screening_passed=passed,
            screening_gate_feedback=ev["breakdown_notes"]
        )
        db.add(pipeline)
        db.commit()

        status = "PASS" if passed else "FAIL"
        total = ev["total_score"]
        skills = ev["skills_score"]
        exp = ev["experience_score"]
        jd = ev["jd_match_score"]
        notes = ev["breakdown_notes"][:100]
        print(f"  [{status}] {cand.name:<25} total={total:5.1f}  skills={skills:5.1f}  exp={exp:5.1f}  jd={jd:5.1f}")
        print(f"         {notes}")
finally:
    db.close()
