import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { CurrencyProvider } from "@/context/CurrencyContext";
import { Navbar, Footer } from "@/components/Layout";
import { Spinner } from "@/components/Shared";
import { InstallPrompt } from "@/components/InstallPrompt";
import { AiChatWidget } from "@/components/AiChatWidget";
import Home from "@/pages/Home";
import { Login, Register, ForgotPassword, ResetPassword } from "@/pages/Auth";
import AuthCallback from "@/pages/AuthCallback";
import Welcome from "@/pages/Welcome";
import Dashboard, { Orders, Notifications, SavedEvents } from "@/pages/Dashboard";
import { Events, EventDetail } from "@/pages/Events";
import { Discover, PublicProfile, MyProfile } from "@/pages/Discover";
import Messages from "@/pages/Messages";
import { Membership, Passes, Checkout } from "@/pages/Commerce";
import { PaymentSuccess, PaymentCancel } from "@/pages/Payment";
import { CmsPage, Safety } from "@/pages/Content";
import Referrals from "@/pages/Referrals";
import Concierge from "@/pages/Concierge";
import LeaderboardPage from "@/pages/Leaderboard";
import { CityIndex, CityPage } from "@/pages/Cities";
import PartnerDashboard from "@/pages/Partner";
import Admin from "@/pages/Admin";
import Console from "@/pages/Console";
import "@/index.css";

function Protected({ children, roles }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Spinner label="Checking your session" />;
  if (!user) return <Navigate to="/login" state={{ from: loc.pathname }} replace />;
  if (user.profile_complete === false && loc.pathname !== "/welcome") return <Navigate to="/welcome" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/dashboard" replace />;
  return children;
}

function Shell() {
  const loc = useLocation();
  // Emergent OAuth returns to {origin}/dashboard#session_id=... — exchange it before any route renders.
  if (loc.hash?.includes("session_id=")) return <AuthCallback />;
  // The vendor console is its own surface — no member navbar, footer or Buddy widget.
  if (loc.pathname.startsWith("/console")) return <Console />;
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/events" element={<Events />} />
          <Route path="/cities" element={<CityIndex />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/city/:slug" element={<CityPage />} />
          <Route path="/events/:id" element={<EventDetail />} />
          <Route path="/passes" element={<Passes />} />
          <Route path="/membership" element={<Membership />} />
          <Route path="/safety" element={<Safety />} />
          <Route path="/p/:slug" element={<CmsPage />} />
          <Route path="/u/:id" element={<PublicProfile />} />
          <Route path="/payment/success" element={<PaymentSuccess />} />
          <Route path="/payment/cancel" element={<PaymentCancel />} />

          <Route path="/welcome" element={<Protected><Welcome /></Protected>} />
          <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
          <Route path="/discover" element={<Protected><Discover /></Protected>} />
          <Route path="/messages" element={<Protected><Messages /></Protected>} />
          <Route path="/orders" element={<Protected><Orders /></Protected>} />
          <Route path="/saved" element={<Protected><SavedEvents /></Protected>} />
          <Route path="/notifications" element={<Protected><Notifications /></Protected>} />
          <Route path="/profile" element={<Protected><MyProfile /></Protected>} />
          <Route path="/referrals" element={<Protected><Referrals /></Protected>} />
          <Route path="/ai" element={<Protected><Concierge /></Protected>} />
          <Route path="/checkout" element={<Protected><Checkout /></Protected>} />
          <Route path="/partner" element={<Protected roles={["partner", "admin"]}><PartnerDashboard /></Protected>} />
          <Route path="/admin" element={<Protected roles={["admin"]}><Admin /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Footer />
      <InstallPrompt />
      <AiChatWidget />
      <Toaster position="top-center" richColors />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <CurrencyProvider>
          <Shell />
        </CurrencyProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
