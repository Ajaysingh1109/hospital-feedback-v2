import React, { useState } from "react";
import { Lock, User as UserIcon, ArrowRight, ShieldCheck, HeartPulse, KeyRound, AlertCircle } from "lucide-react";
import { login, changePassword, setToken } from "../services/api";
import { AuthResponse } from "../types";

interface LoginViewProps {
  onLoginSuccess: (auth: AuthResponse) => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Forced Password Change state (Section 8)
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changeLoading, setChangeLoading] = useState(false);
  const [pendingAuth, setPendingAuth] = useState<AuthResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await login(username, password);
      if (res.must_change_password) {
        setPendingAuth(res);
        setMustChangePassword(true);
      } else {
        onLoginSuccess(res);
      }
    } catch (err: any) {
      setError(err?.message || "Invalid credentials. Please verify your login details.");
    } finally {
      setLoading(false);
    }
  };

  const handlePasswordChangeSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
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

  return (
    <div className="min-h-screen flex flex-col justify-center items-center px-4 py-8 bg-gradient-to-br from-slate-100 via-sky-50 to-teal-50">
      <div className="w-full max-w-md bg-white rounded-3xl shadow-xl border border-slate-200/80 p-6 sm:p-8 animate-fade-in">
        {/* Brand Header */}
        <div className="text-center mb-6">
          <div className="w-16 h-16 rounded-3xl bg-gradient-to-tr from-sky-600 to-teal-500 mx-auto flex items-center justify-center text-white shadow-lg shadow-sky-600/30 mb-3">
            <HeartPulse className="w-9 h-9 stroke-[2.2]" />
          </div>
          <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight">
            Saarthi Hospital Care
          </h1>
          <p className="text-sm font-medium text-slate-500 mt-1">
            AI-Powered Voice Patient Feedback System
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3.5 bg-red-50 border border-red-200 text-red-700 text-xs rounded-2xl font-medium flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Forced Password Change Form (Section 8) */}
        {mustChangePassword ? (
          <form onSubmit={handlePasswordChangeSubmit} className="space-y-4">
            <div className="bg-amber-50 border border-amber-200 p-3.5 rounded-2xl text-xs text-amber-900 flex items-start gap-2.5">
              <KeyRound className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <strong className="block font-bold">Password Change Required</strong>
                <span>For initial security, please choose a new personal password before accessing the system.</span>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                New Password (Min 8 chars)
              </label>
              <input
                type="password"
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                Confirm New Password
              </label>
              <input
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full px-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <button
              type="submit"
              disabled={changeLoading}
              className="w-full py-3.5 bg-teal-600 hover:bg-teal-700 active:scale-[0.99] text-white font-bold rounded-2xl shadow-lg transition flex items-center justify-center gap-2 text-sm disabled:opacity-50"
            >
              {changeLoading ? "Updating Password..." : "SET NEW PASSWORD & CONTINUE"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                Username
              </label>
              <div className="relative">
                <UserIcon className="w-5 h-5 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter username"
                  className="w-full pl-11 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="w-5 h-5 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="w-full pl-11 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white transition"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3.5 px-4 bg-gradient-to-r from-sky-600 to-teal-600 hover:from-sky-700 hover:to-teal-700 active:scale-[0.99] text-white font-bold rounded-2xl shadow-lg shadow-sky-600/25 transition flex items-center justify-center gap-2 text-base mt-2 disabled:opacity-50"
            >
              {loading ? "Authenticating..." : "Sign In to Mobile System"}
              <ArrowRight className="w-5 h-5" />
            </button>
          </form>
        )}

        <div className="mt-6 text-center text-xs text-slate-400 flex items-center justify-center gap-1.5">
          <ShieldCheck className="w-4 h-4 text-emerald-600" />
          <span>Role-Based Access • Private Storage • Encrypted</span>
        </div>
      </div>
    </div>
  );
};
