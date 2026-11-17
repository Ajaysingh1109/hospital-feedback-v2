import React, { useState } from "react";
import {
  Lock,
  User as UserIcon,
  ArrowRight,
  ShieldCheck,
  HeartPulse,
  KeyRound,
  AlertCircle,
  Eye,
  EyeOff,
  X,
  Stethoscope,
  ShieldAlert,
  Loader2,
  CheckCircle2,
  Info,
} from "lucide-react";
import { login, changePassword, setToken } from "../services/api";
import { AuthResponse } from "../types";

interface LoginViewProps {
  onLoginSuccess: (auth: AuthResponse) => void;
}

type LoginType = "EMPLOYEE" | "MASTER";

export const LoginView: React.FC<LoginViewProps> = ({ onLoginSuccess }) => {
  // Login Role Selector state (Default: Employee)
  // SECURITY NOTE: This selection is purely for UI guidance and theme styling.
  // Backend server-side authentication alone determines the user's actual role and permissions.
  const [loginType, setLoginType] = useState<LoginType>("EMPLOYEE");

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Session Expiration Banner (Read once from sessionStorage, then cleared)
  const [sessionNotice, setSessionNotice] = useState<string | null>(() => {
    try {
      const notice = sessionStorage.getItem("auth_notice");
      if (notice) {
        sessionStorage.removeItem("auth_notice");
        return notice;
      }
    } catch (_) {}
    return null;
  });

  // Forgot Password Modal State
  const [forgotModalOpen, setForgotModalOpen] = useState(false);
  const [forgotUsername, setForgotUsername] = useState("");
  const [forgotSubmitted, setForgotSubmitted] = useState(false);

  // Forced Password Change state
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [changeLoading, setChangeLoading] = useState(false);
  const [pendingAuth, setPendingAuth] = useState<AuthResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;

    setError(null);
    setLoading(true);

    try {
      // Authenticate via server-side endpoint.
      // Backend determines actual role based on username/password in database,
      // completely independent of the frontend loginType toggle.
      const res = await login(username.trim(), password);

      if (res.must_change_password) {
        setPendingAuth(res);
        setMustChangePassword(true);
      } else {
        onLoginSuccess(res);
      }
    } catch (err: any) {
      const msg = err?.message || "Invalid username or password.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handlePasswordChangeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (changeLoading) return;

    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters long.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("New passwords do not match.");
      return;
    }

    setChangeLoading(true);
    try {
      if (pendingAuth?.access_token) {
        setToken(pendingAuth.access_token);
      }
      await changePassword(password, newPassword);
      if (pendingAuth) {
        onLoginSuccess({ ...pendingAuth, must_change_password: false });
      }
    } catch (err: any) {
      setError(err?.message || "Failed to change password.");
    } finally {
      setChangeLoading(false);
    }
  };

  const handleForgotSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setForgotSubmitted(true);
  };

  const closeForgotModal = () => {
    setForgotModalOpen(false);
    setForgotSubmitted(false);
    setForgotUsername("");
  };

  const isEmployee = loginType === "EMPLOYEE";

  return (
    <div className="min-h-screen flex flex-col justify-center items-center px-4 py-8 bg-gradient-to-br from-slate-100 via-sky-50 to-teal-50 transition-colors duration-500">
      <div className="w-full max-w-md bg-white rounded-3xl shadow-xl border border-slate-200/80 p-6 sm:p-8 animate-fade-in relative transition-all duration-300">
        
        {/* Brand Header */}
        <div className="text-center mb-6">
          <div
            className={`w-16 h-16 rounded-3xl mx-auto flex items-center justify-center text-white shadow-xl mb-3 transition-all duration-300 ${
              isEmployee
                ? "bg-gradient-to-tr from-teal-700 to-emerald-600 shadow-teal-700/30"
                : "bg-gradient-to-tr from-indigo-700 to-purple-600 shadow-indigo-700/30"
            }`}
          >
            {isEmployee ? (
              <HeartPulse className="w-9 h-9 stroke-[2.2] animate-pulse" />
            ) : (
              <ShieldAlert className="w-9 h-9 stroke-[2.2]" />
            )}
          </div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">
            FEEDBACK MAC
          </h1>
          <p className="text-xs font-extrabold text-teal-700 uppercase tracking-widest mt-0.5">
            Powered by Saarthi-One
          </p>
          <p className="text-xs text-slate-500 mt-1">
            Autonomous Bedside Voice Feedback Platform
          </p>
        </div>

        {/* Two Login Types Toggle Pill */}
        {!mustChangePassword && (
          <div className="mb-5">
            <div className="flex bg-slate-100 p-1.5 rounded-2xl border border-slate-200">
              <button
                type="button"
                onClick={() => {
                  setLoginType("EMPLOYEE");
                  setError(null);
                }}
                className={`flex-1 py-2.5 px-3 rounded-xl font-bold text-xs sm:text-sm transition-all duration-200 flex items-center justify-center gap-2 ${
                  isEmployee
                    ? "bg-teal-700 text-white shadow-md shadow-teal-700/20"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Stethoscope className="w-4 h-4" />
                <span>Employee</span>
              </button>

              <button
                type="button"
                onClick={() => {
                  setLoginType("MASTER");
                  setError(null);
                }}
                className={`flex-1 py-2.5 px-3 rounded-xl font-bold text-xs sm:text-sm transition-all duration-200 flex items-center justify-center gap-2 ${
                  !isEmployee
                    ? "bg-indigo-700 text-white shadow-md shadow-indigo-700/20"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <ShieldAlert className="w-4 h-4" />
                <span>Master</span>
              </button>
            </div>

            {/* Role-Specific Context Subtext */}
            <div
              className={`mt-2.5 px-3.5 py-2 rounded-xl text-xs flex items-center gap-2 transition-colors duration-200 ${
                isEmployee
                  ? "bg-teal-50 border border-teal-100 text-teal-900"
                  : "bg-indigo-50 border border-indigo-100 text-indigo-900"
              }`}
            >
              <span className="font-bold shrink-0">
                {isEmployee ? "Feedback Collection:" : "Master Administration:"}
              </span>
              <span className="text-slate-600 truncate">
                {isEmployee
                  ? "Capture patient feedback quickly at bedside."
                  : "Manage feedback, users and exports."}
              </span>
            </div>
          </div>
        )}

        {/* Session Expiration Notice */}
        {sessionNotice && (
          <div className="mb-4 p-3.5 bg-amber-50 border border-amber-200 text-amber-900 text-xs rounded-2xl font-medium flex items-center justify-between gap-2 animate-fade-in">
            <div className="flex items-center gap-2">
              <Info className="w-4 h-4 text-amber-600 shrink-0" />
              <span>{sessionNotice}</span>
            </div>
            <button
              type="button"
              onClick={() => setSessionNotice(null)}
              className="text-amber-700 hover:text-amber-900 p-0.5 rounded-lg"
              aria-label="Dismiss notice"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Error Alert */}
        {error && (
          <div className="mb-4 p-3.5 bg-red-50 border border-red-200 text-red-700 text-xs rounded-2xl font-medium flex items-center gap-2 animate-fade-in">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span className="flex-1">{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-red-700 hover:text-red-900 p-0.5"
              aria-label="Dismiss error"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Forced Password Change Form */}
        {mustChangePassword ? (
          <form onSubmit={handlePasswordChangeSubmit} className="space-y-4 animate-fade-in">
            <div className="bg-amber-50 border border-amber-200 p-3.5 rounded-2xl text-xs text-amber-900 flex items-start gap-2.5">
              <KeyRound className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <strong className="block font-bold">Password Change Required</strong>
                <span>For initial security, please choose a new personal password (minimum 8 characters) before proceeding.</span>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                New Password (Min 8 chars)
              </label>
              <div className="relative">
                <input
                  type={showNewPassword ? "text" : "password"}
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full pl-4 pr-11 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
                <button
                  type="button"
                  onClick={() => setShowNewPassword(!showNewPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-1"
                  aria-label={showNewPassword ? "Hide password" : "Show password"}
                >
                  {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                Confirm New Password
              </label>
              <div className="relative">
                <input
                  type={showConfirmPassword ? "text" : "password"}
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full pl-4 pr-11 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-1"
                  aria-label={showConfirmPassword ? "Hide password" : "Show password"}
                >
                  {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={changeLoading}
              className="w-full py-3.5 bg-teal-600 hover:bg-teal-700 active:scale-[0.99] text-white font-bold rounded-2xl shadow-lg transition flex items-center justify-center gap-2 text-sm disabled:opacity-50"
            >
              {changeLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Updating Password...</span>
                </>
              ) : (
                "Set New Password & Continue"
              )}
            </button>
          </form>
        ) : (
          /* Standard Sign In Form */
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                Username / Employee ID
              </label>
              <div className="relative">
                <UserIcon className="w-5 h-5 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  required
                  autoFocus
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder={
                    isEmployee ? "Enter Employee ID or Username" : "Enter Master Username"
                  }
                  className="w-full pl-11 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:bg-white transition"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Password
                </label>
                <button
                  type="button"
                  onClick={() => setForgotModalOpen(true)}
                  className="text-xs text-slate-500 hover:text-slate-800 font-medium underline underline-offset-2 transition"
                >
                  Forgot Password?
                </button>
              </div>

              <div className="relative">
                <Lock className="w-5 h-5 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full pl-11 pr-11 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:bg-white transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-1"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className={`w-full py-3.5 px-4 text-white font-bold rounded-2xl shadow-lg active:scale-[0.99] transition-all flex items-center justify-center gap-2 text-base mt-2 disabled:opacity-50 disabled:cursor-not-allowed ${
                isEmployee
                  ? "bg-gradient-to-r from-teal-700 to-emerald-600 hover:from-teal-800 hover:to-emerald-700 shadow-teal-700/25"
                  : "bg-gradient-to-r from-indigo-700 to-purple-600 hover:from-indigo-800 hover:to-purple-700 shadow-indigo-700/25"
              }`}
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>Authenticating...</span>
                </>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-5 h-5" />
                </>
              )}
            </button>
          </form>
        )}

        {/* Security & Compliance Footer */}
        <div className="mt-6 text-center text-xs text-slate-400 flex items-center justify-center gap-1.5">
          <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>Role-Based Access • Private Storage • Encrypted</span>
        </div>
      </div>

      {/* Forgot Password Modal */}
      {forgotModalOpen && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 flex items-center justify-center p-4 animate-fade-in">
          <div className="w-full max-w-md bg-white rounded-3xl p-6 sm:p-8 shadow-2xl border border-slate-200 relative">
            <button
              type="button"
              onClick={closeForgotModal}
              className="absolute top-5 right-5 text-slate-400 hover:text-slate-600 p-1 rounded-full"
              aria-label="Close dialog"
            >
              <X className="w-5 h-5" />
            </button>

            {isEmployee ? (
              /* Employee Forgot Password Protocol */
              <div>
                <div className="flex items-center gap-2.5 mb-3">
                  <div className="w-10 h-10 rounded-2xl bg-teal-100 text-teal-800 flex items-center justify-center">
                    <Stethoscope className="w-5 h-5" />
                  </div>
                  <div>
                    <span className="text-[10px] font-black tracking-widest text-teal-700 uppercase">
                      Employee Recovery Protocol
                    </span>
                    <h3 className="text-lg font-bold text-slate-900">
                      Password Assistance
                    </h3>
                  </div>
                </div>

                <p className="text-xs text-slate-600 leading-relaxed mb-4">
                  For patient data security and hospital governance, employee bedside credentials cannot be reset via public automated email.
                </p>

                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 mb-4 text-xs space-y-2 text-slate-700">
                  <div className="font-bold text-slate-900">Authorized Recovery Options:</div>
                  <div className="flex items-start gap-2">
                    <span className="font-bold text-teal-700">1.</span>
                    <span>Contact your Nursing Supervisor or Department In-charge.</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="font-bold text-teal-700">2.</span>
                    <span>Call Hospital IT Operations Desk: <strong>Ext. 2321 / 2322</strong></span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="font-bold text-teal-700">3.</span>
                    <span>Submit an administrative ticket request below.</span>
                  </div>
                </div>

                {forgotSubmitted ? (
                  <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-2xl text-xs text-emerald-900 flex items-start gap-2.5 mb-4">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
                    <div>
                      <strong className="block font-bold">Request Dispatched</strong>
                      <span>If an active employee account matches the provided identifier, a supervisor verification notification has been queued. Please inform your shift supervisor.</span>
                    </div>
                  </div>
                ) : (
                  <form onSubmit={handleForgotSubmit} className="space-y-3 mb-4">
                    <div>
                      <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1">
                        Employee ID or Username
                      </label>
                      <input
                        type="text"
                        required
                        value={forgotUsername}
                        onChange={(e) => setForgotUsername(e.target.value)}
                        placeholder="e.g. EMP-1042 or username"
                        className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-500"
                      />
                    </div>
                    <button
                      type="submit"
                      className="w-full py-2.5 bg-teal-700 hover:bg-teal-800 text-white font-bold rounded-xl text-xs transition"
                    >
                      Dispatch Supervisor Reset Notice
                    </button>
                  </form>
                )}

                <button
                  type="button"
                  onClick={closeForgotModal}
                  className="w-full py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl text-xs transition"
                >
                  Return to Sign In
                </button>
              </div>
            ) : (
              /* Master Forgot Password Protocol */
              <div>
                <div className="flex items-center gap-2.5 mb-3">
                  <div className="w-10 h-10 rounded-2xl bg-indigo-100 text-indigo-800 flex items-center justify-center">
                    <ShieldAlert className="w-5 h-5" />
                  </div>
                  <div>
                    <span className="text-[10px] font-black tracking-widest text-indigo-700 uppercase">
                      Security Governance
                    </span>
                    <h3 className="text-lg font-bold text-slate-900">
                      Master Key Recovery
                    </h3>
                  </div>
                </div>

                <p className="text-xs text-slate-600 leading-relaxed mb-4">
                  Master Administrator credentials are securely governed by server-side infrastructure environment variables (<code className="bg-slate-100 px-1 py-0.5 rounded text-indigo-700 font-mono text-[11px]">MASTER_PASSWORD</code>).
                </p>

                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 mb-5 text-xs space-y-2 text-slate-700">
                  <div className="font-bold text-slate-900">Master Recovery Instructions:</div>
                  <div className="flex items-start gap-2">
                    <span className="font-bold text-indigo-700">1.</span>
                    <span>Access your secure deployment server or cloud environment config.</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="font-bold text-indigo-700">2.</span>
                    <span>Update the <code className="bg-slate-200/70 px-1 rounded font-mono text-[10px]">MASTER_PASSWORD</code> secret variable in your server configuration.</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="font-bold text-indigo-700">3.</span>
                    <span>Restart the application service to apply the rotated secret.</span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={closeForgotModal}
                  className="w-full py-2.5 bg-indigo-700 hover:bg-indigo-800 text-white font-bold rounded-xl text-xs transition"
                >
                  Understood & Return
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};