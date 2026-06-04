export function Spinner({ size = 'sm' }) {
  return <div className={`spinner${size === 'lg' ? ' spinner-lg' : ''}`} />;
}

export function LoadingOverlay({ message = 'Processing...' }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', gap: '1rem', padding: '3rem',
    }}>
      <Spinner size="lg" />
      <p style={{ color: '#94a3b8', fontSize: '0.95rem' }}>{message}</p>
    </div>
  );
}

export function Toast({ toast }) {
  if (!toast) return null;
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  return (
    <div className="toast-container">
      <div className={`toast toast-${toast.type}`}>
        <span>{icons[toast.type]}</span>
        <span>{toast.message}</span>
      </div>
    </div>
  );
}

export function ScoreBadge({ score }) {
  const cls = score >= 70 ? 'score-high' : score >= 50 ? 'score-mid' : 'score-low';
  return <div className={`score-ring ${cls}`}>{Math.round(score)}</div>;
}

export function PipelineBadge({ status }) {
  const map = {
    Screening: 'badge-info',
    Interviewing: 'badge-accent',
    HR: 'badge-warning',
    Offered: 'badge-success',
    Rejected: 'badge-danger',
    'Not Evaluated': 'badge-gray',
  };
  return <span className={`badge ${map[status] || 'badge-gray'}`}>{status}</span>;
}

export function SectionHeader({ icon, title, subtitle }) {
  return (
    <div className="section-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
        <span style={{ fontSize: '1.5rem' }}>{icon}</span>
        <h1 className="gradient-text">{title}</h1>
      </div>
      {subtitle && <p className="text-muted">{subtitle}</p>}
    </div>
  );
}

export function SkillTag({ skill }) {
  return <span className="tag">{skill}</span>;
}

export function EmptyState({ icon = '📭', title, subtitle }) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      {subtitle && <p style={{ marginTop: '0.5rem', fontSize: '0.9rem' }}>{subtitle}</p>}
    </div>
  );
}

export function CandidateCard({ candidate, rank }) {
  const score = candidate.total_score || 0;
  const cls = score >= 70 ? 'score-high' : score >= 50 ? 'score-mid' : 'score-low';
  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', flexWrap: 'wrap' }}>
        {rank && (
          <div style={{
            width: 40, height: 40, borderRadius: '50%', flexShrink: 0,
            background: rank <= 3 ? 'linear-gradient(135deg,#f59e0b,#ef4444)' : 'rgba(255,255,255,0.08)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontWeight: 800, fontSize: '0.9rem',
          }}>
            {rank === 1 ? '🥇' : rank === 2 ? '🥈' : rank === 3 ? '🥉' : `#${rank}`}
          </div>
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: '1rem' }}>{candidate.name}</div>
          <div style={{ color: '#94a3b8', fontSize: '0.85rem' }}>{candidate.email}</div>
        </div>
        <ScoreBadge score={score} />
        <PipelineBadge status={candidate.pipeline_status || 'Not Evaluated'} />
      </div>
      {candidate.parsed_skills?.length > 0 && (
        <div style={{ marginTop: '1rem', display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
          {candidate.parsed_skills.slice(0, 8).map(s => <SkillTag key={s} skill={s} />)}
          {candidate.parsed_skills.length > 8 && <span className="tag">+{candidate.parsed_skills.length - 8}</span>}
        </div>
      )}
      <div style={{ display: 'flex', gap: '1.5rem', marginTop: '1rem', flexWrap: 'wrap' }}>
        {[
          { label: 'Skills', val: candidate.skills_score || 0, max: 40 },
          { label: 'Experience', val: candidate.experience_score || 0, max: 20 },
          { label: 'Projects', val: candidate.projects_score || 0, max: 25 },
          { label: 'JD Match', val: candidate.jd_match_score || 0, max: 15 },
        ].map(({ label, val, max }) => (
          <div key={label} style={{ flex: 1, minWidth: 100 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{label}</span>
              <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>{Math.round(val)}/{max}</span>
            </div>
            <div className="progress-bar-wrap">
              <div className="progress-bar-fill" style={{ width: `${(val / max) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
