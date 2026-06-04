from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.session import Base


class HiringRequest(Base):
    __tablename__ = "hiring_requests"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    role_name = Column(String, nullable=False, index=True)
    skills_required = Column(JSON, nullable=False)   # list of strings
    experience_level = Column(String, nullable=True)  # e.g. "0-1 Years"
    num_openings = Column(Integer, default=1)
    additional_context = Column(Text, nullable=True)
    status = Column(String, default="Pending")  # Pending, JD Generated, Approved
    created_at = Column(DateTime, default=datetime.utcnow)

class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id = Column(Integer, primary_key=True, index=True)
    role_name = Column(String, index=True)
    skills_required = Column(JSON, nullable=False)  # list of strings
    min_experience = Column(Integer, default=0)
    responsibilities = Column(Text, nullable=True)
    status = Column(String, default="Draft")  # Draft, Approved
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    candidates_scored = relationship("CandidateScore", back_populates="job")
    pipelines = relationship("InterviewPipeline", back_populates="job")
    rubrics = relationship("Rubric", back_populates="job", cascade="all, delete-orphan")
    questions = relationship("InterviewQuestion", back_populates="job", cascade="all, delete-orphan")


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String, nullable=True)
    parsed_skills = Column(JSON, nullable=True)  # list of strings
    experience_years = Column(Float, default=0.0)
    resume_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    scores = relationship("CandidateScore", back_populates="candidate", cascade="all, delete-orphan")
    pipelines = relationship("InterviewPipeline", back_populates="candidate", cascade="all, delete-orphan")
    responses = relationship("CandidateResponse", back_populates="candidate", cascade="all, delete-orphan")


class CandidateScore(Base):
    __tablename__ = "candidate_scores"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("job_descriptions.id"), nullable=False)
    total_score = Column(Float, default=0.0)
    skills_score = Column(Float, default=0.0)
    experience_score = Column(Float, default=0.0)
    projects_score = Column(Float, default=0.0)
    jd_match_score = Column(Float, default=0.0)
    breakdown_notes = Column(Text, nullable=True)  # Detailed evaluation text
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    candidate = relationship("Candidate", back_populates="scores")
    job = relationship("JobDescription", back_populates="candidates_scored")


class InterviewPipeline(Base):
    __tablename__ = "interview_pipelines"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("job_descriptions.id"), nullable=False)
    status = Column(String, default="Screening")  # Screening, Interviewing, Shortlisted, Rejected
    current_gate = Column(String, default="Screening_AI")  # Screening_AI, Interview_AI, Approval_HR
    
    screening_passed = Column(Boolean, nullable=True)
    screening_gate_feedback = Column(Text, nullable=True)
    
    interview_passed = Column(Boolean, nullable=True)
    interview_gate_feedback = Column(Text, nullable=True)
    
    hr_passed = Column(Boolean, nullable=True)
    hr_gate_feedback = Column(Text, nullable=True)
    
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    candidate = relationship("Candidate", back_populates="pipelines")
    job = relationship("JobDescription", back_populates="pipelines")


class Rubric(Base):
    __tablename__ = "rubrics"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("job_descriptions.id"), nullable=False)
    criteria = Column(JSON, nullable=False)  # list of objects containing name, weight, scale description

    # Relationships
    job = relationship("JobDescription", back_populates="rubrics")


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("job_descriptions.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    expected_answer = Column(Text, nullable=True)
    eval_rubric = Column(JSON, nullable=True)  # Criteria specific to this question

    # Relationships
    job = relationship("JobDescription", back_populates="questions")
    responses = relationship("CandidateResponse", back_populates="question", cascade="all, delete-orphan")


class CandidateResponse(Base):
    __tablename__ = "candidate_responses"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("interview_questions.id"), nullable=False)
    answer_text = Column(Text, nullable=False)
    score = Column(Float, default=0.0)
    feedback = Column(Text, nullable=True)

    # Relationships
    candidate = relationship("Candidate", back_populates="responses")
    question = relationship("InterviewQuestion", back_populates="responses")
