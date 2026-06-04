import axios from 'axios';

const BASE_URL = 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ─── Hiring Requests ────────────────────────────────────────────────────────

export const createHiringRequest = (payload) =>
  api.post('/api/hiring-requests', payload).then(r => r.data);

export const listHiringRequests = () =>
  api.get('/api/hiring-requests').then(r => r.data);

export const getHiringRequest = (id) =>
  api.get(`/api/hiring-requests/${id}`).then(r => r.data);

// ─── JD Generation ──────────────────────────────────────────────────────────

export const generateJD = (hiring_request_id) =>
  api.post('/api/jd/generate', { hiring_request_id }).then(r => r.data);

export const approveJD = (hiring_request_id, generated_jd) =>
  api.post('/api/jd/approve', { hiring_request_id, generated_jd }).then(r => r.data);

// ─── Jobs ────────────────────────────────────────────────────────────────────

export const listJobs = () =>
  api.get('/api/jobs').then(r => r.data);

export const getJob = (id) =>
  api.get(`/api/jobs/${id}`).then(r => r.data);

// ─── Candidates ──────────────────────────────────────────────────────────────

export const listCandidates = () =>
  api.get('/api/candidates').then(r => r.data);

export const uploadResume = (jobId, file) => {
  const form = new FormData();
  form.append('file', file);
  return axios.post(`${BASE_URL}/api/candidates/upload?job_id=${jobId}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  }).then(r => r.data);
};

export const evaluateCandidate = (candidateId, jobId) =>
  api.post(`/api/candidates/${candidateId}/evaluate/${jobId}`).then(r => r.data);

export const getCandidateScores = (jobId) =>
  api.get(`/api/candidates/scores?job_id=${jobId}`).then(r => r.data);

// ─── Pipeline (Interview + HR) ───────────────────────────────────────────────

export const listPipelines = () =>
  api.get('/api/pipelines').then(r => r.data);

export const getPipeline = (pipelineId) =>
  api.get(`/api/pipelines/${pipelineId}`).then(r => r.data);

export const getInterviewQuestions = (jobId) =>
  api.get(`/api/pipelines/questions?job_id=${jobId}`).then(r => r.data);

export const submitInterviewAnswers = (pipelineId, answers) =>
  api.post(`/api/pipelines/${pipelineId}/interview/submit`, { answers }).then(r => r.data);

export const resolveHRGate = (pipelineId, approved, feedback = '') =>
  api.post(`/api/pipelines/${pipelineId}/hr-action`, {
    approved,
    feedback,
  }).then(r => r.data);

export const getCandidatePipeline = (candidateId, jobId) =>
  api.get(`/api/pipelines/candidate/${candidateId}?job_id=${jobId}`).then(r => r.data);

// ─── Offer & Onboarding ─────────────────────────────────────────────────────

export const generateOfferLetter = (payload) =>
  api.post('/api/offer/generate', payload).then(r => r.data);

export const generateOnboarding = (payload) =>
  api.post('/api/offer/onboarding', payload).then(r => r.data);

// ─── Dashboard ──────────────────────────────────────────────────────────────

export const getDashboard = () =>
  api.get('/api/dashboard').then(r => r.data);

// ─── Error helper ────────────────────────────────────────────────────────────

export const getErrorMessage = (error) => {
  if (error?.response?.data?.detail) {
    const detail = error.response.data.detail;
    return typeof detail === 'string' ? detail : JSON.stringify(detail);
  }
  return error?.message || 'An unexpected error occurred';
};

export default api;
