import { HireFlowProvider, useHireFlow, STEPS } from './context/HireFlowContext';
import { Toast } from './components/UI';
import Navbar from './components/Navbar';
import StepIndicator from './components/StepIndicator';

// Pages
import HiringForm from './pages/HiringForm';
import JDReview from './pages/JDReview';
import ResumeUpload from './pages/ResumeUpload';
import CandidateRanking from './pages/CandidateRanking';
import InterviewQuestions from './pages/InterviewQuestions';
import ApprovalCenter from './pages/ApprovalCenter';
import OfferOnboarding from './pages/OfferOnboarding';

const PAGE_MAP = {
  1: HiringForm,
  2: JDReview,
  3: ResumeUpload,
  4: CandidateRanking,
  5: InterviewQuestions,
  6: ApprovalCenter,
  7: OfferOnboarding,
};

function AppContent() {
  const { currentStep, toast } = useHireFlow();
  const PageComponent = PAGE_MAP[currentStep] || HiringForm;

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <StepIndicator steps={STEPS} currentStep={currentStep} />

      <main style={{
        flex: 1,
        maxWidth: 1000,
        width: '100%',
        margin: '0 auto',
        padding: '2rem 1.5rem 4rem',
      }}>
        <PageComponent />
      </main>

      <Toast toast={toast} />
    </div>
  );
}

export default function App() {
  return (
    <HireFlowProvider>
      <AppContent />
    </HireFlowProvider>
  );
}
