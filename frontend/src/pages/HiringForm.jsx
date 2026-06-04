import { useState } from 'react';
import { useHireFlow } from '../context/HireFlowContext';
import { createHiringRequest } from '../services/api';
import { SectionHeader, LoadingOverlay } from '../components/UI';

const EXPERIENCE_OPTIONS = ['0-1 Years', '0-2 Years', '1-3 Years', '2-4 Years', '3-5 Years', '5+ Years', 'Fresher'];

export default function HiringForm() {
  const { setHiringRequest, goNext, showToast } = useHireFlow();
  const [loading, setLoading] = useState(false);
  const [skillInput, setSkillInput] = useState('');
  const [form, setForm] = useState({
    company_name: '',
    role_name: '',
    skills_required: [],
    experience_level: '0-2 Years',
    num_openings: 1,
    additional_context: '',
  });

  const addSkill = () => {
    const s = skillInput.trim();
    if (s && !form.skills_required.includes(s)) {
      setForm(p => ({ ...p, skills_required: [...p.skills_required, s] }));
    }
    setSkillInput('');
  };

  const removeSkill = (s) => setForm(p => ({ ...p, skills_required: p.skills_required.filter(x => x !== s) }));

  const handleKeyDown = (e) => { if (e.key === 'Enter') { e.preventDefault(); addSkill(); } };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.company_name || !form.role_name) return showToast('error', 'Company name and role are required.');
    if (form.skills_required.length === 0) return showToast('error', 'Add at least one required skill.');
    setLoading(true);
    try {
      const result = await createHiringRequest(form);
      setHiringRequest(result);
      showToast('success', 'Hiring requirement saved! Generating JD next...');
      goNext();
    } catch (err) {
      showToast('error', err?.response?.data?.detail || 'Failed to submit requirement.');
    } finally { setLoading(false); }
  };

  if (loading) return <LoadingOverlay message="Saving hiring requirement..." />;

  return (
    <div>
      <SectionHeader icon="📋" title="Hiring Requirements" subtitle="Tell us who you're looking to hire. AI will generate a professional Job Description." />

      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-grid">
            <div className="form-group">
              <label className="form-label">Company Name *</label>
              <input className="form-input" placeholder="e.g. ABC Technologies" value={form.company_name}
                onChange={e => setForm(p => ({ ...p, company_name: e.target.value }))} required />
            </div>
            <div className="form-group">
              <label className="form-label">Job Role / Title *</label>
              <input className="form-input" placeholder="e.g. Python Intern" value={form.role_name}
                onChange={e => setForm(p => ({ ...p, role_name: e.target.value }))} required />
            </div>
            <div className="form-group">
              <label className="form-label">Experience Level</label>
              <select className="form-select" value={form.experience_level}
                onChange={e => setForm(p => ({ ...p, experience_level: e.target.value }))}>
                {EXPERIENCE_OPTIONS.map(o => <option key={o}>{o}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Number of Openings</label>
              <input className="form-input" type="number" min={1} max={50} value={form.num_openings}
                onChange={e => setForm(p => ({ ...p, num_openings: parseInt(e.target.value) || 1 }))} />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Required Skills *</label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <input className="form-input" placeholder="Type a skill and press Enter or Add"
                value={skillInput} onChange={e => setSkillInput(e.target.value)} onKeyDown={handleKeyDown} />
              <button type="button" className="btn btn-secondary" onClick={addSkill}>Add</button>
            </div>
            {form.skills_required.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.75rem' }}>
                {form.skills_required.map(s => (
                  <span key={s} style={{
                    display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                    padding: '0.25rem 0.75rem', background: 'rgba(99,102,241,0.15)',
                    border: '1px solid rgba(99,102,241,0.3)', borderRadius: 999,
                    fontSize: '0.8rem', color: '#818cf8',
                  }}>
                    {s}
                    <span style={{ cursor: 'pointer', opacity: 0.7 }} onClick={() => removeSkill(s)}>✕</span>
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="form-group">
            <label className="form-label">Additional Context (Optional)</label>
            <textarea className="form-textarea" rows={3}
              placeholder="Any extra context — team size, tech stack, culture, remote/onsite..."
              value={form.additional_context}
              onChange={e => setForm(p => ({ ...p, additional_context: e.target.value }))} />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
            <button type="submit" className="btn btn-primary btn-lg">
              Generate Job Description →
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
