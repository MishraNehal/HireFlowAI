import { useHireFlow, STEPS } from '../context/HireFlowContext';

export default function StepIndicator() {
  const { currentStep, goToStep } = useHireFlow();

  return (
    <div style={{ background: 'rgba(13,21,38,0.7)', borderBottom: '1px solid rgba(255,255,255,0.05)', padding: '1rem 1.5rem', overflowX: 'auto' }}>
      <div style={{ maxWidth: 1100, margin: '0 auto', display: 'flex', alignItems: 'center', gap: 0, minWidth: 'max-content' }}>
        {STEPS.map((step, i) => {
          const done = currentStep > step.id;
          const active = currentStep === step.id;
          return (
            <div key={step.id} style={{ display: 'flex', alignItems: 'center' }}>
              <div
                onClick={() => done && goToStep(step.id)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.5rem',
                  padding: '0.5rem 0.75rem', borderRadius: 10, cursor: done ? 'pointer' : 'default',
                  background: active ? 'rgba(99,102,241,0.15)' : 'transparent',
                  border: active ? '1px solid rgba(99,102,241,0.4)' : '1px solid transparent',
                  transition: 'all 0.2s',
                  opacity: !active && !done ? 0.45 : 1,
                }}>
                <div style={{
                  width: 28, height: 28, borderRadius: '50%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '0.75rem', fontWeight: 700, flexShrink: 0,
                  background: done ? '#10b981' : active ? 'linear-gradient(135deg,#6366f1,#8b5cf6)' : 'rgba(255,255,255,0.08)',
                  color: '#fff', boxShadow: active ? '0 0 12px rgba(99,102,241,0.5)' : 'none',
                }}>
                  {done ? '✓' : step.id}
                </div>
                <span style={{ fontSize: '0.8rem', fontWeight: active ? 700 : 500, color: active ? '#f1f5f9' : '#94a3b8', whiteSpace: 'nowrap' }}>
                  {step.label}
                </span>
              </div>
              {i < STEPS.length - 1 && (
                <div style={{ width: 24, height: 1, background: done ? 'rgba(16,185,129,0.4)' : 'rgba(255,255,255,0.08)', flexShrink: 0 }} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
