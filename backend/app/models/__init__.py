# Re-export all models so SQLAlchemy's registry sees them on startup
from app.models.company import Company, CompanyUser                   # noqa
from app.models.campaign import (                                      # noqa
    Campaign, CampaignWorkflowConfig, CampaignRound,
    Checkpoint, College, CampaignCollege, EmailLog,
)
from app.models.candidate import (                                     # noqa
    Candidate, Resume, CandidateProfile, Score, AssessmentResult,
)
from app.models.interview import (                                     # noqa
    InterviewSession, InterviewEvaluation, EmotionSnapshot,
)
from app.models.offer import Offer, OnboardingDocument                 # noqa
from app.models.knowledge import KnowledgeBase, ApprovalRecord        # noqa

__all__ = [
    "Company", "CompanyUser",
    "Campaign", "CampaignWorkflowConfig", "CampaignRound",
    "Checkpoint", "College", "CampaignCollege", "EmailLog",
    "Candidate", "Resume", "CandidateProfile", "Score", "AssessmentResult",
    "InterviewSession", "InterviewEvaluation", "EmotionSnapshot",
    "Offer", "OnboardingDocument",
    "KnowledgeBase", "ApprovalRecord",
]
