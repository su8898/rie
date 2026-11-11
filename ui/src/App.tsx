// Route table. Every route except /login is wrapped in <RequireAuth> and
// rendered inside the <Layout> shell. Pages load on demand.

import { lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth";
import Layout from "./components/Layout";
import LoginPage from "./pages/Login";

// Each page is its own chunk, loaded when first opened.
const AccidentsPage = lazy(() => import("./pages/Accidents"));
const AdminLayout = lazy(() => import("./pages/admin/AdminLayout"));
const AuditLogAdmin = lazy(() => import("./pages/admin/AuditLog"));
const ChannelAccessAdmin = lazy(() => import("./pages/admin/ChannelAccess"));
const CodingRulesAdmin = lazy(() => import("./pages/admin/CodingRules"));
const DatedRatesAdmin = lazy(() => import("./pages/admin/DatedRates"));
const NegotiatedRatesAdmin = lazy(() => import("./pages/admin/NegotiatedRates"));
const PreauthCodesAdmin = lazy(() => import("./pages/admin/PreauthCodes"));
const SignalModesAdmin = lazy(() => import("./pages/admin/SignalModes"));
const StatutoryCapAdmin = lazy(() => import("./pages/admin/StatutoryCap"));
const UsersAdmin = lazy(() => import("./pages/admin/Users"));
const AuditPage = lazy(() => import("./pages/Audit"));
const CasesPage = lazy(() => import("./pages/Cases"));
const CaseRecordPage = lazy(() => import("./pages/CaseRecord"));
const ClaimDetailPage = lazy(() => import("./pages/ClaimDetail"));
const ClaimNewPage = lazy(() => import("./pages/ClaimNew"));
const ClaimsPage = lazy(() => import("./pages/Claims"));
const CodingPage = lazy(() => import("./pages/Coding"));
const DashboardPage = lazy(() => import("./pages/Dashboard"));
const DisputesPage = lazy(() => import("./pages/Disputes"));
const DisputeRecordPage = lazy(() => import("./pages/DisputeRecord"));
const GovernancePage = lazy(() => import("./pages/Governance"));
const IntelligencePage = lazy(() => import("./pages/Intelligence"));
const NotificationsPage = lazy(() => import("./pages/Notifications"));
const PaymentsPage = lazy(() => import("./pages/Payments"));
const PracticesPage = lazy(() => import("./pages/Practices"));
const PracticeRecordPage = lazy(() => import("./pages/PracticeRecord"));
const PriceListsPage = lazy(() => import("./pages/PriceLists"));
const PriceListRecordPage = lazy(() => import("./pages/PriceListRecord"));
const PaymentRunPage = lazy(() => import("./pages/PaymentRun"));
const RemittanceAdvicePage = lazy(() => import("./pages/RemittanceAdvice"));
const ReasonsPage = lazy(() => import("./pages/Reasons"));
const ReferencePage = lazy(() => import("./pages/Reference"));

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
        <Route path="/claims/new" element={<ClaimNewPage />} />
        <Route path="/claims/:id" element={<ClaimDetailPage />} />
        <Route path="/submit" element={<Navigate to="/claims/new" replace />} />
        <Route path="/practices" element={<PracticesPage />} />
        <Route path="/practices/:id" element={<PracticeRecordPage />} />
        <Route path="/payments" element={<PaymentsPage />} />
        <Route path="/payments/runs/:id" element={<PaymentRunPage />} />
        <Route path="/payments/remittances/:ref" element={<RemittanceAdvicePage />} />
        <Route path="/cases" element={<CasesPage />} />
        <Route path="/cases/:id" element={<CaseRecordPage />} />
        <Route path="/disputes" element={<DisputesPage />} />
        <Route path="/disputes/:id" element={<DisputeRecordPage />} />
        <Route path="/audit" element={<AuditPage />} />
        <Route path="/accidents" element={<AccidentsPage />} />
        <Route path="/intelligence" element={<IntelligencePage />} />
        <Route path="/coding" element={<CodingPage />} />
        <Route path="/governance" element={<GovernancePage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/reference" element={<ReferencePage />} />
        <Route path="/price-lists" element={<PriceListsPage />} />
        <Route path="/price-lists/:id" element={<PriceListRecordPage />} />
        <Route path="/reasons" element={<ReasonsPage />} />
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<Navigate to="users" replace />} />
          <Route path="users" element={<UsersAdmin />} />
          <Route path="channel" element={<ChannelAccessAdmin />} />
          <Route path="rates" element={<DatedRatesAdmin />} />
          <Route path="negotiated" element={<NegotiatedRatesAdmin />} />
          <Route path="cap" element={<StatutoryCapAdmin />} />
          <Route path="preauth" element={<PreauthCodesAdmin />} />
          <Route path="coding-rules" element={<CodingRulesAdmin />} />
          <Route path="signals" element={<SignalModesAdmin />} />
          <Route path="audit" element={<AuditLogAdmin />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
