import React, { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { getMe, logout } from "./services/api";
import { initSyncEngine } from "./services/syncEngine";
import { AuthResponse, User } from "./types";
import { AdminView } from "./views/AdminView";
import { LoginView } from "./views/LoginView";
import { StaffView } from "./views/StaffView";

export const App: React.FC = () => {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [isOnline, setIsOnline] = useState<boolean>(navigator.onLine);
  const [pendingSyncCount, setPendingSyncCount] = useState<number>(0);
  const [adminViewMode, setAdminViewMode] = useState<"admin" | "mobile_staff">("admin");

  useEffect(() => {
    // 1. Check network status
    const updateOnlineStatus = () => setIsOnline(navigator.onLine);
    window.addEventListener("online", updateOnlineStatus);
    window.addEventListener("offline", updateOnlineStatus);

    // 2. Start offline background sync engine
    initSyncEngine((count) => setPendingSyncCount(count));

    // 3. Listen for forced logout events
    const handleForcedLogout = () => setCurrentUser(null);
    window.addEventListener("auth:logout", handleForcedLogout);

    // 4. Authenticate current user if token stored
    checkAuth();

    return () => {
      window.removeEventListener("online", updateOnlineStatus);
      window.removeEventListener("offline", updateOnlineStatus);
      window.removeEventListener("auth:logout", handleForcedLogout);
    };
  }, []);

  const checkAuth = async () => {
    try {
      const user = await getMe();
      setCurrentUser(user);
    } catch (_) {
      setCurrentUser(null);
    } finally {
      setLoading(false);
    }
  };

  const handleLoginSuccess = (auth: AuthResponse) => {
    setCurrentUser({
      id: auth.user_id,
      username: auth.username,
      display_name: auth.display_name,
      role: auth.role,
      is_active: true,
      created_at: new Date().toISOString(),
    });
  };

  const handleLogout = async () => {
    await logout();
    setCurrentUser(null);
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-center space-y-3">
          <div className="w-10 h-10 border-4 border-sky-600 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            Loading Hospital System...
          </p>
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return <LoginView onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans antialiased">
      {/* Universal Hospital Header */}
      <Header
        user={currentUser}
        isOnline={isOnline}
        onLogout={handleLogout}
        pendingSyncCount={pendingSyncCount}
      />

      {/* Admin Mode Switcher (Allows Admin to test mobile staff interface) */}
      {(currentUser.role === "ADMIN" || currentUser.role === "MASTER") && (
        <div className="bg-purple-50 border-b border-purple-200 px-4 py-2 text-xs flex items-center justify-between">
          <span className="font-semibold text-purple-900">
            Admin View Switcher:
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setAdminViewMode("admin")}
              className={`py-1 px-3 rounded-lg font-bold transition ${
                adminViewMode === "admin"
                  ? "bg-purple-700 text-white shadow-xs"
                  : "bg-white text-purple-800 border border-purple-300"
              }`}
            >
              Central Admin Dashboard
            </button>
            <button
              onClick={() => setAdminViewMode("mobile_staff")}
              className={`py-1 px-3 rounded-lg font-bold transition ${
                adminViewMode === "mobile_staff"
                  ? "bg-purple-700 text-white shadow-xs"
                  : "bg-white text-purple-800 border border-purple-300"
              }`}
            >
              Simulate Staff Mobile View
            </button>
          </div>
        </div>
      )}

      {/* Role-Based View Rendering */}
      <main className="animate-fade-in">
        {currentUser.role === "STAFF" || ((currentUser.role === "ADMIN" || currentUser.role === "MASTER") && adminViewMode === "mobile_staff") ? (
          <StaffView user={currentUser} isOnline={isOnline} />
        ) : (
          <AdminView currentUser={currentUser} />
        )}
      </main>
    </div>
  );
};
