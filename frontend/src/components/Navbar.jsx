import { useHireFlow, STEPS } from '../context/HireFlowContext';

export default function Navbar() {
  const { resetAll } = useHireFlow();
  return (
    <nav style={{
      background: 'rgba(10,15,30,0.9)',
      backdropFilter: 'blur(16px)',
      borderBottom: '1px solid rgba(255,255,255,0.06)',
      position: 'sticky', top: 0, zIndex: 100,
      padding: '0 1.5rem',
    }}>
      <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: 60 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }} onClick={resetAll}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '1.2rem', boxShadow: '0 0 20px rgba(99,102,241,0.4)'
          }}>⚡</div>
          <div>
            <div style={{ fontWeight: 800, fontSize: '1rem', color: '#f1f5f9' }}>HireFlow<span style={{ color: '#818cf8' }}>AI</span></div>
            <div style={{ fontSize: '0.65rem', color: '#475569', fontWeight: 500 }}>Agentic Recruitment Platform</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', boxShadow: '0 0 8px #10b981' }} />
          <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>System Online</span>
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer"
            className="btn btn-secondary btn-sm" style={{ textDecoration: 'none' }}>
            API Docs
          </a>
        </div>
      </div>
    </nav>
  );
}
