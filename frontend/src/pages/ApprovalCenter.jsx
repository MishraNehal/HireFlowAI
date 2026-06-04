import { useState, useEffect } from 'react';
import { useHireFlow } from '../context/HireFlowContext';
import { listPipelines, resolveHRGate } from '../services/api';
import { SectionHeader, PipelineBadge, LoadingOverlay, EmptyState, ScoreBadge } from '../components/UI';

export default function ApprovalCenter() {
  const { approvedJob, pipelines, setPipelines, setSelectedCandidate, goNext, goPrev, showToast } = useHireFlow();
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(null);
  const [feedback, setFeedback] = useState({});

  useEffect(() => { fetchPipelines(); }, []);

  const fetchPipelines = async () => {
    setLoading(true);
    try {
      const all = await listPipelines();
      const filtered = approvedJob ? all.filter(p => p.job_id === approvedJob.id) : all;
      setPipelines(filtered);
    } catch (err) {
      showToast('error', 'Failed to load pipeline data.');
    } finally { setLoading(false); }
  };

  const handleHRDecision = async (pipelineId, approved) => {
    setActionLoading(pipelineId);
    try {
      await resolveHRGate(pipelineId, approved, feedback[pipelineId] || '');
      showToast('success', approved ? '✅ Candidate approved – Offer Extended!' : '❌ Candidate rejected.');
      await fetchPipelines();
    } catch (err) {
      showToast('error', err?.response?.data?.detail || 'HR action failed.');
    } finally { setActionLoading(null); }
  };

  const handleOfferClick = (pipeline) => {
    if (pipeline.candidate) setSelectedCandidate(pipeline.candidate);
    goNext();
  };

  if (loading) return <LoadingOverlay message="Loading approval pipeline..." />;

  const hrPending = pipelines.filter(p => p.status === 'HR');
  const offered = pipelines.filter(p => p.status === 'Offered');
  const others = pipelines.filter(p => !['HR', 'Offered'].includes(p.status));

  return (
    <div>
      <SectionHeader icon="🎯" title="Approval Center" subtitle="Human-in-the-loop HR gate — approve or reject candidates who passed the interview." />

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
        <button className="btn btn-secondary btn-sm" onClick={fetchPipelines}>🔄 Refresh</button>
      </div>

      {pipelines.length === 0 ? (
        <EmptyState icon="📭" title="No pipeline records" subtitle="Candidates appear here after resume evaluation." />
      ) : (
        <>
          {hrPending.length > 0 && (
            <Section title="⏳ Pending HR Decision" count={hrPending.length} color="#f59e0b">
              {hrPending.map(p => (
                <PipelineRow key={p.id} p={p} feedback={feedback} setFeedback={setFeedback} onApprove={() => handleHRDecision(p.id, true)} onReject={() => handleHRDecision(p.id, false)} actionLoading={actionLoading} />
              ))}
            </Section>
          )}

          {offered.length > 0 && (
            <Section title="🎉 Offer Extended" count={offered.length} color="#10b981">
              {offered.map(p => (
                <div key={p.id} className="card" style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700 }}>{p.candidate?.name || `Candidate #${p.candidate_id}`}</div>
                    <div style={{ color: '#94a3b8', fontSize: '0.85rem' }}>{p.candidate?.email}</div>
                  </div>
                  <PipelineBadge status="Offered" />
                  <button className="btn btn-primary btn-sm" onClick={() => handleOfferClick(p)}>📄 Generate Offer Letter</button>
                </div>
              ))}
            </Section>
          )}

          {others.length > 0 && (
            <Section title="📊 All Other Candidates" count={others.length} color="#6366f1">
              {others.map(p => (
                <div key={p.id} className="card" style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', opacity: p.status === 'Rejected' ? 0.6 : 1 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700 }}>{p.candidate?.name || `Candidate #${p.candidate_id}`}</div>
                    <div style={{ color: '#94a3b8', fontSize: '0.85rem' }}>{p.candidate?.email}</div>
                  </div>
                  <PipelineBadge status={p.status} />
                </div>
              ))}
            </Section>
          )}
        </>
      )}

      <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
        <button className="btn btn-secondary" onClick={goPrev}>← Back</button>
        <button className="btn btn-primary btn-lg" onClick={goNext}>Offer & Onboarding →</button>
      </div>
    </div>
  );
}

function Section({ title, count, color, children }) {
  return (
    <div style={{ marginBottom: '2rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
        <h2 style={{ fontSize: '1rem', fontWeight: 700 }}>{title}</h2>
        <span style={{ background: `${color}22`, border: `1px solid ${color}44`, color, borderRadius: 999, padding: '0.1rem 0.6rem', fontSize: '0.75rem', fontWeight: 700 }}>{count}</span>
      </div>
      {children}
    </div>
  );
}

function PipelineRow({ p, feedback, setFeedback, onApprove, onReject, actionLoading }) {
  return (
    <div className="card" style={{ marginBottom: '0.75rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: '1rem' }}>{p.candidate?.name || `Candidate #${p.candidate_id}`}</div>
          <div style={{ color: '#94a3b8', fontSize: '0.85rem' }}>{p.candidate?.email}</div>
        </div>
        <PipelineBadge status={p.status} />
        {p.interview_gate_feedback && (
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', maxWidth: 300 }}>
            Interview feedback: {p.interview_gate_feedback}
          </div>
        )}
      </div>
      <textarea
        className="form-textarea" rows={2}
        placeholder="Optional HR feedback / notes..."
        value={feedback[p.id] || ''}
        onChange={e => setFeedback(prev => ({ ...prev, [p.id]: e.target.value }))}
        style={{ marginBottom: '0.75rem' }}
      />
      <div style={{ display: 'flex', gap: '0.75rem' }}>
        <button className="btn btn-success" disabled={actionLoading === p.id} onClick={onApprove}>
          {actionLoading === p.id ? '⏳' : '✅'} Approve → Extend Offer
        </button>
        <button className="btn btn-danger" disabled={actionLoading === p.id} onClick={onReject}>
          {actionLoading === p.id ? '⏳' : '❌'} Reject
        </button>
      </div>
    </div>
  );
}
