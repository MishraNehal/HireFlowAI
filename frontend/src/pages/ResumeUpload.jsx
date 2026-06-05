import { useState, useRef } from 'react';
import { useHireFlow } from '../context/HireFlowContext';
import { uploadResume, getCandidateScores, evaluateCandidate, listCandidates } from '../services/api';
import { SectionHeader, LoadingOverlay, PipelineBadge } from '../components/UI';

export default function ResumeUpload() {
  const { approvedJob, uploadedCandidates, setUploadedCandidates, setCandidateScores, goNext, goPrev, showToast } = useHireFlow();
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [results, setResults] = useState([]);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef();

  if (!approvedJob) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
        <p style={{ color: '#94a3b8' }}>No approved Job Description found. Please go back and approve a JD first.</p>
        <button className="btn btn-secondary" style={{ marginTop: '1rem' }} onClick={goPrev}>← Back</button>
      </div>
    );
  }

  const addFiles = (incoming) => {
    const pdfs = Array.from(incoming).filter(f => f.type === 'application/pdf' && f.size <= 5 * 1024 * 1024);
    if (pdfs.length < incoming.length) showToast('warning', 'Only PDF files under 5MB are accepted.');
    setFiles(prev => {
      const names = new Set(prev.map(f => f.name));
      return [...prev, ...pdfs.filter(f => !names.has(f.name))];
    });
  };

  // Score all candidates uploaded in the current session
  const handleScoreAll = async () => {
    if (!approvedJob?.id) return;
    setScoring(true);
    try {
      let scored = 0;
      for (const c of uploadedCandidates) {
        const candidateId = c.candidate?.id || c.id;
        try {
          await evaluateCandidate(candidateId, approvedJob.id);
          scored++;
        } catch (e) { /* skip already-scored or errors */ }
      }
      const scores = await getCandidateScores(approvedJob.id);
      const currentSessionIds = uploadedCandidates.map(c => c.candidate?.id || c.id);
      const filteredScores = currentSessionIds.length > 0 ? scores.filter(s => currentSessionIds.includes(s.candidate_id)) : scores;
      setCandidateScores(filteredScores);
      showToast('success', `Scored ${scored} candidate(s) successfully!`);
    } catch (e) {
      showToast('error', 'Failed to score candidates.');
    } finally {
      setScoring(false);
    }
  };

  const handleUpload = async () => {
    if (files.length === 0) return showToast('error', 'Please select at least one PDF resume.');
    setUploading(true);
    const uploadResults = [];
    for (const file of files) {
      try {
        const res = await uploadResume(approvedJob.id, file);
        uploadResults.push({ name: file.name, status: 'success', data: res });
      } catch (err) {
        uploadResults.push({ name: file.name, status: 'error', error: err?.response?.data?.detail || err.message });
      }
    }
    setResults(uploadResults);
    const successful = uploadResults.filter(r => r.status === 'success').map(r => r.data);
    setUploadedCandidates(prev => [...prev, ...successful]);

    // Auto-evaluate each uploaded candidate immediately
    if (successful.length > 0 && approvedJob?.id) {
      showToast('info', `Scoring ${successful.length} candidate(s)...`);
      for (const cand of successful) {
        const candidateId = cand.candidate?.id || cand.id;
        if (candidateId) {
          try {
            await evaluateCandidate(candidateId, approvedJob.id);
          } catch (e) { /* non-fatal */ }
        }
      }
    }

    // Fetch updated scores
    try {
      const scores = await getCandidateScores(approvedJob.id);
      
      // Filter scores to only show the ones uploaded in THIS session
      const currentSessionIds = [...uploadedCandidates, ...successful].map(c => c.candidate?.id || c.id);
      const filteredScores = currentSessionIds.length > 0 ? scores.filter(s => currentSessionIds.includes(s.candidate_id)) : scores;
      setCandidateScores(filteredScores);
    } catch (e) { /* non-fatal */ }

    showToast('success', `${successful.length}/${files.length} resumes processed & scored.`);
    setFiles([]);
    setUploading(false);
  };

  const handleDrop = (e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); };

  if (uploading || scoring) return <LoadingOverlay message={uploading ? 'Parsing & evaluating resumes with AI... This may take a moment.' : 'Scoring all candidates with AI... Please wait.'} />;

  return (
    <div>
      <SectionHeader icon="📂" title="Resume Upload" subtitle={`Upload PDF resumes for "${approvedJob.role_name}". Max 5MB per file.`} />

      <div className="card" style={{ marginBottom: '1rem' }}>
        <div
          className={`upload-zone${dragging ? ' dragging' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>📄</div>
          <p style={{ color: '#f1f5f9', fontWeight: 600, marginBottom: '0.25rem' }}>Drag & drop resumes here</p>
          <p style={{ color: '#94a3b8', fontSize: '0.85rem' }}>or click to browse — PDF only, max 5MB</p>
          <input ref={fileRef} type="file" accept=".pdf" multiple hidden onChange={e => addFiles(e.target.files)} />
        </div>

        {files.length > 0 && (
          <div style={{ marginTop: '1rem' }}>
            <p style={{ fontSize: '0.85rem', color: '#94a3b8', marginBottom: '0.5rem' }}>Selected ({files.length})</p>
            {files.map(f => (
              <div key={f.name} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.6rem 0.75rem', background: 'rgba(255,255,255,0.04)', borderRadius: 8, marginBottom: '0.4rem' }}>
                <span style={{ fontSize: '0.85rem' }}>📄 {f.name}</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{(f.size / 1024).toFixed(0)} KB</span>
                  <button
                    onClick={() => setFiles(prev => prev.filter(x => x.name !== f.name))}
                    title="Remove"
                    style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '1rem', lineHeight: 1, padding: '0 2px' }}
                  >✕</button>
                </div>
              </div>
            ))}
            <button className="btn btn-primary" style={{ marginTop: '0.75rem', width: '100%' }} onClick={handleUpload}>
              🚀 Upload & Parse All Resumes
            </button>
          </div>
        )}

      </div>

      {results.length > 0 && (
        <div className="card" style={{ marginBottom: '1rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Upload Results</h3>
          {results.map(r => (
            <div key={r.name} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.6rem 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
              <span>{r.status === 'success' ? '✅' : '❌'}</span>
              <span style={{ flex: 1, fontSize: '0.85rem' }}>{r.name}</span>
              {r.status === 'error' && <span style={{ color: '#ef4444', fontSize: '0.8rem' }}>{r.error}</span>}
              {r.status === 'success' && r.data?.candidate?.name && (
                <span style={{ color: '#10b981', fontSize: '0.8rem' }}>→ {r.data.candidate.name}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {uploadedCandidates.length > 0 && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
            <h3>Parsed Candidates ({uploadedCandidates.length})</h3>
            <button className="btn btn-primary" style={{ fontSize: '0.8rem', padding: '0.5rem 1rem' }} onClick={handleScoreAll}>
              ⚡ Score & Rank All
            </button>
          </div>
          {uploadedCandidates.map((c, i) => {
            const cand = c.candidate || c;
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '0.75rem 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <div style={{ width: 36, height: 36, borderRadius: '50%', background: 'rgba(99,102,241,0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, flexShrink: 0 }}>
                  {cand.name?.[0]?.toUpperCase() || '?'}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600 }}>{cand.name}</div>
                  <div style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{cand.email} · {cand.experience_years}yr exp</div>
                </div>
                <PipelineBadge status={c.pipeline?.status || 'Screening'} />
              </div>
            );
          })}
        </div>
      )}

      <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
        <button className="btn btn-secondary" onClick={goPrev}>← Back</button>
        <button className="btn btn-primary btn-lg" onClick={goNext} disabled={uploadedCandidates.length === 0}>
          View Rankings →
        </button>
      </div>
    </div>
  );
}
