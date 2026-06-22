"""Initial schema

Revision ID: 0001
Revises: 
Create Date: 2025-01-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop all enums first if they exist
    op.execute("DROP TYPE IF EXISTS userrole CASCADE")
    op.execute("DROP TYPE IF EXISTS workmode CASCADE")
    op.execute("DROP TYPE IF EXISTS campaignstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS candidatestatus CASCADE")
    op.execute("DROP TYPE IF EXISTS roundstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS interviewmode CASCADE")
    op.execute("DROP TYPE IF EXISTS parsestatus CASCADE")
    op.execute("DROP TYPE IF EXISTS scorerecommendation CASCADE")
    op.execute("DROP TYPE IF EXISTS offerstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS doctype CASCADE")
    op.execute("DROP TYPE IF EXISTS docstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS checkpointstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS approvaldecision CASCADE")
    op.execute("DROP TYPE IF EXISTS collegetier CASCADE")
    op.execute("DROP TYPE IF EXISTS campaigncollegestatus CASCADE")
    op.execute("DROP TYPE IF EXISTS emailstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS recipienttype CASCADE")
    op.execute("DROP TYPE IF EXISTS knowledgedoctype CASCADE")
    op.execute("DROP TYPE IF EXISTS knowledgesource CASCADE")
    op.execute("DROP TYPE IF EXISTS evaluatedby CASCADE")
    op.execute("DROP TYPE IF EXISTS interviewstatus CASCADE")
    op.execute("DROP TYPE IF EXISTS interviewrecommendation CASCADE")

    # Drop all tables if they exist
    op.execute("DROP TABLE IF EXISTS approval_records CASCADE")
    op.execute("DROP TABLE IF EXISTS onboarding_documents CASCADE")
    op.execute("DROP TABLE IF EXISTS offers CASCADE")
    op.execute("DROP TABLE IF EXISTS emotion_snapshots CASCADE")
    op.execute("DROP TABLE IF EXISTS interview_evaluations CASCADE")
    op.execute("DROP TABLE IF EXISTS interview_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS assessment_results CASCADE")
    op.execute("DROP TABLE IF EXISTS scores CASCADE")
    op.execute("DROP TABLE IF EXISTS candidate_profiles CASCADE")
    op.execute("DROP TABLE IF EXISTS resumes CASCADE")
    op.execute("DROP TABLE IF EXISTS candidates CASCADE")
    op.execute("DROP TABLE IF EXISTS campaign_colleges CASCADE")
    op.execute("DROP TABLE IF EXISTS colleges CASCADE")
    op.execute("DROP TABLE IF EXISTS checkpoints CASCADE")
    op.execute("DROP TABLE IF EXISTS campaign_rounds CASCADE")
    op.execute("DROP TABLE IF EXISTS campaign_workflow_config CASCADE")
    op.execute("DROP TABLE IF EXISTS campaigns CASCADE")
    op.execute("DROP TABLE IF EXISTS email_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS knowledge_base CASCADE")
    op.execute("DROP TABLE IF EXISTS company_users CASCADE")
    op.execute("DROP TABLE IF EXISTS companies CASCADE")
    op.execute("DROP TABLE IF EXISTS alembic_version CASCADE")

    # Enable pgvector
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create companies table
    op.create_table(
        'companies',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('industry', sa.String(100), nullable=True),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('clerk_org_id', sa.String(255), nullable=True, unique=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create company_users table
    op.execute("""
        CREATE TYPE userrole AS ENUM ('admin', 'hr', 'recruiter', 'viewer')
    """)
    op.create_table(
        'company_users',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('clerk_user_id', sa.String(255), nullable=False),
        sa.Column('role', postgresql.ENUM('admin', 'hr', 'recruiter', 'viewer',
                                   name='userrole', create_type=False), nullable=False,
                  server_default='hr'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create campaigns table
    op.execute("""
        CREATE TYPE workmode AS ENUM ('remote', 'hybrid', 'onsite')
    """)
    op.execute("""
        CREATE TYPE campaignstatus AS ENUM
        ('draft', 'active', 'paused', 'completed', 'cancelled')
    """)
    op.create_table(
        'campaigns',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('role', sa.String(255), nullable=False),
        sa.Column('batch_year', sa.Integer(), nullable=True),
        sa.Column('openings', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('skills_required', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('skills_preferred', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('stipend', sa.String(100), nullable=True),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('work_mode', postgresql.ENUM('remote', 'hybrid', 'onsite',
                                        name='workmode', create_type=False), nullable=True),
        sa.Column('status', postgresql.ENUM('draft', 'active', 'paused',
                                     'completed', 'cancelled',
                                     name='campaignstatus', create_type=False),
                  nullable=False, server_default='draft'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create campaign_workflow_config
    op.create_table(
        'campaign_workflow_config',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('rounds_selected', postgresql.JSONB(), nullable=True),
        sa.Column('approval_gates', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create campaign_rounds 
    op.execute("""
        CREATE TYPE roundstatus AS ENUM
        ('pending', 'active', 'completed', 'skipped')
    """)
    op.execute("""
        CREATE TYPE interviewmode AS ENUM
        ('ai_only', 'human_only', 'ai_and_human')
    """)
    op.create_table(
        'campaign_rounds',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('round_order', sa.Integer(), nullable=False),
        sa.Column('round_type', sa.String(100), nullable=False),
        sa.Column('round_name', sa.String(255), nullable=True),
        sa.Column('interview_mode', postgresql.ENUM('ai_only', 'human_only',
                                             'ai_and_human',
                                             name='interviewmode', create_type=False),
                  nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'active', 'completed',
                                     'skipped', name='roundstatus', create_type=False),
                  nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create colleges
    op.execute("""
        CREATE TYPE collegetier AS ENUM ('tier1', 'tier2', 'tier3')
    """)
    op.create_table(
        'colleges',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('state', sa.String(100), nullable=True),
        sa.Column('tier', postgresql.ENUM('tier1', 'tier2', 'tier3',
                                   name='collegetier', create_type=False), nullable=True),
        sa.Column('placement_email', sa.String(255), nullable=True),
        sa.Column('tpo_name', sa.String(255), nullable=True),
        sa.Column('tpo_contact', sa.String(50), nullable=True),
        sa.Column('historical_rating', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create campaign_colleges
    op.execute("""
        CREATE TYPE campaigncollegestatus AS ENUM
        ('recommended','approved','contacted','confirmed','declined','removed')
    """)
    op.create_table(
        'campaign_colleges',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('college_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('colleges.id'), nullable=False),
        sa.Column('status', postgresql.ENUM('recommended', 'approved', 'contacted',
                                     'confirmed', 'declined', 'removed',
                                     name='campaigncollegestatus', create_type=False),
                  nullable=False, server_default='recommended'),
        sa.Column('outreach_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('students_registered', sa.Integer(), server_default='0'),
    )

    # Create checkpoints
    op.execute("""
        CREATE TYPE checkpointstatus AS ENUM
        ('pending','approved','rejected','revision_requested','rolled_back')
    """)
    op.create_table(
        'checkpoints',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('stage_name', sa.String(255), nullable=False),
        sa.Column('stage_order', sa.Integer(), nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'approved', 'rejected',
                                     'revision_requested', 'rolled_back',
                                     name='checkpointstatus', create_type=False),
                  nullable=False, server_default='pending'),
        sa.Column('state_snapshot', postgresql.JSONB(), nullable=True),
        sa.Column('hr_notes', sa.Text(), nullable=True),
        sa.Column('decided_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create candidates
    op.execute("""
        CREATE TYPE candidatestatus AS ENUM
        ('registered','screened','shortlisted','assessment_pending',
         'assessment_done','interview_scheduled','interview_done',
         'selected','rejected','on_hold','offer_sent','offer_accepted',
         'offer_declined','onboarding')
    """)
    op.create_table(
        'candidates',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('college_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('colleges.id'), nullable=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(20), nullable=True),
        sa.Column('batch_year', sa.Integer(), nullable=True),
        sa.Column('current_cgpa', sa.Float(), nullable=True),
        sa.Column('status', postgresql.ENUM(
            'registered', 'screened', 'shortlisted',
            'assessment_pending', 'assessment_done',
            'interview_scheduled', 'interview_done',
            'selected', 'rejected', 'on_hold',
            'offer_sent', 'offer_accepted',
            'offer_declined', 'onboarding',
            name='candidatestatus', create_type=False),
            nullable=False, server_default='registered'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create resumes
    op.execute("""
        CREATE TYPE parsestatus AS ENUM ('pending', 'parsed', 'failed')
    """)
    op.create_table(
        'resumes',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('file_url', sa.String(500), nullable=True),
        sa.Column('file_name', sa.String(255), nullable=True),
        sa.Column('file_size_kb', sa.Integer(), nullable=True),
        sa.Column('parse_status', postgresql.ENUM('pending', 'parsed', 'failed',
                                           name='parsestatus', create_type=False),
                  nullable=False, server_default='pending'),
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('parsed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create candidate_profiles
    op.create_table(
        'candidate_profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('skills', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('projects', postgresql.JSONB(), nullable=True),
        sa.Column('experience', postgresql.JSONB(), nullable=True),
        sa.Column('education', postgresql.JSONB(), nullable=True),
        sa.Column('certifications', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create scores
    op.execute("""
        CREATE TYPE scorerecommendation AS ENUM
        ('strong_match', 'moderate_match', 'weak_match')
    """)
    op.create_table(
        'scores',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('skills_score', sa.Float(), nullable=True),
        sa.Column('project_score', sa.Float(), nullable=True),
        sa.Column('experience_score', sa.Float(), nullable=True),
        sa.Column('education_score', sa.Float(), nullable=True),
        sa.Column('total_score', sa.Float(), nullable=True),
        sa.Column('strengths', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('gaps', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('recommendation', postgresql.ENUM('strong_match', 'moderate_match',
                                             'weak_match',
                                             name='scorerecommendation', create_type=False),
                  nullable=True),
        sa.Column('is_overridden', sa.Boolean(), server_default='false'),
        sa.Column('override_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('override_notes', sa.Text(), nullable=True),
        sa.Column('scored_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create assessment_results
    op.create_table(
        'assessment_results',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('round_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaign_rounds.id'), nullable=True),
        sa.Column('mcq_score', sa.Float(), nullable=True),
        sa.Column('coding_score', sa.Float(), nullable=True),
        sa.Column('written_score', sa.Float(), nullable=True),
        sa.Column('total_score', sa.Float(), nullable=True),
        sa.Column('time_taken_mins', sa.Integer(), nullable=True),
        sa.Column('submission_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('auto_evaluated', sa.Boolean(), server_default='false'),
        sa.Column('evaluation_notes', sa.Text(), nullable=True),
    )

    # Create interview_sessions
    op.execute("""
        CREATE TYPE interviewstatus AS ENUM
        ('scheduled','started','completed','no_show','cancelled')
    """)
    op.create_table(
        'interview_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('round_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaign_rounds.id'), nullable=True),
        sa.Column('interview_mode', postgresql.ENUM('ai_only', 'human_only',
                                             'ai_and_human',
                                             name='interviewmode', create_type=False),
                  nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_mins', sa.Integer(), nullable=True),
        sa.Column('daily_room_url', sa.String(500), nullable=True),
        sa.Column('recording_url', sa.String(500), nullable=True),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('status', postgresql.ENUM('scheduled', 'started', 'completed',
                                     'no_show', 'cancelled',
                                     name='interviewstatus', create_type=False),
                  nullable=False, server_default='scheduled'),
    )

    # Create interview_evaluations
    op.execute("""
        CREATE TYPE evaluatedby AS ENUM ('ai', 'human', 'both')
    """)
    op.execute("""
        CREATE TYPE interviewrecommendation AS ENUM ('hire', 'hold', 'reject')
    """)
    op.create_table(
        'interview_evaluations',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('interview_sessions.id'), nullable=False),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('technical_score', sa.Float(), nullable=True),
        sa.Column('communication_score', sa.Float(), nullable=True),
        sa.Column('problem_solving', sa.Float(), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('behavioral_score', sa.Float(), nullable=True),
        sa.Column('overall_score', sa.Float(), nullable=True),
        sa.Column('strengths', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('concerns', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('recommendation', postgresql.ENUM('hire', 'hold', 'reject',
                                             name='interviewrecommendation', create_type=False),
                  nullable=True),
        sa.Column('evaluated_by', postgresql.ENUM('ai', 'human', 'both',
                                           name='evaluatedby', create_type=False), nullable=True),
        sa.Column('ai_reasoning', sa.Text(), nullable=True),
        sa.Column('hr_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create emotion_snapshots
    op.create_table(
        'emotion_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('interview_sessions.id'), nullable=False),
        sa.Column('timestamp_ms', sa.Integer(), nullable=True),
        sa.Column('happy', sa.Float(), nullable=True),
        sa.Column('neutral', sa.Float(), nullable=True),
        sa.Column('surprised', sa.Float(), nullable=True),
        sa.Column('sad', sa.Float(), nullable=True),
        sa.Column('angry', sa.Float(), nullable=True),
        sa.Column('fearful', sa.Float(), nullable=True),
        sa.Column('disgusted', sa.Float(), nullable=True),
        sa.Column('attention', sa.Float(), nullable=True),
        sa.Column('valence', sa.Float(), nullable=True),
        sa.Column('arousal', sa.Float(), nullable=True),
        sa.Column('eye_contact', sa.Boolean(), nullable=True),
        sa.Column('face_present', sa.Boolean(), nullable=True),
        sa.Column('multiple_faces', sa.Boolean(), nullable=True),
    )

    # Create email_logs
    op.execute("""
        CREATE TYPE emailstatus AS ENUM
        ('pending', 'sent', 'failed', 'bounced')
    """)
    op.execute("""
        CREATE TYPE recipienttype AS ENUM ('college', 'candidate')
    """)
    op.create_table(
        'email_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaigns.id'), nullable=True),
        sa.Column('recipient_email', sa.String(255), nullable=False),
        sa.Column('recipient_type', postgresql.ENUM('college', 'candidate',
                                             name='recipienttype', create_type=False), nullable=True),
        sa.Column('email_type', sa.String(100), nullable=True),
        sa.Column('subject', sa.Text(), nullable=True),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'sent', 'failed', 'bounced',
                                     name='emailstatus', create_type=False),
                  nullable=False, server_default='pending'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create offers
    op.execute("""
        CREATE TYPE offerstatus AS ENUM
        ('draft','approved','sent','accepted','declined','expired')
    """)
    op.create_table(
        'offers',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('offer_letter_url', sa.String(500), nullable=True),
        sa.Column('stipend_offered', sa.String(100), nullable=True),
        sa.Column('joining_date', sa.Date(), nullable=True),
        sa.Column('status', postgresql.ENUM('draft', 'approved', 'sent',
                                     'accepted', 'declined', 'expired',
                                     name='offerstatus', create_type=False),
                  nullable=False, server_default='draft'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('response_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create onboarding_documents
    op.execute("""
        CREATE TYPE doctype AS ENUM
        ('aadhaar','pan','marksheet','offer_signed',
         'bank_details','photo','other')
    """)
    op.execute("""
        CREATE TYPE docstatus AS ENUM
        ('pending','submitted','verified','rejected')
    """)
    op.create_table(
        'onboarding_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('candidate_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('candidates.id'), nullable=False),
        sa.Column('doc_type', postgresql.ENUM('aadhaar', 'pan', 'marksheet',
                                       'offer_signed', 'bank_details',
                                       'photo', 'other',
                                       name='doctype', create_type=False), nullable=False),
        sa.Column('file_url', sa.String(500), nullable=True),
        sa.Column('status', postgresql.ENUM('pending', 'submitted', 'verified',
                                     'rejected', name='docstatus', create_type=False),
                  nullable=False, server_default='pending'),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verified_by', postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Create knowledge_base
    op.execute("""
        CREATE TYPE knowledgedoctype AS ENUM
        ('past_jd','interview_question','rubric','model_answer',
         'hiring_policy','salary_data','college_performance')
    """)
    op.execute("""
        CREATE TYPE knowledgesource AS ENUM ('synthetic', 'real')
    """)
    op.create_table(
        'knowledge_base',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('doc_type', postgresql.ENUM(
            'past_jd', 'interview_question', 'rubric',
            'model_answer', 'hiring_policy',
            'salary_data', 'college_performance',
            name='knowledgedoctype', create_type=False), nullable=False),
        sa.Column('role_tag', sa.String(100), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source', postgresql.ENUM('synthetic', 'real',
                                     name='knowledgesource', create_type=False),
                  nullable=False, server_default='synthetic'),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )

    # Create approval_records
    op.execute("""
        CREATE TYPE approvaldecision AS ENUM
        ('approved', 'rejected', 'revision_requested')
    """)
    op.create_table(
        'approval_records',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('checkpoint_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('checkpoints.id'), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('stage', sa.String(255), nullable=False),
        sa.Column('decision', postgresql.ENUM('approved', 'rejected',
                                       'revision_requested',
                                       name='approvaldecision', create_type=False),
                  nullable=False),
        sa.Column('previous_checkpoint_id', postgresql.UUID(as_uuid=True),
                  nullable=True),
        sa.Column('hr_notes', sa.Text(), nullable=True),
        sa.Column('decided_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('approval_records')
    op.drop_table('knowledge_base')
    op.drop_table('onboarding_documents')
    op.drop_table('offers')
    op.drop_table('email_logs')
    op.drop_table('emotion_snapshots')
    op.drop_table('interview_evaluations')
    op.drop_table('interview_sessions')
    op.drop_table('assessment_results')
    op.drop_table('scores')
    op.drop_table('candidate_profiles')
    op.drop_table('resumes')
    op.drop_table('candidates')
    op.drop_table('campaign_colleges')
    op.drop_table('checkpoints')
    op.drop_table('campaign_rounds')
    op.drop_table('campaign_workflow_config')
    op.drop_table('campaigns')
    op.drop_table('colleges')
    op.drop_table('email_logs')
    op.drop_table('company_users')
    op.drop_table('companies')