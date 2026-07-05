// Route table. Every route except /login is wrapped in <RequireAuth> and
// rendered inside the <Layout> shell.

import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth";
import Layout from "./components/Layout";
import AccidentsPage from "./pages/Accidents";
import AdminPage from "./pages/Admin";
import AuditPage from "./pages/Audit";
import CasesPage from "./pages/Cases";
import ClaimDetailPage from "./pages/ClaimDetail";
import ClaimsPage from "./pages/Claims";
import CodingPage from "./pages/Coding";
import DashboardPage from "./pages/Dashboard";
import DisputesPage from "./pages/Disputes";
import GovernancePage from "./pages/Governance";
import IntelligencePage from "./pages/Intelligence";
import LoginPage from "./pages/Login";
import NotificationsPage from "./pages/Notifications";
import PaymentsPage from "./pages/Payments";
import ReasonsPage from "./pages/Reasons";
import ReferencePage from "./pages/Reference";
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
        <Route path="/cases" element={<CasesPage />} />
        <Route path="/disputes" element={<DisputesPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/accidents" element={<AccidentsPage />} />
        <Route path="/intelligence" element={<IntelligencePage />} />
        <Route path="/coding" element={<CodingPage />} />
        <Route path="/governance" element={<GovernancePage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/reference" element={<ReferencePage />} />
        <Route path="/reasons" element={<ReasonsPage />} />
        <Route path="/admin" element={<AdminPage />} />
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
