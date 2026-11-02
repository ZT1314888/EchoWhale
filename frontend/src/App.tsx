import { Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthProvider";
import { RequireAuth } from "./auth/RequireAuth";
import { AppShell } from "./components/AppShell";
import { HistoryPage } from "./pages/HistoryPage";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { HomeUploadPage } from "./pages/HomeUploadPage";
import { LoginPage } from "./pages/LoginPage";
import { PostPracticeReviewPage } from "./pages/PostPracticeReviewPage";
import { PracticeSessionPage } from "./pages/PracticeSessionPage";
import { ProgressPage } from "./pages/ProgressPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { StartupLoadingPage } from "./pages/StartupLoadingPage";
import { VerifyEmailPage } from "./pages/VerifyEmailPage";

export function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* pathless layout route：全部应用路由共享 navbar/footer 外壳，auth 路由也在内
            （原型的账户页同样带 navbar）。RequireAuth 仍是逐路由 element，不随外壳改变。 */}
        <Route element={<AppShell />}>
          <Route path="/" element={<HomeUploadPage />} />
          <Route path="/session/loading" element={<StartupLoadingPage />} />
          <Route path="/session/:sessionId" element={<PracticeSessionPage />} />
          <Route path="/session/:sessionId/review" element={<PostPracticeReviewPage />} />
          <Route
            path="/history"
            element={
              <RequireAuth>
                <HistoryPage />
              </RequireAuth>
            }
          />
          <Route
            path="/progress"
            element={
              <RequireAuth>
                <ProgressPage />
              </RequireAuth>
            }
          />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
