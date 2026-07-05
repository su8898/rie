// Route table. Every route except /login is wrapped in <RequireAuth> and
// rendered inside the <Layout> shell.

import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth";
import Layout from "./components/Layout";
import AccidentsPage from "./pages/Accidents";
import ClaimDetailPage from "./pages/ClaimDetail";
import ClaimsPage from "./pages/Claims";
import DashboardPage from "./pages/Dashboard";
import LoginPage from "./pages/Login";
import PaymentsPage from "./pages/Payments";
import ReasonsPage from "./pages/Reasons";
import SubmitPage from "./pages/Submit";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/claims" element={<ClaimsPage />} />
        <Route path="/claims/:id" element={<ClaimDetailPage />} />
        <Route path="/submit" element={<SubmitPage />} />
        <Route path="/payments" element={<PaymentsPage />} />
        <Route path="/accidents" element={<AccidentsPage />} />
        <Route path="/reasons" element={<ReasonsPage />} />
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
