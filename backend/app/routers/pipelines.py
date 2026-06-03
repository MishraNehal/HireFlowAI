from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel
from app.database.session import get_db
from app.models.models import InterviewPipeline, InterviewQuestion, CandidateResponse, Candidate
from app.schemas import schemas
from app.services.evaluator import evaluate_candidate_response

router = APIRouter(prefix="/api/pipelines", tags=["Pipelines"])

# --- Custom Request Schemas ---
class AnswerSubmission(BaseModel):
    question_id: int
    answer_text: str

class SubmitAnswersRequest(BaseModel):
    answers: List[AnswerSubmission]

class HRActionRequest(BaseModel):
    passed: bool
    feedback: str


@router.get("", response_model=List[schemas.InterviewPipelineORM])
def list_pipelines(db: Session = Depends(get_db)):
    return db.query(InterviewPipeline).all()

@router.get("/{pipeline_id}", response_model=schemas.InterviewPipelineORM)
def get_pipeline(pipeline_id: int, db: Session = Depends(get_db)):
    pipeline = db.query(InterviewPipeline).filter(InterviewPipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return pipeline

@router.get("/candidate/{candidate_id}", response_model=List[schemas.InterviewPipelineORM])
def get_candidate_pipelines(candidate_id: int, db: Session = Depends(get_db)):
    return db.query(InterviewPipeline).filter(InterviewPipeline.candidate_id == candidate_id).all()

@router.get("/{pipeline_id}/questions", response_model=List[schemas.InterviewQuestionORM])
def get_pipeline_questions(pipeline_id: int, db: Session = Depends(get_db)):
    pipeline = db.query(InterviewPipeline).filter(InterviewPipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    # Questions are attached to the job description
    questions = db.query(InterviewQuestion).filter(InterviewQuestion.job_id == pipeline.job_id).all()
    return questions

@router.post("/{pipeline_id}/submit-answers")
def submit_interview_answers(
    pipeline_id: int, 
    payload: SubmitAnswersRequest, 
    db: Session = Depends(get_db)
):
    pipeline = db.query(InterviewPipeline).filter(InterviewPipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if pipeline.status == "Rejected":
        raise HTTPException(status_code=400, detail="Cannot submit answers for a rejected candidate.")

    responses_evaluated = []
    total_score = 0.0
    count = 0

    # Clean old responses for this candidate/job if they exist to allow re-takes
    db.query(CandidateResponse).filter(
        CandidateResponse.candidate_id == pipeline.candidate_id,
        CandidateResponse.question_id.in_([ans.question_id for ans in payload.answers])
    ).delete(synchronize_session=False)
    db.commit()

    for ans in payload.answers:
        question = db.query(InterviewQuestion).filter(InterviewQuestion.id == ans.question_id).first()
        if not question:
            continue
        
        # Call LLM grader
        grading = evaluate_candidate_response(
            question_text=question.question_text,
            expected_answer=question.expected_answer or "",
            eval_rubric=question.eval_rubric or [],
            candidate_answer=ans.answer_text
        )

        score = grading.get("score", 0.0)
        feedback = grading.get("feedback", "")

        db_resp = CandidateResponse(
            candidate_id=pipeline.candidate_id,
            question_id=ans.question_id,
            answer_text=ans.answer_text,
            score=score,
            feedback=feedback
        )
        db.add(db_resp)
        db.commit()
        db.refresh(db_resp)

        responses_evaluated.append({
            "question_id": ans.question_id,
            "score": score,
            "feedback": feedback
        })
        total_score += score
        count += 1

    # Update pipeline stage and status based on performance
    avg_score = (total_score / count) if count > 0 else 0.0
    interview_passed = avg_score >= 3.0 # Passing score threshold is 3.0 out of 5.0

    pipeline.interview_passed = interview_passed
    pipeline.interview_gate_feedback = (
        f"Interview finished. Average Score: {avg_score:.2f}/5.0. "
        f"{'Passed to HR round.' if interview_passed else 'Did not meet technical bar.'}"
    )

    if interview_passed:
        pipeline.status = "HR"
        pipeline.current_gate = "HR_Gate"
    else:
        pipeline.status = "Rejected"
        # Keep gate as Interview_AI to show where they failed

    db.commit()
    db.refresh(pipeline)

    return {
        "pipeline": {
            "id": pipeline.id,
            "status": pipeline.status,
            "current_gate": pipeline.current_gate,
            "interview_passed": pipeline.interview_passed,
            "interview_gate_feedback": pipeline.interview_gate_feedback
        },
        "scores": responses_evaluated,
        "average_score": avg_score
    }

@router.post("/{pipeline_id}/hr-action", response_model=schemas.InterviewPipelineORM)
def resolve_hr_gate(
    pipeline_id: int, 
    payload: HRActionRequest, 
    db: Session = Depends(get_db)
):
    pipeline = db.query(InterviewPipeline).filter(InterviewPipeline.id == pipeline_id).first()
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    if pipeline.status != "HR":
        raise HTTPException(status_code=400, detail="Pipeline is not in the HR gate.")

    pipeline.hr_passed = payload.passed
    pipeline.hr_gate_feedback = payload.feedback
    
    if payload.passed:
        pipeline.status = "Offered"
    else:
        pipeline.status = "Rejected"

    db.commit()
    db.refresh(pipeline)
    return pipeline
