import React, { createContext, useContext, useState, useCallback } from 'react';

const HireFlowContext = createContext(null);

export const STEPS = [
  { id: 1, key: 'hiring-form',    label: 'Hiring Requirements' },
  { id: 2, key: 'jd-review',      label: 'Job Description' },
  { id: 3, key: 'resume-upload',  label: 'Resume Upload' },
  { id: 4, key: 'candidate-rank', label: 'Candidate Ranking' },
  { id: 5, key: 'interview-qs',   label: 'Interview Questions' },
  { id: 6, key: 'approval',       label: 'Approval Center' },
  { id: 7, key: 'offer',          label: 'Offer & Onboarding' },
];

export function HireFlowProvider({ children }) {
  // Navigation
  const [currentStep, setCurrentStep] = useState(1);

  // Step 1: Hiring requirements
  const [hiringRequest, setHiringRequest] = useState(null);

  // Step 2: JD review
  const [generatedJD, setGeneratedJD] = useState(null);
  const [approvedJob, setApprovedJob] = useState(null);

  // Step 3: Resume upload
  const [uploadedCandidates, setUploadedCandidates] = useState([]);

  // Step 4: Candidate scores
  const [candidateScores, setCandidateScores] = useState([]);

  // Step 5: Interview questions
  const [interviewQuestions, setInterviewQuestions] = useState([]);

  // Step 6: Pipelines / Approvals
  const [pipelines, setPipelines] = useState([]);
  const [selectedCandidate, setSelectedCandidate] = useState(null);

  // Step 7: Offer / Onboarding
  const [offerLetter, setOfferLetter] = useState('');
  const [onboardingChecklist, setOnboardingChecklist] = useState([]);

  // Global toast/error
  const [toast, setToast] = useState(null);  // { type: 'success'|'error', message }

  const showToast = useCallback((type, message) => {
    setToast({ type, message });
    setTimeout(() => setToast(null), 4500);
  }, []);

  const goToStep = useCallback((step) => {
    setCurrentStep(step);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const goNext = useCallback(() => {
    setCurrentStep(prev => Math.min(prev + 1, STEPS.length));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const goPrev = useCallback(() => {
    setCurrentStep(prev => Math.max(prev - 1, 1));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const resetAll = useCallback(() => {
    setCurrentStep(1);
    setHiringRequest(null);
    setGeneratedJD(null);
    setApprovedJob(null);
    setUploadedCandidates([]);
    setCandidateScores([]);
    setInterviewQuestions([]);
    setPipelines([]);
    setSelectedCandidate(null);
    setOfferLetter('');
    setOnboardingChecklist([]);
  }, []);

  return (
    <HireFlowContext.Provider value={{
      // Navigation
      currentStep, goToStep, goNext, goPrev,

      // Step data
      hiringRequest, setHiringRequest,
      generatedJD, setGeneratedJD,
      approvedJob, setApprovedJob,
      uploadedCandidates, setUploadedCandidates,
      candidateScores, setCandidateScores,
      interviewQuestions, setInterviewQuestions,
      pipelines, setPipelines,
      selectedCandidate, setSelectedCandidate,
      offerLetter, setOfferLetter,
      onboardingChecklist, setOnboardingChecklist,

      // UI
      toast, showToast,

      // Reset
      resetAll,
    }}>
      {children}
    </HireFlowContext.Provider>
  );
}

export const useHireFlow = () => {
  const ctx = useContext(HireFlowContext);
  if (!ctx) throw new Error('useHireFlow must be used within a HireFlowProvider');
  return ctx;
};
