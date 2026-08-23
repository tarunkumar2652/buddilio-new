import { useEffect } from "react";
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
import { PaymentSuccess, PaymentCancel, PayPalReturn, PayPalSubscriptionReturn } from "@/pages/Payment";
import VerifyPass from "@/pages/VerifyPass";
import Door from "@/pages/Door";
import Blog from "@/pages/Blog";
import BlogPost from "@/pages/BlogPost";
import BlogAuthor from "@/pages/BlogAuthor";
import Unsubscribe from "@/pages/Unsubscribe";
import { CmsPage, Safety } from "@/pages/Content";
import Referrals from "@/pages/Referrals";
import Concierge from "@/pages/Concierge";
import LeaderboardPage from "@/pages/Leaderboard";
import { CityIndex, CityPage } from "@/pages/Cities";
import { Hosts, HostProfile } from "@/pages/Hosts";
import { Hangouts, CompanionDetail, MyBookings, HostHangouts } from "@/pages/Hangouts";
import PartnerDashboard from "@/pages/Partner";
import Admin from "@/pages/Admin";
import Wallet from "@/pages/Wallet";
import Travel from "@/pages/Travel";
import ProviderSignup from "@/pages/ProviderSignup";
import Invoice from "@/pages/Invoice";
import LedgerPage from "@/components/MyLedger";
import VendorAgreement from "@/pages/VendorAgreement";
import { PolicyConsent } from "@/components/PolicyConsent";
import Console from "@/pages/Console";
import VendorSignup from "@/pages/VendorSignup";
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

function ScrollToTop() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) {
      const el = document.getElementById(hash.slice(1));
      if (el) { el.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
    }
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname, hash]);
  return null;
}

function Shell() {
  const loc = useLocation();
  // Emergent OAuth returns to {origin}/dashboard#session_id=... — exchange it before any route renders.
  if (loc.hash?.includes("session_id=")) return <AuthCallback />;
  // The vendor console is its own surface — no member navbar, footer or Buddy widget.
  if (loc.pathname.startsWith("/console")) return <Console />;
  return (
    <div className="min-h-screen flex flex-col">
      <ScrollToTop />
      <Navbar />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/vendor-signup" element={<VendorSignup />} />
          <Route path="/events" element={<Events />} />
          <Route path="/cities" element={<CityIndex />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/city/:slug" element={<CityPage />} />
          <Route path="/events/:id" element={<EventDetail />} />
          <Route path="/hosts" element={<Hosts />} />
          <Route path="/host/:id" element={<HostProfile />} />
          <Route path="/passes" element={<Passes />} />
          <Route path="/membership" element={<Membership />} />
          <Route path="/safety" element={<Safety />} />
          <Route path="/p/:slug" element={<CmsPage />} />
          <Route path="/u/:id" element={<PublicProfile />} />
          <Route path="/payment/success" element={<PaymentSuccess />} />
          <Route path="/payment/cancel" element={<PaymentCancel />} />
          <Route path="/verify" element={<VerifyPass />} />
          <Route path="/verify/:code" element={<VerifyPass />} />
          <Route path="/door" element={<Protected><Door /></Protected>} />
          <Route path="/blog" element={<Blog />} />
          <Route path="/blog/author/:slug" element={<BlogAuthor />} />
          <Route path="/blog/:slug" element={<BlogPost />} />
          <Route path="/unsubscribe" element={<Unsubscribe />} />
          <Route path="/payments/paypal/return" element={<Protected><PayPalReturn /></Protected>} />
          <Route path="/payments/paypal/subscription-return" element={<Protected><PayPalSubscriptionReturn /></Protected>} />

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
          <Route path="/wallet" element={<Protected><Wallet /></Protected>} />
          <Route path="/travel" element={<Protected><Travel /></Protected>} />
          <Route path="/travel/provider" element={<Protected><ProviderSignup /></Protected>} />
          <Route path="/invoice/:id" element={<Protected><Invoice /></Protected>} />
          <Route path="/ledger" element={<Protected><LedgerPage /></Protected>} />
          <Route path="/vendor/agreement" element={<Protected><VendorAgreement /></Protected>} />
          <Route path="/hangouts" element={<Protected><Hangouts /></Protected>} />
          <Route path="/hangouts/host" element={<Protected><HostHangouts /></Protected>} />
          <Route path="/hangouts/bookings" element={<Protected><MyBookings /></Protected>} />
          <Route path="/hangouts/:id" element={<Protected><CompanionDetail /></Protected>} />
          <Route path="/checkout" element={<Protected><Checkout /></Protected>} />
          <Route path="/partner" element={<Protected roles={["partner", "admin"]}><PartnerDashboard /></Protected>} />
          <Route path="/admin" element={<Protected roles={["admin"]}><Admin /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Footer />
      <PolicyConsent />
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
