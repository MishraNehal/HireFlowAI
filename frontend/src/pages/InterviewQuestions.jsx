import { useState, useEffect } from 'react';
import { useHireFlow } from '../context/HireFlowContext';
import { getInterviewQuestions } from '../services/api';
import { SectionHeader, LoadingOverlay, EmptyState } from '../components/UI';

export default function InterviewQuestions() {
  const { approvedJob, interviewQuestions, setInterviewQuestions, goNext, goPrev, showToast } = useHireFlow();
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => { if (approvedJob && interviewQuestions.length === 0) fetchQuestions(); }, []);

  const fetchQuestions = async () => {
    if (!approvedJob?.id) return;
    setLoading(true);
    try {
      const qs = await getInterviewQuestions(approvedJob.id);
      setInterviewQuestions(qs);
    } catch (err) {
      showToast('error', 'Failed to load interview questions.');
    } finally { setLoading(false); }
  };

  if (loading) return <LoadingOverlay message="Loading RAG-generated interview questions..." />;

  return (
    <div>
      <SectionHeader icon="💬" title="Interview Questions" subtitle="RAG-generated, role-specific questions for your interviewers." />

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem', gap: '0.5rem' }}>
        <button className="btn btn-secondary btn-sm" onClick={fetchQuestions}>🔄 Refresh</button>
      </div>

      {interviewQuestions.length === 0 ? (
        <EmptyState icon="💬" title="No questions found" subtitle="Questions are generated when a JD is approved. Try refreshing." />
      ) : (
        <div className="table-wrap">
          {interviewQuestions.map((q, i) => (
            <div key={q.id || i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', padding: '1rem 1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem', cursor: 'pointer' }}
                onClick={() => setExpanded(expanded === i ? null : i)}>
                <div style={{ width: 28, height: 28, borderRadius: '50%', flexShrink: 0, background: 'rgba(99,102,241,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.75rem', fontWeight: 700, color: '#818cf8' }}>
                  Q{i + 1}
                </div>
                <div style={{ flex: 1 }}>
                  <p style={{ fontSize: '0.95rem', fontWeight: 500, color: '#f1f5f9' }}>{q.question_text}</p>
                </div>
                <span style={{ color: '#94a3b8', flexShrink: 0, marginTop: 2 }}>{expanded === i ? '▲' : '▼'}</span>
              </div>

              {expanded === i && q.expected_answer && (
                <div style={{ marginTop: '0.75rem', marginLeft: '2.5rem', padding: '1rem', background: 'rgba(16,185,129,0.07)', border: '1px solid rgba(16,185,129,0.2)', borderRadius: 10 }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#10b981', marginBottom: '0.4rem', textTransform: 'uppercase' }}>Model Answer</div>
                  <p style={{ fontSize: '0.875rem', color: '#a7f3d0', lineHeight: 1.6 }}>{q.expected_answer}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
        <button className="btn btn-secondary" onClick={goPrev}>← Back</button>
        <button className="btn btn-primary btn-lg" onClick={goNext}>Approval Center →</button>
      </div>
    </div>
  );
}
