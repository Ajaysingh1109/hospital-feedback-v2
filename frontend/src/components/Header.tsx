import React from "react";
import { Activity, LogOut, Wifi, WifiOff, Shield } from "lucide-react";
import { User } from "../types";

interface HeaderProps {
  user: User | null;
  isOnline: boolean;
  onLogout: () => void;
  pendingSyncCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  user,
  isOnline,
  onLogout,
  pendingSyncCount = 0,
}) => {
  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200 px-4 py-3 shadow-xs">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-3">
        {/* Brand */}
        <div className="flex items-center gap-2.5">
          <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-sky-600 to-teal-600 flex items-center justify-center text-white shadow-md shadow-sky-600/20">
            <Activity className="w-6 h-6 stroke-[2.5]" />
          </div>
          <div>
            <h1 className="text-base font-bold text-slate-900 tracking-tight leading-tight">
              Hospital Patient Feedback
            </h1>
            <p className="text-[11px] font-medium text-slate-500 flex items-center gap-1.5">
              <span>Saarthi Care Intelligence</span>
              {(user?.role === "ADMIN" || user?.role === "MASTER") && (
                <span className="bg-purple-100 text-purple-700 font-bold px-1.5 py-0.2 rounded-md text-[10px]">
                  {user.role}
                </span>
              )}
            </p>
          </div>
        </div>

        {/* Network & User Actions */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Connection Status Badge (Section 8) */}
          <div
            className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold tracking-wide border transition-all ${
              isOnline
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-amber-100 text-amber-800 border-amber-300 animate-pulse"
            }`}
          >
            {isOnline ? (
              <>
                <Wifi className="w-3.5 h-3.5 text-emerald-600" />
                <span className="hidden sm:inline">ONLINE</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3.5 h-3.5 text-amber-700" />
                <span className="text-[11px] sm:text-xs">
                  OFFLINE — DATA WILL SYNC AUTOMATICALLY
                  {pendingSyncCount > 0 && ` (${pendingSyncCount})`}
                </span>
              </>
            )}
          </div>

          {/* User info & Logout */}
          {user && (
            <div className="flex items-center gap-2 pl-2 border-l border-slate-200">
              <div className="hidden md:block text-right">
                <span className="text-xs font-bold text-slate-800 block leading-tight">
                  {user.display_name}
                </span>
                <span className="text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
                  {user.role}
                </span>
              </div>
              <button
                onClick={onLogout}
                title="Logout"
                className="p-2 text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-xl transition"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
