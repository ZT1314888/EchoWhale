import { Navigate, Route, Routes } from "react-router-dom";

import { HistoryPage } from "./pages/HistoryPage";
import { HomeUploadPage } from "./pages/HomeUploadPage";
import { LoginPage } from "./pages/LoginPage";
import { PostPracticeReviewPage } from "./pages/PostPracticeReviewPage";
import { PracticeSessionPage } from "./pages/PracticeSessionPage";
import { RegisterPage } from "./pages/RegisterPage";
import { StartupLoadingPage } from "./pages/StartupLoadingPage";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeUploadPage />} />
      <Route path="/session/loading" element={<StartupLoadingPage />} />
      <Route path="/session/:sessionId" element={<PracticeSessionPage />} />
      <Route path="/session/:sessionId/review" element={<PostPracticeReviewPage />} />
      <Route path="/history" element={<HistoryPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
