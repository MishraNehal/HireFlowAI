from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


# --- Hiring Request ---
class HiringRequestCreate(BaseModel):
    company_name: str
    role_name: str
    skills_required: List[str]
    experience_level: str = "0-2 Years"
    num_openings: int = 1
    additional_context: Optional[str] = None

class HiringRequestORM(HiringRequestCreate):
    id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# --- JD Generation ---
class GenerateJDRequest(BaseModel):
    hiring_request_id: int

class GeneratedJD(BaseModel):
    job_title: str
    company_overview: str
    responsibilities: List[str]
    required_skills: List[str]
    preferred_skills: List[str]
    eligibility_criteria: str
    hiring_process: List[str]
    perks: List[str]


# --- Approval ---
class ApprovalAction(BaseModel):
    approved: bool
    notes: Optional[str] = None


# --- Offer Letter ---
class OfferLetterRequest(BaseModel):
    candidate_id: int
    company_name: str
    start_date: Optional[str] = None
    salary_range: Optional[str] = None


# --- Onboarding ---
class OnboardingRequest(BaseModel):
    candidate_id: int
    company_name: str

# --- Rubric ---
class RubricBase(BaseModel):
    criteria: List[Dict[str, Any]]

class RubricCreate(RubricBase):
    pass

class RubricORM(RubricBase):
    id: int
    job_id: int

    class Config:
        from_attributes = True


# --- Interview Question ---
class InterviewQuestionBase(BaseModel):
    question_text: str
    expected_answer: Optional[str] = None
    eval_rubric: Optional[List[Dict[str, Any]]] = None

class InterviewQuestionCreate(InterviewQuestionBase):
    pass

class InterviewQuestionORM(InterviewQuestionBase):
    id: int
    job_id: int

    class Config:
        from_attributes = True


# --- Job Description ---
class JobDescriptionBase(BaseModel):
    role_name: str
    skills_required: List[str]
    min_experience: int = 0
    responsibilities: Optional[str] = None
    status: str = "Draft"

class JobDescriptionCreate(JobDescriptionBase):
    pass

class JobDescriptionUpdate(BaseModel):
    role_name: Optional[str] = None
    skills_required: Optional[List[str]] = None
    min_experience: Optional[int] = None
    responsibilities: Optional[str] = None
    status: Optional[str] = None

class JobDescriptionORM(JobDescriptionBase):
    id: int
    created_at: datetime
    rubrics: List[RubricORM] = []
    questions: List[InterviewQuestionORM] = []

    class Config:
        from_attributes = True


# --- Candidate ---
class CandidateBase(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    parsed_skills: Optional[List[str]] = []
    experience_years: float = 0.0
    resume_path: Optional[str] = None

class CandidateCreate(CandidateBase):
    pass

class CandidateORM(CandidateBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Candidate Score ---
class CandidateScoreBase(BaseModel):
    candidate_id: int
    job_id: int
    total_score: float
    skills_score: float
    experience_score: float
    projects_score: float
    jd_match_score: float
    breakdown_notes: Optional[str] = None

class CandidateScoreORM(CandidateScoreBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Candidate Response ---
class CandidateResponseBase(BaseModel):
    answer_text: str

class CandidateResponseCreate(CandidateResponseBase):
    question_id: int
    candidate_id: int

class CandidateResponseORM(CandidateResponseBase):
    id: int
    candidate_id: int
    question_id: int
    score: float
    feedback: Optional[str] = None

    class Config:
        from_attributes = True


# --- Interview Pipeline ---
class InterviewPipelineBase(BaseModel):
    candidate_id: int
    job_id: int
    status: str = "Screening"
    current_gate: str = "Screening_AI"
    screening_passed: Optional[bool] = None
    screening_gate_feedback: Optional[str] = None
    interview_passed: Optional[bool] = None
    interview_gate_feedback: Optional[str] = None
    hr_passed: Optional[bool] = None
    hr_gate_feedback: Optional[str] = None

class InterviewPipelineUpdate(BaseModel):
    status: Optional[str] = None
    current_gate: Optional[str] = None
    screening_passed: Optional[bool] = None
    screening_gate_feedback: Optional[str] = None
    interview_passed: Optional[bool] = None
    interview_gate_feedback: Optional[str] = None
    hr_passed: Optional[bool] = None
    hr_gate_feedback: Optional[str] = None

class InterviewPipelineORM(InterviewPipelineBase):
    id: int
    last_updated: datetime
    candidate: CandidateORM
    job: JobDescriptionORM

    class Config:
        from_attributes = True


# --- Enveloped Response Wrapper ---
class EnvelopedResponse(BaseModel):
    status: str = "success"
    data: Any
    message: Optional[str] = None
