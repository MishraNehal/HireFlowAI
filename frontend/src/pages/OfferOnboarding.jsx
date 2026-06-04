import { useState, useEffect } from 'react';
import { useHireFlow } from '../context/HireFlowContext';
import { generateOfferLetter, generateOnboarding, getErrorMessage } from '../services/api';
import { SectionHeader, LoadingOverlay, EmptyState } from '../components/UI';

export default function OfferOnboarding() {
  const {
    approvedJob,
    selectedCandidate,
    offerLetter, setOfferLetter,
    onboardingChecklist, setOnboardingChecklist,
    goPrev, showToast, resetAll,
  } = useHireFlow();

  const [loadingOffer, setLoadingOffer] = useState(false);
  const [loadingOnboarding, setLoadingOnboarding] = useState(false);
  const [offerGenerated, setOfferGenerated] = useState(false);
  const [onboardingGenerated, setOnboardingGenerated] = useState(false);
  const [activeTab, setActiveTab] = useState('offer'); // 'offer' | 'onboarding'

  // Pre-fill form with candidate data if available
  const [offerForm, setOfferForm] = useState({
    candidate_name: selectedCandidate?.name || '',
    candidate_email: selectedCandidate?.email || '',
    job_title: approvedJob?.title || '',
    company_name: approvedJob?.company || '',
    salary: '',
    start_date: '',
    additional_notes: '',
  });

  useEffect(() => {
    if (selectedCandidate) {
      setOfferForm(prev => ({
        ...prev,
        candidate_name: selectedCandidate.name || prev.candidate_name,
        candidate_email: selectedCandidate.email || prev.candidate_email,
      }));
    }
    if (approvedJob) {
      setOfferForm(prev => ({
        ...prev,
        job_title: approvedJob.title || prev.job_title,
        company_name: approvedJob.company || prev.company_name,
      }));
    }
  }, [selectedCandidate, approvedJob]);

  const handleGenerateOffer = async () => {
    if (!offerForm.candidate_name || !offerForm.job_title || !offerForm.company_name) {
      return showToast('error', 'Candidate name, job title, and company are required.');
    }
    setLoadingOffer(true);
    try {
      const payload = {
        candidate_name: offerForm.candidate_name,
        candidate_email: offerForm.candidate_email,
        job_title: offerForm.job_title,
        company_name: offerForm.company_name,
        salary: offerForm.salary,
        start_date: offerForm.start_date,
        additional_notes: offerForm.additional_notes,
        job_id: approvedJob?.id,
      };
      const result = await generateOfferLetter(payload);
      setOfferLetter(result.offer_letter || result.data?.offer_letter || '');
      setOfferGenerated(true);
      setActiveTab('offer');
      showToast('success', '✅ Offer letter generated successfully!');
    } catch (err) {
      showToast('error', getErrorMessage(err));
    } finally {
      setLoadingOffer(false);
    }
  };

  const handleGenerateOnboarding = async () => {
    setLoadingOnboarding(true);
    try {
      const payload = {
        candidate_name: offerForm.candidate_name,
        job_title: offerForm.job_title,
        company_name: offerForm.company_name,
        start_date: offerForm.start_date,
        job_id: approvedJob?.id,
      };
      const result = await generateOnboarding(payload);
      const checklist = result.checklist || result.data?.checklist || [];
      setOnboardingChecklist(checklist);
      setOnboardingGenerated(true);
      setActiveTab('onboarding');
      showToast('success', '✅ Onboarding checklist generated!');
    } catch (err) {
      showToast('error', getErrorMessage(err));
    } finally {
      setLoadingOnboarding(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const handleCopyOffer = () => {
    navigator.clipboard.writeText(offerLetter);
    showToast('success', 'Offer letter copied to clipboard!');
  };

  if (loadingOffer) return <LoadingOverlay message="Drafting offer letter with AI..." />;
  if (loadingOnboarding) return <LoadingOverlay message="Building onboarding checklist..." />;

  return (
    <div>
      <SectionHeader
        icon="🎉"
        title="Offer & Onboarding"
        subtitle="Generate a formal offer letter and structured onboarding checklist for the selected candidate."
      />

      {/* Candidate Info Banner */}
      {selectedCandidate && (
        <div style={{
          background: 'linear-gradient(135deg, rgba(99,102,241,0.1), rgba(16,185,129,0.1))',
          border: '1px solid rgba(99,102,241,0.25)',
          borderRadius: 12,
          padding: '1rem 1.25rem',
          marginBottom: '1.5rem',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem',
          flexWrap: 'wrap',
        }}>
          <div style={{
            width: 44, height: 44, borderRadius: '50%',
            background: 'linear-gradient(135deg,#6366f1,#10b981)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '1.2rem', fontWeight: 800,
          }}>
            {selectedCandidate.name?.[0]?.toUpperCase() || '?'}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: '1rem' }}>{selectedCandidate.name}</div>
            <div style={{ color: '#94a3b8', fontSize: '0.85rem' }}>{selectedCandidate.email}</div>
          </div>
          <span style={{
            background: 'rgba(16,185,129,0.15)', border: '1px solid rgba(16,185,129,0.3)',
            color: '#10b981', borderRadius: 999, padding: '0.25rem 0.75rem',
            fontSize: '0.8rem', fontWeight: 700,
          }}>🎉 Offer Extended</span>
        </div>
      )}

      {/* Offer Details Form */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '1.25rem', color: '#e2e8f0' }}>
          📝 Offer Details
        </h2>
        <div className="form-grid">
          <div className="form-group">
            <label className="form-label">Candidate Name *</label>
            <input className="form-input" placeholder="Full name"
              value={offerForm.candidate_name}
              onChange={e => setOfferForm(p => ({ ...p, candidate_name: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Candidate Email</label>
            <input className="form-input" type="email" placeholder="email@example.com"
              value={offerForm.candidate_email}
              onChange={e => setOfferForm(p => ({ ...p, candidate_email: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Job Title *</label>
            <input className="form-input" placeholder="e.g. Python Intern"
              value={offerForm.job_title}
              onChange={e => setOfferForm(p => ({ ...p, job_title: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Company Name *</label>
            <input className="form-input" placeholder="e.g. ABC Technologies"
              value={offerForm.company_name}
              onChange={e => setOfferForm(p => ({ ...p, company_name: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Salary / Stipend</label>
            <input className="form-input" placeholder="e.g. ₹25,000/month"
              value={offerForm.salary}
              onChange={e => setOfferForm(p => ({ ...p, salary: e.target.value }))} />
          </div>
          <div className="form-group">
            <label className="form-label">Start Date</label>
            <input className="form-input" type="date"
              value={offerForm.start_date}
              onChange={e => setOfferForm(p => ({ ...p, start_date: e.target.value }))} />
          </div>
        </div>
        <div className="form-group">
          <label className="form-label">Additional Notes (Optional)</label>
          <textarea className="form-textarea" rows={2}
            placeholder="Any extra clauses, perks, or notes to include in the letter..."
            value={offerForm.additional_notes}
            onChange={e => setOfferForm(p => ({ ...p, additional_notes: e.target.value }))} />
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginTop: '1rem' }}>
          <button className="btn btn-primary" onClick={handleGenerateOffer}>
            📄 Generate Offer Letter
          </button>
          <button className="btn btn-secondary" onClick={handleGenerateOnboarding}>
            📋 Generate Onboarding Checklist
          </button>
        </div>
      </div>

      {/* Output Tabs */}
      {(offerGenerated || onboardingGenerated) && (
        <div className="card">
          {/* Tab Header */}
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '0.75rem' }}>
            {offerGenerated && (
              <button
                onClick={() => setActiveTab('offer')}
                style={{
                  padding: '0.4rem 1rem', borderRadius: 8, border: 'none', cursor: 'pointer',
                  fontWeight: 600, fontSize: '0.875rem',
                  background: activeTab === 'offer' ? 'rgba(99,102,241,0.2)' : 'transparent',
                  color: activeTab === 'offer' ? '#818cf8' : '#94a3b8',
                  borderBottom: activeTab === 'offer' ? '2px solid #6366f1' : '2px solid transparent',
                  transition: 'all 0.2s',
                }}
              >
                📄 Offer Letter
              </button>
            )}
            {onboardingGenerated && (
              <button
                onClick={() => setActiveTab('onboarding')}
                style={{
                  padding: '0.4rem 1rem', borderRadius: 8, border: 'none', cursor: 'pointer',
                  fontWeight: 600, fontSize: '0.875rem',
                  background: activeTab === 'onboarding' ? 'rgba(16,185,129,0.2)' : 'transparent',
                  color: activeTab === 'onboarding' ? '#34d399' : '#94a3b8',
                  borderBottom: activeTab === 'onboarding' ? '2px solid #10b981' : '2px solid transparent',
                  transition: 'all 0.2s',
                }}
              >
                📋 Onboarding Checklist
              </button>
            )}
          </div>

          {/* Offer Letter Tab */}
          {activeTab === 'offer' && offerLetter && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginBottom: '1rem' }}>
                <button className="btn btn-secondary btn-sm" onClick={handleCopyOffer}>📋 Copy</button>
                <button className="btn btn-secondary btn-sm" onClick={handlePrint}>🖨️ Print</button>
                <button className="btn btn-secondary btn-sm" onClick={handleGenerateOffer}>🔄 Regenerate</button>
              </div>
              <div style={{
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: 10,
                padding: '2rem',
                fontFamily: '"Georgia", serif',
                fontSize: '0.95rem',
                lineHeight: 1.75,
                color: '#e2e8f0',
                whiteSpace: 'pre-wrap',
                maxHeight: 600,
                overflowY: 'auto',
              }}>
                {offerLetter}
              </div>
            </div>
          )}

          {/* Onboarding Checklist Tab */}
          {activeTab === 'onboarding' && (
            <div>
              {onboardingChecklist.length === 0 ? (
                <EmptyState icon="📋" title="No checklist generated" subtitle="Click 'Generate Onboarding Checklist' above." />
              ) : (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
                    <button className="btn btn-secondary btn-sm" onClick={handleGenerateOnboarding}>🔄 Regenerate</button>
                  </div>
                  {onboardingChecklist.map((section, si) => (
                    <ChecklistSection key={si} section={section} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* No output yet */}
      {!offerGenerated && !onboardingGenerated && (
        <div className="card">
          <EmptyState
            icon="📄"
            title="Nothing generated yet"
            subtitle="Fill in the offer details above and click 'Generate Offer Letter' or 'Generate Onboarding Checklist'."
          />
        </div>
      )}

      {/* Navigation */}
      <div style={{ display: 'flex', gap: '1rem', justifyContent: 'space-between', marginTop: '2rem', flexWrap: 'wrap' }}>
        <button className="btn btn-secondary" onClick={goPrev}>← Back</button>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            className="btn btn-success"
            onClick={() => {
              showToast('success', '🎊 Recruitment process complete! Starting a new cycle...');
              setTimeout(resetAll, 2000);
            }}
          >
            🎊 Complete & Start New
          </button>
        </div>
      </div>
    </div>
  );
}

function ChecklistSection({ section }) {
  const [expanded, setExpanded] = useState(true);

  // Support both object-based sections and plain string arrays
  if (typeof section === 'string') {
    return (
      <div style={{
        display: 'flex', alignItems: 'flex-start', gap: '0.75rem',
        padding: '0.6rem 0', borderBottom: '1px solid rgba(255,255,255,0.06)',
      }}>
        <span style={{ color: '#10b981', marginTop: 2 }}>✓</span>
        <span style={{ color: '#cbd5e1', fontSize: '0.9rem' }}>{section}</span>
      </div>
    );
  }

  const { title, category, items = [] } = section;
  const displayTitle = title || category || 'General';

  return (
    <div style={{ marginBottom: '1.25rem' }}>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex', alignItems: 'center', gap: '0.75rem',
          cursor: 'pointer', padding: '0.6rem 0.75rem',
          background: 'rgba(99,102,241,0.06)', borderRadius: 8,
          marginBottom: expanded ? '0.75rem' : 0,
          userSelect: 'none',
        }}
      >
        <span style={{ color: '#6366f1', fontSize: '1.1rem' }}>{expanded ? '▼' : '▶'}</span>
        <span style={{ fontWeight: 700, fontSize: '0.95rem', color: '#e2e8f0', flex: 1 }}>{displayTitle}</span>
        <span style={{
          background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.3)',
          color: '#818cf8', borderRadius: 999, padding: '0.1rem 0.5rem', fontSize: '0.72rem',
        }}>
          {items.length} tasks
        </span>
      </div>

      {expanded && (
        <div style={{ paddingLeft: '1rem' }}>
          {items.map((item, i) => {
            const label = typeof item === 'string' ? item : item.task || item.label || item;
            const owner = typeof item === 'object' ? item.owner || item.responsible : null;
            const deadline = typeof item === 'object' ? item.deadline || item.due : null;
            return (
              <div key={i} style={{
                display: 'flex', alignItems: 'flex-start', gap: '0.75rem',
                padding: '0.6rem 0.5rem', borderBottom: '1px solid rgba(255,255,255,0.05)',
              }}>
                <span style={{
                  width: 20, height: 20, borderRadius: 4, flexShrink: 0, marginTop: 2,
                  border: '2px solid rgba(99,102,241,0.4)',
                  background: 'rgba(99,102,241,0.05)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '0.65rem', color: '#6366f1',
                }}>
                  {i + 1}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ color: '#cbd5e1', fontSize: '0.88rem', lineHeight: 1.5 }}>{label}</div>
                  {(owner || deadline) && (
                    <div style={{ display: 'flex', gap: '1rem', marginTop: '0.25rem' }}>
                      {owner && <span style={{ color: '#94a3b8', fontSize: '0.75rem' }}>👤 {owner}</span>}
                      {deadline && <span style={{ color: '#94a3b8', fontSize: '0.75rem' }}>📅 {deadline}</span>}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
