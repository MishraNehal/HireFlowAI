import { useState, useEffect } from 'react';
import { useHireFlow } from '../context/HireFlowContext';
import { getCandidateScores } from '../services/api';
import { SectionHeader, CandidateCard, LoadingOverlay } from '../components/UI';

export default function CandidateRanking() {
  const { approvedJob, candidateScores, setCandidateScores, goNext, goPrev, showToast } = useHireFlow();
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (approvedJob && candidateScores.length === 0) fetchScores();
  }, []);

  const fetchScores = async () => {
    if (!approvedJob?.id) return;
    setLoading(true);
    try {
      const scores = await getCandidateScores(approvedJob.id);
      setCandidateScores(scores);
    } catch (err) {
      showToast('error', 'Failed to load candidate scores.');
    } finally { setLoading(false); }
  };

  const sorted = [...candidateScores].sort((a, b) => (b.total_score || 0) - (a.total_score || 0));
  const qualified = sorted.filter(c => (c.total_score || 0) >= 60);
  const notQualified = sorted.filter(c => (c.total_score || 0) < 60);

  if (loading) return <LoadingOverlay message="Loading candidate scores..." />;

  return (
    <div>
      <SectionHeader icon="🏆" title="Candidate Rankings" subtitle={`AI-scored candidates for "${approvedJob?.role_name}". Score ≥ 60 advances to interview.`} />

      {sorted.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <div style={{ fontSize: '3rem', marginBottom: '1rem', opacity: 0.5 }}>📭</div>
          <p style={{ color: '#94a3b8' }}>No candidates scored yet. Upload resumes first.</p>
          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', marginTop: '1.5rem' }}>
            <button className="btn btn-secondary" onClick={goPrev}>← Upload Resumes</button>
            <button className="btn btn-secondary" onClick={fetchScores}>🔄 Refresh</button>
          </div>
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
            {[
              { label: 'Total', val: sorted.length, color: '#6366f1' },
              { label: 'Shortlisted (≥60)', val: qualified.length, color: '#10b981' },
              { label: 'Rejected (<60)', val: notQualified.length, color: '#ef4444' },
            ].map(({ label, val, color }) => (
              <div key={label} className="card" style={{ flex: 1, minWidth: 140, padding: '1rem 1.25rem' }}>
                <div style={{ fontSize: '1.75rem', fontWeight: 800, color }}>{val}</div>
                <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginTop: '0.25rem' }}>{label}</div>
              </div>
            ))}
          </div>

          {qualified.length > 0 && (
            <div style={{ marginBottom: '2rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                <span style={{ fontSize: '1rem' }}>✅</span>
                <h2 style={{ color: '#10b981' }}>Shortlisted Candidates</h2>
              </div>
              {qualified.map((c, i) => <CandidateCard key={c.id} candidate={c} rank={i + 1} />)}
            </div>
          )}

          {notQualified.length > 0 && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                <span style={{ fontSize: '1rem' }}>❌</span>
                <h2 style={{ color: '#ef4444' }}>Below Threshold</h2>
              </div>
              {notQualified.map((c, i) => <CandidateCard key={c.id} candidate={c} rank={qualified.length + i + 1} />)}
            </div>
          )}

          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
            <button className="btn btn-secondary" onClick={goPrev}>← Back</button>
            <button className="btn btn-secondary" onClick={fetchScores}>🔄 Refresh</button>
            <button className="btn btn-primary btn-lg" onClick={goNext} disabled={qualified.length === 0}>
              View Interview Questions →
            </button>
          </div>
        </>
      )}
    </div>
  );
}
