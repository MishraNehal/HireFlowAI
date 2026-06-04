import { useState, useEffect } from 'react';
import { useHireFlow } from '../context/HireFlowContext';
import { generateJD, approveJD } from '../services/api';
import { SectionHeader, LoadingOverlay, SkillTag } from '../components/UI';

export default function JDReview() {
  const { hiringRequest, generatedJD, setGeneratedJD, setApprovedJob, goNext, goPrev, showToast } = useHireFlow();
  const [loading, setLoading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [jd, setJd] = useState(generatedJD);

  useEffect(() => { if (!jd && hiringRequest) handleGenerate(); }, []);

  const handleGenerate = async () => {
    if (!hiringRequest?.id) return showToast('error', 'No hiring request found.');
    setLoading(true);
    try {
      const res = await generateJD(hiringRequest.id);
      setJd(res.generated_jd);
      setGeneratedJD(res.generated_jd);
    } catch (err) {
      showToast('error', 'JD generation failed. Check backend.');
    } finally { setLoading(false); }
  };

  const handleApprove = async () => {
    setApproving(true);
    try {
      const savedJob = await approveJD(hiringRequest.id, jd);
      setApprovedJob(savedJob);
      showToast('success', 'Job Description approved! Upload resumes next.');
      goNext();
    } catch (err) {
      showToast('error', 'Failed to save approved JD.');
    } finally { setApproving(false); }
  };

  if (loading) return <LoadingOverlay message="Generating Job Description with AI..." />;

  return (
    <div>
      <SectionHeader icon="📝" title="Job Description Review" subtitle="Review the AI-generated JD. You can regenerate if needed." />

      {!jd ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <p style={{ color: '#94a3b8', marginBottom: '1.5rem' }}>Click to generate the Job Description for <strong>{hiringRequest?.role_name}</strong>.</p>
          <button className="btn btn-primary btn-lg" onClick={handleGenerate}>✨ Generate JD</button>
        </div>
      ) : (
        <>
          <div className="card" style={{ marginBottom: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem' }}>
              <div>
                <h2 className="gradient-text">{jd.job_title}</h2>
                <p style={{ color: '#94a3b8', fontSize: '0.9rem', marginTop: '0.25rem' }}>{hiringRequest?.company_name}</p>
              </div>
              <button className="btn btn-secondary" onClick={handleGenerate}>🔄 Regenerate</button>
            </div>

            {jd.company_overview && (
              <Section title="Company Overview"><p style={{ color: '#cbd5e1' }}>{jd.company_overview}</p></Section>
            )}
            <Section title="Responsibilities">
              <ul style={{ paddingLeft: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {jd.responsibilities?.map((r, i) => <li key={i} style={{ color: '#cbd5e1', fontSize: '0.9rem' }}>{r}</li>)}
              </ul>
            </Section>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
              <Section title="Required Skills">
                <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                  {jd.required_skills?.map(s => <SkillTag key={s} skill={s} />)}
                </div>
              </Section>
              <Section title="Preferred Skills">
                <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                  {jd.preferred_skills?.map(s => <span key={s} className="tag" style={{ opacity: 0.7 }}>{s}</span>)}
                </div>
              </Section>
            </div>
            <Section title="Eligibility Criteria"><p style={{ color: '#cbd5e1', fontSize: '0.9rem' }}>{jd.eligibility_criteria}</p></Section>
            <Section title="Hiring Process">
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {jd.hiring_process?.map((s, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.3)', borderRadius: 8, padding: '0.25rem 0.75rem', fontSize: '0.8rem', color: '#818cf8' }}>
                      {i + 1}. {s}
                    </span>
                    {i < jd.hiring_process.length - 1 && <span style={{ color: '#475569' }}>→</span>}
                  </div>
                ))}
              </div>
            </Section>
            {jd.perks?.length > 0 && (
              <Section title="Perks & Benefits">
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px,1fr))', gap: '0.5rem' }}>
                  {jd.perks.map((p, i) => (
                    <div key={i} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', color: '#10b981', fontSize: '0.85rem' }}>
                      <span>✓</span><span>{p}</span>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </div>

          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
            <button className="btn btn-secondary" onClick={goPrev}>← Back</button>
            <button className="btn btn-success btn-lg" onClick={handleApprove} disabled={approving}>
              {approving ? '⏳ Saving...' : '✅ Approve JD & Continue →'}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: '1.5rem' }}>
      <h3 style={{ fontSize: '0.8rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.75rem' }}>{title}</h3>
      {children}
    </div>
  );
}
