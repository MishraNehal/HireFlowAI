import { useState, useEffect } from 'react';
import { useHireFlow } from '../context/HireFlowContext';
import { getOfferCandidates, generateOfferLetter, generateOnboarding, getErrorMessage } from '../services/api';
import { SectionHeader, LoadingOverlay, EmptyState } from '../components/UI';

export default function OfferOnboarding() {
  const { approvedJob, goPrev, showToast, resetAll } = useHireFlow();

  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);

  // Per-candidate generated content: { [pipelineId]: { offerLetter, checklist } }
  const [generated, setGenerated] = useState({});
  const [loadingAction, setLoadingAction] = useState(null); // "offer-<id>" | "onboard-<id>"

  useEffect(() => {
    fetchCandidates();
  }, []);

  const fetchCandidates = async () => {
    setLoading(true);
    try {
      const data = await getOfferCandidates(approvedJob?.id || null);
      setCandidates(data);
    } catch (err) {
      showToast('error', 'Failed to load onboarding candidates.');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateOffer = async (pipeline) => {
    const actionKey = `offer-${pipeline.id}`;
    setLoadingAction(actionKey);
    try {
      const payload = {
        candidate_id: pipeline.candidate?.id || pipeline.candidate_id,
        candidate_name: pipeline.candidate?.name || `Candidate #${pipeline.candidate_id}`,
        job_title: pipeline.job?.role_name || 'the assigned role',
        company_name: approvedJob?.company || 'Our Company',
        salary: '',
        start_date: '',
        additional_notes: '',
        job_id: pipeline.job_id,
      };
      const result = await generateOfferLetter(payload);
      const letter = result.offer_letter || result.data?.offer_letter || '';
      setGenerated(prev => ({
        ...prev,
        [pipeline.id]: { ...prev[pipeline.id], offerLetter: letter },
      }));
      setExpandedId(pipeline.id);
      showToast('success', `✅ Offer letter generated for ${payload.candidate_name}!`);
    } catch (err) {
      showToast('error', getErrorMessage(err));
    } finally {
      setLoadingAction(null);
    }
  };

  const handleGenerateOnboarding = async (pipeline) => {
    const actionKey = `onboard-${pipeline.id}`;
    setLoadingAction(actionKey);
    try {
      const payload = {
        candidate_id: pipeline.candidate?.id || pipeline.candidate_id,
        candidate_name: pipeline.candidate?.name || `Candidate #${pipeline.candidate_id}`,
        job_title: pipeline.job?.role_name || 'the assigned role',
        company_name: approvedJob?.company || 'Our Company',
        start_date: '',
        job_id: pipeline.job_id,
      };
      const result = await generateOnboarding(payload);
      const checklist = result.checklist || result.data?.checklist || [];
      setGenerated(prev => ({
        ...prev,
        [pipeline.id]: { ...prev[pipeline.id], checklist },
      }));
      setExpandedId(pipeline.id);
      showToast('success', `✅ Onboarding checklist generated for ${payload.candidate_name}!`);
    } catch (err) {
      showToast('error', getErrorMessage(err));
    } finally {
      setLoadingAction(null);
    }
  };

  const handleCopy = (text) => {
    navigator.clipboard.writeText(text);
    showToast('success', 'Copied to clipboard!');
  };

  if (loading) return <LoadingOverlay message="Loading onboarding candidates..." />;

  return (
    <div>
      <SectionHeader
        icon="🎉"
        title="Offer & Onboarding"
        subtitle="Generate offer letters and onboarding checklists for all approved candidates."
      />

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
        <button className="btn btn-secondary btn-sm" onClick={fetchCandidates}>🔄 Refresh</button>
      </div>

      {candidates.length === 0 ? (
        <div className="card">
          <EmptyState
            icon="📭"
            title="No candidates ready for onboarding"
            subtitle="Candidates appear here after being approved in the Approval Center."
          />
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {candidates.map(pipeline => {
            const cand = pipeline.candidate || {};
            const job = pipeline.job || {};
            const pipeGenerated = generated[pipeline.id] || {};
            const isExpanded = expandedId === pipeline.id;
            const hasOffer = !!pipeGenerated.offerLetter;
            const hasChecklist = pipeGenerated.checklist?.length > 0;

            return (
              <div key={pipeline.id} className="card" style={{ transition: 'all 0.3s' }}>
                {/* ─── Candidate Row ─────────────────────────────────── */}
                <div style={{
                  display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap',
                }}>
                  {/* Avatar */}
                  <div style={{
                    width: 48, height: 48, borderRadius: '50%',
                    background: 'linear-gradient(135deg,#6366f1,#10b981)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '1.25rem', fontWeight: 800, flexShrink: 0,
                    color: '#fff',
                  }}>
                    {cand.name?.[0]?.toUpperCase() || '?'}
                  </div>

                  {/* Info */}
                  <div style={{ flex: 1, minWidth: 160 }}>
                    <div style={{ fontWeight: 700, fontSize: '1rem' }}>
                      {cand.name || `Candidate #${pipeline.candidate_id}`}
                    </div>
                    <div style={{ color: '#94a3b8', fontSize: '0.82rem' }}>
                      {cand.email || '—'}
                    </div>
                    <div style={{ color: '#64748b', fontSize: '0.75rem', marginTop: 2 }}>
                      {job.role_name || 'N/A'} • Pipeline #{pipeline.id}
                    </div>
                  </div>

                  {/* Status badges */}
                  <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{
                      background: 'rgba(16,185,129,0.15)', border: '1px solid rgba(16,185,129,0.3)',
                      color: '#10b981', borderRadius: 999, padding: '0.2rem 0.65rem',
                      fontSize: '0.72rem', fontWeight: 700,
                    }}>
                      ✅ {pipeline.status}
                    </span>
                    {hasOffer && (
                      <span style={{
                        background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.25)',
                        color: '#818cf8', borderRadius: 999, padding: '0.2rem 0.55rem',
                        fontSize: '0.68rem', fontWeight: 600,
                      }}>📄 Offer Ready</span>
                    )}
                    {hasChecklist && (
                      <span style={{
                        background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.25)',
                        color: '#f59e0b', borderRadius: 999, padding: '0.2rem 0.55rem',
                        fontSize: '0.68rem', fontWeight: 600,
                      }}>📋 Checklist Ready</span>
                    )}
                  </div>

                  {/* Action buttons */}
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <button
                      className="btn btn-primary btn-sm"
                      disabled={loadingAction === `offer-${pipeline.id}`}
                      onClick={() => handleGenerateOffer(pipeline)}
                      style={{ whiteSpace: 'nowrap' }}
                    >
                      {loadingAction === `offer-${pipeline.id}` ? '⏳ Generating...' : '📄 Generate Offer'}
                    </button>
                    <button
                      className="btn btn-secondary btn-sm"
                      disabled={loadingAction === `onboard-${pipeline.id}`}
                      onClick={() => handleGenerateOnboarding(pipeline)}
                      style={{ whiteSpace: 'nowrap' }}
                    >
                      {loadingAction === `onboard-${pipeline.id}` ? '⏳ Generating...' : '📋 Onboarding Checklist'}
                    </button>
                    {(hasOffer || hasChecklist) && (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => setExpandedId(isExpanded ? null : pipeline.id)}
                        style={{ minWidth: 36, padding: '0.3rem 0.5rem' }}
                      >
                        {isExpanded ? '▲' : '▼'}
                      </button>
                    )}
                  </div>
                </div>

                {/* ─── Expanded: Generated Content ────────────────────── */}
                {isExpanded && (hasOffer || hasChecklist) && (
                  <div style={{
                    marginTop: '1.25rem', paddingTop: '1rem',
                    borderTop: '1px solid rgba(255,255,255,0.06)',
                  }}>
                    {/* Tab bar */}
                    <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
                      {hasOffer && (
                        <TabButton
                          label="📄 Offer Letter"
                          active={!hasChecklist || true}
                          color="#6366f1"
                        />
                      )}
                    </div>

                    {/* Offer letter */}
                    {hasOffer && (
                      <div style={{ marginBottom: hasChecklist ? '1.5rem' : 0 }}>
                        <div style={{
                          display: 'flex', justifyContent: 'space-between',
                          alignItems: 'center', marginBottom: '0.75rem',
                        }}>
                          <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#818cf8', margin: 0 }}>
                            📄 Offer Letter
                          </h3>
                          <div style={{ display: 'flex', gap: '0.4rem' }}>
                            <button className="btn btn-secondary btn-sm" onClick={() => handleCopy(pipeGenerated.offerLetter)}>
                              📋 Copy
                            </button>
                            <button className="btn btn-secondary btn-sm" onClick={() => window.print()}>
                              🖨️ Print
                            </button>
                            <button className="btn btn-secondary btn-sm" onClick={() => handleGenerateOffer(pipeline)}>
                              🔄 Regenerate
                            </button>
                          </div>
                        </div>
                        <div style={{
                          background: 'rgba(255,255,255,0.03)',
                          border: '1px solid rgba(255,255,255,0.08)',
                          borderRadius: 10, padding: '1.5rem',
                          fontFamily: '"Georgia", serif',
                          fontSize: '0.92rem', lineHeight: 1.75,
                          color: '#e2e8f0', whiteSpace: 'pre-wrap',
                          maxHeight: 500, overflowY: 'auto',
                        }}>
                          {pipeGenerated.offerLetter}
                        </div>
                      </div>
                    )}

                    {/* Onboarding checklist */}
                    {hasChecklist && (
                      <div>
                        <div style={{
                          display: 'flex', justifyContent: 'space-between',
                          alignItems: 'center', marginBottom: '0.75rem',
                        }}>
                          <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: '#34d399', margin: 0 }}>
                            📋 Onboarding Checklist
                          </h3>
                          <button className="btn btn-secondary btn-sm" onClick={() => handleGenerateOnboarding(pipeline)}>
                            🔄 Regenerate
                          </button>
                        </div>
                        {pipeGenerated.checklist.map((section, si) => (
                          <ChecklistSection key={si} section={section} />
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
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


/* ─── Helper Components ──────────────────────────────────────────────────── */

function TabButton({ label, active, color }) {
  return (
    <span style={{
      padding: '0.3rem 0.75rem', borderRadius: 8,
      fontSize: '0.8rem', fontWeight: 600,
      background: active ? `${color}22` : 'transparent',
      color: active ? color : '#94a3b8',
      borderBottom: active ? `2px solid ${color}` : '2px solid transparent',
    }}>
      {label}
    </span>
  );
}


function ChecklistSection({ section }) {
  const [expanded, setExpanded] = useState(true);

  // Support plain string items
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
