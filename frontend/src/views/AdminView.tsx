import React, { useEffect, useState } from "react";
import {
  BarChart3,
  Download,
  Filter,
  Search,
  Users,
  Settings,
  Shield,
  FileSpreadsheet,
  RefreshCw,
  Eye,
  Trash2,
  CheckCircle,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Edit2,
  Play,
  Calendar,
  Layers,
  Sparkles,
  TrendingUp,
  Clock,
  PlusCircle,
  Volume2,
  VolumeX,
} from "lucide-react";
import {
  bulkDeleteFeedback,
  correctFeedback,
  createUser,
  deleteFeedback,
  downloadExcel,
  fetchAdminAnalytics,
  fetchAdminFeedback,
  fetchAudioBlob,
  fetchAuditLogs,
  fetchHODMappings,
  fetchMasterData,
  fetchSettings,
  fetchUsers,
  getFeedbackDetail,
  triggerRetentionPurge,
  updateHODMapping,
  createHODMapping,
  restoreDefaultHODMappings,
  updateSetting,
  updateUser,
  resetUserPassword,
} from "../services/api";
import {
  AnalyticsSummary,
  FeedbackRecord,
  MasterData,
  User as UserType,
} from "../types";

interface AdminViewProps {
  currentUser: UserType;
}

export const AdminView: React.FC<AdminViewProps> = ({ currentUser }) => {
  const [activeTab, setActiveTab] = useState<"dashboard" | "feedback" | "users" | "master" | "settings" | "audit">("dashboard");

  // Analytics & Feedback
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [feedbacks, setFeedbacks] = useState<FeedbackRecord[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedDept, setSelectedDept] = useState<string>("");
  const [selectedHOD, setSelectedHOD] = useState<string>("");
  const [selectedStaff, setSelectedStaff] = useState<string>("");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");

  // Detail Modal & Correction
  const [selectedFeedback, setSelectedFeedback] = useState<FeedbackRecord | null>(null);
  const [showDetailModal, setShowDetailModal] = useState<boolean>(false);
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioLoading, setAudioLoading] = useState<boolean>(false);
  const [audioError, setAudioError] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({
    department: "",
    complaint_summary: "",
    priority: "",
    location: "",
  });

  // Master Data & Users
  const [masterData, setMasterData] = useState<MasterData | null>(null);
  const [usersList, setUsersList] = useState<UserType[]>([]);
  const [hodMappings, setHodMappings] = useState<any[]>([]);
  const [editingHodId, setEditingHodId] = useState<number | null>(null);
  const [editingHodName, setEditingHodName] = useState<string>("");
  const [showAddHodModal, setShowAddHodModal] = useState<boolean>(false);
  const [newHodDept, setNewHodDept] = useState<string>("");
  const [newHodName, setNewHodName] = useState<string>("");
  const [systemSettings, setSystemSettings] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);

  // User Create Modal
  const [showNewUserModal, setShowNewUserModal] = useState<boolean>(false);
  const [newUserData, setNewUserData] = useState({
    username: "",
    display_name: "",
    password: "",
    role: "STAFF",
  });

  // Data Retention & Delete States
  const [selectedFeedbackIds, setSelectedFeedbackIds] = useState<string[]>([]);
  const [deleteModal, setDeleteModal] = useState<{
    isOpen: boolean;
    isBulk: boolean;
    targetId?: string;
    count: number;
  }>({
    isOpen: false,
    isBulk: false,
    count: 0,
  });
  const [isDeleting, setIsDeleting] = useState<boolean>(false);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    setLoading(true);
    try {
      const [anRes, mdRes] = await Promise.all([
        fetchAdminAnalytics(),
        fetchMasterData(),
      ]);
      setAnalytics(anRes);
      setMasterData(mdRes);
      loadFeedbackList(1);
    } catch (e) {
      console.error("Failed to load admin data:", e);
    } finally {
      setLoading(false);
    }
  };

  const loadFeedbackList = async (page: number = 1) => {
    setLoading(true);
    try {
      const res = await fetchAdminFeedback({
        search: searchQuery || undefined,
        department: selectedDept || undefined,
        hod: selectedHOD || undefined,
        staff: selectedStaff || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        page,
        page_size: 15,
      });
      setFeedbacks(res.items);
      setTotalCount(res.total);
      setCurrentPage(res.page);
      setTotalPages(res.total_pages);
    } catch (e) {
      console.error("Failed to load feedback list:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadFeedbackList(1);
  };

  const handleExportExcel = async () => {
    try {
      await downloadExcel({
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        department: selectedDept || undefined,
        hod: selectedHOD || undefined,
        staff: selectedStaff || undefined,
      });
    } catch (e) {
      alert("Failed to export Excel report. Please verify permissions.");
    }
  };

  const handleOpenDetail = async (fb: FeedbackRecord) => {
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    setAudioLoading(false);
    setAudioError(null);
    setSelectedFeedback(fb);
    setEditForm({
      department: fb.department,
      complaint_summary: fb.complaint_summary,
      priority: fb.priority,
      location: fb.location || "",
    });
    setIsEditing(false);
    setShowDetailModal(true);
  };

  const handleCloseDetail = () => {
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      setAudioUrl(null);
    }
    setAudioLoading(false);
    setAudioError(null);
    setShowDetailModal(false);
  };

  const handleSaveCorrection = async () => {
    if (!selectedFeedback) return;
    try {
      const updated = await correctFeedback(selectedFeedback.feedback_id, editForm);
      setSelectedFeedback(updated);
      setIsEditing(false);
      loadFeedbackList(currentPage);
      loadDashboardData();
    } catch (e) {
      alert("Failed to save correction.");
    }
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      const allIds = feedbacks.map((fb) => fb.id);
      setSelectedFeedbackIds(Array.from(new Set([...selectedFeedbackIds, ...allIds])));
    } else {
      const currentIds = new Set(feedbacks.map((fb) => fb.id));
      setSelectedFeedbackIds(selectedFeedbackIds.filter((id) => !currentIds.has(id)));
    }
  };

  const handleToggleSelectOne = (id: string) => {
    setSelectedFeedbackIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleDeleteFeedback = (id: string) => {
    setDeleteModal({
      isOpen: true,
      isBulk: false,
      targetId: id,
      count: 1,
    });
  };

  const handleExecuteDelete = async () => {
    if (!deleteModal.isOpen) return;
    setIsDeleting(true);
    try {
      if (deleteModal.isBulk) {
        await bulkDeleteFeedback(selectedFeedbackIds);
        setSelectedFeedbackIds([]);
      } else if (deleteModal.targetId) {
        await deleteFeedback(deleteModal.targetId);
        setSelectedFeedbackIds((prev) => prev.filter((id) => id !== deleteModal.targetId));
      }
      setDeleteModal({ isOpen: false, isBulk: false, count: 0 });
      setShowDetailModal(false);
      loadFeedbackList(currentPage);
      loadDashboardData();
    } catch (err: any) {
      alert(err?.message || "Failed to permanently delete feedback record.");
    } finally {
      setIsDeleting(false);
    }
  };

  const handleTriggerPurge = async () => {
    if (!confirm("Run 12-hour retention cleanup now? Any records older than 12 hours will be permanently deleted.")) return;
    try {
      const res = await triggerRetentionPurge();
      alert(`Retention Purge Complete!\nPurged records: ${res.purged_count}\nEligible: ${res.total_eligible}`);
      loadDashboardData();
      loadFeedbackList(1);
    } catch (err: any) {
      alert("Failed to run retention purge: " + (err?.message || err));
    }
  };

  // User management actions
  const loadUsers = async () => {
    const list = await fetchUsers();
    setUsersList(list);
  };

  const handleToggleUserActive = async (u: UserType) => {
    try {
      await updateUser(u.id, { is_active: !u.is_active });
      loadUsers();
    } catch (e) {
      alert("Failed to update user status.");
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createUser(newUserData);
      setShowNewUserModal(false);
      setNewUserData({ username: "", display_name: "", password: "", role: "STAFF" });
      loadUsers();
    } catch (e: any) {
      alert(e?.message || "Failed to create user.");
    }
  };

  // Master data & settings actions
  const loadMasterDataTab = async () => {
    const mappings = await fetchHODMappings();
    setHodMappings(mappings);
  };

  const handleSaveHod = async (id: number) => {
    if (!editingHodName.trim()) return;
    try {
      await updateHODMapping(id, editingHodName.trim());
      setEditingHodId(null);
      loadMasterDataTab();
    } catch (e: any) {
      alert("Failed to update HOD: " + (e?.message || e));
    }
  };

  const handleAddHodMapping = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newHodDept.trim() || !newHodName.trim()) return;
    try {
      await createHODMapping(newHodDept.trim(), newHodName.trim());
      setShowAddHodModal(false);
      setNewHodDept("");
      setNewHodName("");
      loadMasterDataTab();
    } catch (e: any) {
      alert("Failed to add HOD mapping: " + (e?.message || e));
    }
  };

  const handleRestoreDefaultHods = async () => {
    if (!confirm("Restore all departments to canonical default HOD assignments?")) return;
    try {
      await restoreDefaultHODMappings();
      loadMasterDataTab();
    } catch (e: any) {
      alert("Failed to restore default HODs: " + (e?.message || e));
    }
  };

  const loadSettingsTab = async () => {
    const sets = await fetchSettings();
    setSystemSettings(sets);
  };

  const loadAuditLogsTab = async () => {
    const logs = await fetchAuditLogs(100);
    setAuditLogs(logs);
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      {/* Master Brand Header (Section 6 & 24) */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-2 border-b border-slate-200">
        <div>
          <span className="text-[10px] font-black uppercase tracking-widest text-teal-700 block">
            Powered by Saarthi-One
          </span>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">
            FEEDBACK MAC — Master Dashboard
          </h1>
          <p className="text-xs text-slate-500 font-medium mt-0.5">
            Centralized Patient Feedback Governance, Analytics & 11-Column Excel Export
          </p>
        </div>
      </div>

      {/* Top Navigation Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-white p-2.5 rounded-2xl border border-slate-200 shadow-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => setActiveTab("dashboard")}
            className={`py-2 px-3.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === "dashboard"
                ? "bg-sky-600 text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            ANALYTICS
          </button>

          <button
            onClick={() => {
              setActiveTab("feedback");
              loadFeedbackList(1);
            }}
            className={`py-2 px-3.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === "feedback"
                ? "bg-sky-600 text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <Layers className="w-4 h-4" />
            ALL FEEDBACK ({totalCount})
          </button>

          <button
            onClick={() => {
              setActiveTab("users");
              loadUsers();
            }}
            className={`py-2 px-3.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === "users"
                ? "bg-sky-600 text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <Users className="w-4 h-4" />
            USERS & ROLES
          </button>

          <button
            onClick={() => {
              setActiveTab("master");
              loadMasterDataTab();
            }}
            className={`py-2 px-3.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === "master"
                ? "bg-sky-600 text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <Shield className="w-4 h-4" />
            HOD MAPPINGS
          </button>

          <button
            onClick={() => {
              setActiveTab("settings");
              loadSettingsTab();
            }}
            className={`py-2 px-3.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === "settings"
                ? "bg-sky-600 text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <Settings className="w-4 h-4" />
            SETTINGS & RETENTION
          </button>

          <button
            onClick={() => {
              setActiveTab("audit");
              loadAuditLogsTab();
            }}
            className={`py-2 px-3.5 rounded-xl text-xs font-bold transition flex items-center gap-1.5 ${
              activeTab === "audit"
                ? "bg-sky-600 text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            AUDIT TRAIL
          </button>
        </div>

        {/* Retention Indicator & Global Export Excel Button (Section 37 & 38) */}
        <div className="flex items-center gap-2.5">
          <span className="py-2 px-3 bg-amber-50 text-amber-900 border border-amber-300 rounded-xl text-xs font-extrabold flex items-center gap-1.5 shadow-xs">
            <Clock className="w-4 h-4 text-amber-600" />
            Retention: 12 hours
          </span>
          <button
            onClick={handleExportExcel}
            className="py-2.5 px-4 bg-emerald-600 hover:bg-emerald-700 active:scale-[0.99] text-white font-extrabold text-xs rounded-xl shadow-sm transition flex items-center gap-2"
          >
            <FileSpreadsheet className="w-4 h-4" />
            EXPORT EXCEL (.XLSX)
          </button>
        </div>
      </div>

      {/* 12-Hour Retention Warning Banner */}
      <div className="bg-amber-50 border border-amber-300 rounded-2xl p-4 flex items-start gap-3 text-amber-900 shadow-xs">
        <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="text-xs space-y-1">
          <p className="font-extrabold text-amber-950">
            ⚠️ Feedback data is automatically deleted after 12 hours. Export required data before the retention period expires.
          </p>
          <p className="text-amber-800 opacity-90">
            Complaints, audio recordings, transcripts, and patient details are permanently wiped 12 hours post-submission in strict accordance with hospital data governance.
          </p>
        </div>
      </div>

      {/* ==================================================================== */}
      {/* 1. ANALYTICS DASHBOARD (SECTION 31 & 40) */}
      {/* ==================================================================== */}
      {activeTab === "dashboard" && analytics && (
        <div className="space-y-6 animate-fade-in">
          {/* Metrics Summary Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3.5">
            <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
              <span className="text-[11px] font-bold text-slate-500 uppercase">Total Feedback</span>
              <span className="text-2xl font-black text-slate-900 block mt-1">{analytics.total_feedback}</span>
              <span className="text-[10px] text-sky-600 font-semibold">Central Database</span>
            </div>

            <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
              <span className="text-[11px] font-bold text-slate-500 uppercase">Today</span>
              <span className="text-2xl font-black text-emerald-600 block mt-1">{analytics.today_count}</span>
              <span className="text-[10px] text-slate-400 font-semibold">Current Shift</span>
            </div>

            <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
              <span className="text-[11px] font-bold text-slate-500 uppercase">This Week</span>
              <span className="text-2xl font-black text-sky-700 block mt-1">{analytics.this_week_count}</span>
              <span className="text-[10px] text-slate-400 font-semibold">Last 7 Days</span>
            </div>

            <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
              <span className="text-[11px] font-bold text-slate-500 uppercase">This Month</span>
              <span className="text-2xl font-black text-slate-900 block mt-1">{analytics.this_month_count}</span>
              <span className="text-[10px] text-slate-400 font-semibold">Monthly Aggregation</span>
            </div>

            <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
              <span className="text-[11px] font-bold text-slate-500 uppercase">Positive Sentiment</span>
              <span className="text-2xl font-black text-teal-600 block mt-1">{analytics.sentiment_counts["Positive Feedback"] || 0}</span>
              <span className="text-[10px] text-teal-600 font-semibold">Appreciations</span>
            </div>

            <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
              <span className="text-[11px] font-bold text-slate-500 uppercase">Complaints</span>
              <span className="text-2xl font-black text-amber-600 block mt-1">{analytics.sentiment_counts["Negative / Complaints"] || 0}</span>
              <span className="text-[10px] text-amber-600 font-semibold">Action Required</span>
            </div>
          </div>

          {/* Breakdown Charts Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Department-wise Feedback Breakdown */}
            <div className="bg-white p-5 rounded-3xl border border-slate-200 shadow-xs space-y-3">
              <h3 className="text-sm font-extrabold text-slate-900 flex items-center justify-between">
                <span>Department-Wise Feedback</span>
                <span className="text-xs font-normal text-slate-400">Total volume</span>
              </h3>
              <div className="space-y-2 pt-1">
                {Object.entries(analytics.department_counts).map(([dept, count]) => {
                  const pct = Math.round((count / Math.max(analytics.total_feedback, 1)) * 100);
                  return (
                    <div key={dept} className="space-y-1">
                      <div className="flex justify-between text-xs font-semibold text-slate-700">
                        <span>{dept}</span>
                        <span>{count} ({pct}%)</span>
                      </div>
                      <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-sky-500 to-teal-500 rounded-full"
                          style={{ width: `${Math.max(pct, 4)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* HOD-wise Distribution */}
            <div className="bg-white p-5 rounded-3xl border border-slate-200 shadow-xs space-y-3">
              <h3 className="text-sm font-extrabold text-slate-900 flex items-center justify-between">
                <span>Fixed HOD Distribution (Deterministic)</span>
                <span className="text-xs font-normal text-slate-400">Escalation ownership</span>
              </h3>
              <div className="space-y-2 pt-1">
                {Object.entries(analytics.hod_counts).map(([hod, count]) => {
                  const pct = Math.round((count / Math.max(analytics.total_feedback, 1)) * 100);
                  return (
                    <div key={hod} className="space-y-1">
                      <div className="flex justify-between text-xs font-semibold text-slate-700">
                        <span className="font-bold text-sky-900">{hod}</span>
                        <span>{count} ({pct}%)</span>
                      </div>
                      <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-teal-500 to-emerald-500 rounded-full"
                          style={{ width: `${Math.max(pct, 4)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* 2. ALL FEEDBACK TABLE WITH SEARCH & FILTER (SECTION 32, 33, 34) */}
      {/* ==================================================================== */}
      {activeTab === "feedback" && (
        <div className="space-y-4 animate-fade-in">
          {/* Search & Filter Toolbar */}
          <form onSubmit={handleSearchSubmit} className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs space-y-3">
            <div className="flex flex-wrap items-center gap-2.5">
              <div className="flex-1 min-w-[220px] relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search UHID, Patient Name, Feedback ID, Consultant, Keyword..."
                  className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-sky-500 focus:outline-none"
                />
              </div>

              {/* Department Filter */}
              <select
                value={selectedDept}
                onChange={(e) => setSelectedDept(e.target.value)}
                className="py-2 px-3 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium"
              >
                <option value="">All Departments</option>
                {masterData?.departments.map((d) => (
                  <option key={d.id} value={d.name}>{d.name}</option>
                ))}
              </select>

              {/* HOD Filter */}
              <select
                value={selectedHOD}
                onChange={(e) => setSelectedHOD(e.target.value)}
                className="py-2 px-3 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium"
              >
                <option value="">All HODs</option>
                <option value="Asha Ma'am">Asha Ma'am</option>
                <option value="Tanveer Sir">Tanveer Sir</option>
                <option value="Reshmi Ma'am">Reshmi Ma'am</option>
                <option value="Vijay Sir">Vijay Sir</option>
                <option value="Valay Sir">Valay Sir</option>
              </select>

              <button
                type="submit"
                className="py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs rounded-xl shadow-xs transition"
              >
                Apply Filters
              </button>

              {selectedFeedbackIds.length > 0 && (
                <button
                  type="button"
                  onClick={() => setDeleteModal({ isOpen: true, isBulk: true, count: selectedFeedbackIds.length })}
                  className="py-2 px-3.5 bg-red-600 hover:bg-red-700 active:scale-[0.99] text-white font-extrabold text-xs rounded-xl shadow-xs transition flex items-center gap-1.5 ml-auto"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  Delete Selected ({selectedFeedbackIds.length})
                </button>
              )}
            </div>
          </form>

          {/* Feedback Data Table (Section 32) */}
          <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                    <th className="py-3 px-3 w-8 text-center">
                      <input
                        type="checkbox"
                        checked={feedbacks.length > 0 && feedbacks.every((fb) => selectedFeedbackIds.includes(fb.id))}
                        onChange={(e) => handleSelectAll(e.target.checked)}
                        className="rounded border-slate-300 text-sky-600 focus:ring-sky-500 cursor-pointer"
                        title="Select All"
                      />
                    </th>
                    <th className="py-3 px-4">Feedback ID</th>
                    <th className="py-3 px-3">Date / Expiry</th>
                    <th className="py-3 px-4">UHID</th>
                    <th className="py-3 px-4">Patient Name</th>
                    <th className="py-3 px-3">Department</th>
                    <th className="py-3 px-3">HOD</th>
                    <th className="py-3 px-3">Staff Name</th>
                    <th className="py-3 px-4">Complaint Summary</th>
                    <th className="py-3 px-2 text-center">Priority</th>
                    <th className="py-3 px-3 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700 font-medium">
                  {feedbacks.length === 0 ? (
                    <tr>
                      <td colSpan={11} className="py-8 text-center text-slate-400">
                        No feedback records match the current filters.
                      </td>
                    </tr>
                  ) : (
                    feedbacks.map((fb) => (
                      <tr
                        key={fb.id}
                        className="hover:bg-sky-50/50 cursor-pointer transition"
                        onClick={() => handleOpenDetail(fb)}
                      >
                        <td className="py-3 px-3 text-center" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selectedFeedbackIds.includes(fb.id)}
                            onChange={() => handleToggleSelectOne(fb.id)}
                            className="rounded border-slate-300 text-sky-600 focus:ring-sky-500 cursor-pointer"
                          />
                        </td>
                        <td className="py-3 px-4 font-mono font-bold text-sky-700">
                          <div className="flex items-center gap-1.5">
                            <span>{fb.feedback_id}</span>
                            {fb.has_audio && !fb.is_audio_expired && (
                              <span title="Voice recording available for ground truth review">
                                <Volume2 className="w-3.5 h-3.5 text-sky-600" />
                              </span>
                            )}
                            {fb.is_audio_expired && (
                              <span title="Voice recording expired & permanently deleted">
                                <VolumeX className="w-3.5 h-3.5 text-slate-300" />
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-3 whitespace-nowrap text-slate-500">
                          <div>{fb.date_str} {fb.time_str}</div>
                          {fb.retention_expiry_str && (
                            <div className="text-[10px] text-amber-700 font-semibold bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200 inline-block mt-0.5">
                              Expires: {fb.retention_expiry_str}
                            </div>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono font-semibold text-slate-900">{fb.uhid}</td>
                        <td className="py-3 px-4 font-bold text-slate-900">{fb.patient_name}</td>
                        <td className="py-3 px-3">
                          <span className="bg-sky-50 text-sky-800 px-2 py-0.5 rounded-md font-semibold">
                            {fb.department}
                          </span>
                        </td>
                        <td className="py-3 px-3 font-semibold text-teal-800">{fb.hod_name}</td>
                        <td className="py-3 px-3 text-slate-600">{fb.staff_name}</td>
                        <td className="py-3 px-4 max-w-xs truncate text-slate-500">
                          {fb.complaint_summary || "Not Provided"}
                        </td>
                        <td className="py-3 px-2 text-center">
                          <span className={`px-2 py-0.5 rounded-md font-bold text-[10px] ${
                            fb.priority === "Critical" || fb.priority === "High"
                              ? "bg-red-100 text-red-700"
                              : fb.priority === "Medium"
                              ? "bg-amber-100 text-amber-700"
                              : "bg-slate-100 text-slate-600"
                          }`}>
                            {fb.priority}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-center" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-center gap-1">
                            <button
                              onClick={() => handleOpenDetail(fb)}
                              className="p-1.5 hover:bg-sky-100 text-sky-700 rounded-lg transition"
                              title="View / Correct"
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDeleteFeedback(fb.id)}
                              className="p-1.5 hover:bg-red-100 text-red-600 rounded-lg transition"
                              title="Delete Permanently"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-t border-slate-200 text-xs text-slate-600">
              <span>Showing Page {currentPage} of {totalPages} ({totalCount} items)</span>
              <div className="flex items-center gap-1.5">
                <button
                  disabled={currentPage <= 1}
                  onClick={() => loadFeedbackList(currentPage - 1)}
                  className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  disabled={currentPage >= totalPages}
                  onClick={() => loadFeedbackList(currentPage + 1)}
                  className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 disabled:opacity-40"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* 3. USER MANAGEMENT TAB (SECTION 4) */}
      {/* ==================================================================== */}
      {activeTab === "users" && (
        <div className="space-y-4 animate-fade-in">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-extrabold text-slate-900">Hospital User Accounts</h3>
              <p className="text-xs text-slate-500">Master Administrator & Staff Accounts</p>
            </div>
            <button
              onClick={() => setShowNewUserModal(true)}
              className="py-2.5 px-4 bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs rounded-xl shadow-xs transition"
            >
              + Add Staff Account
            </button>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-4">Username</th>
                  <th className="py-3 px-4">Display Name</th>
                  <th className="py-3 px-3">Role</th>
                  <th className="py-3 px-3">Status</th>
                  <th className="py-3 px-3">Last Login</th>
                  <th className="py-3 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {usersList.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50 font-medium">
                    <td className="py-3 px-4 font-mono font-bold text-slate-900">{u.username}</td>
                    <td className="py-3 px-4 text-slate-800">{u.display_name}</td>
                    <td className="py-3 px-3">
                      <span className={`px-2 py-0.5 rounded-md font-bold text-[10px] ${
                        u.role === "ADMIN" || (u.role as string) === "MASTER" ? "bg-purple-100 text-purple-700" : "bg-sky-100 text-sky-700"
                      }`}>
                        {u.role}
                      </span>
                    </td>
                    <td className="py-3 px-3">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        u.is_active ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-700"
                      }`}>
                        {u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-slate-500 font-mono text-[11px]">
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}
                    </td>
                    <td className="py-3 px-3 text-right space-x-2">
                      <button
                        onClick={async () => {
                          const newPass = prompt(`Enter new password for ${u.username} (min 8 characters):`);
                          if (newPass && newPass.length >= 8) {
                            try {
                              await resetUserPassword(u.id, newPass);
                              alert(`Password reset for ${u.username}. User must change password on next login.`);
                            } catch (_) {
                              alert("Failed to reset password.");
                            }
                          }
                        }}
                        className="py-1 px-2.5 rounded-lg text-xs font-semibold text-sky-700 hover:bg-sky-50 border border-slate-200"
                      >
                        Reset Password
                      </button>
                      {u.role !== "ADMIN" && (u.role as string) !== "MASTER" && u.id !== currentUser.id && (
                        <button
                          onClick={() => handleToggleUserActive(u)}
                          className={`py-1 px-2.5 rounded-lg text-xs font-semibold ${
                            u.is_active ? "text-red-600 hover:bg-red-50" : "text-emerald-600 hover:bg-emerald-50"
                          }`}
                        >
                          {u.is_active ? "Deactivate" : "Activate"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* New User Account Modal */}
          {showNewUserModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
              <div className="bg-white w-full max-w-md rounded-3xl shadow-2xl border border-slate-200 overflow-hidden p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <h3 className="text-base font-bold text-slate-900">Create New Staff User</h3>
                  <button
                    onClick={() => setShowNewUserModal(false)}
                    className="text-slate-400 hover:text-slate-600 p-1 rounded-lg text-sm font-bold"
                  >
                    ✕
                  </button>
                </div>

                <form onSubmit={handleCreateUser} className="space-y-3.5">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                      Staff Username
                    </label>
                    <input
                      type="text"
                      required
                      value={newUserData.username}
                      onChange={(e) => setNewUserData({ ...newUserData, username: e.target.value })}
                      placeholder="e.g. nurse_priya"
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 text-xs font-medium focus:ring-2 focus:ring-sky-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                      Staff Full Name / Display Name
                    </label>
                    <input
                      type="text"
                      required
                      value={newUserData.display_name}
                      onChange={(e) => setNewUserData({ ...newUserData, display_name: e.target.value })}
                      placeholder="e.g. Priya Sharma (Staff Nurse)"
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 text-xs font-medium focus:ring-2 focus:ring-sky-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                      Initial Password (Min 8 chars)
                    </label>
                    <input
                      type="password"
                      required
                      minLength={8}
                      value={newUserData.password}
                      onChange={(e) => setNewUserData({ ...newUserData, password: e.target.value })}
                      placeholder="••••••••••••"
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 text-xs font-medium focus:ring-2 focus:ring-sky-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                      Role / Permission
                    </label>
                    <select
                      value={newUserData.role}
                      onChange={(e) => setNewUserData({ ...newUserData, role: e.target.value })}
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 text-xs font-bold focus:ring-2 focus:ring-sky-500 focus:outline-none"
                    >
                      <option value="STAFF">STAFF (Bedside Feedback Collection)</option>
                      <option value="ADMIN">ADMIN (Full Administrative Access)</option>
                    </select>
                  </div>

                  <div className="flex gap-2 pt-2">
                    <button
                      type="submit"
                      className="flex-1 py-2.5 bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs rounded-xl shadow-xs transition"
                    >
                      Create Account
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowNewUserModal(false)}
                      className="py-2.5 px-4 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl transition"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ==================================================================== */}
      {/* 4. HOD MAPPINGS TAB (CONFIGURABLE MASTER DATA) */}
      {/* ==================================================================== */}
      {activeTab === "master" && (
        <div className="space-y-4 animate-fade-in">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-extrabold text-slate-900">Department → HOD Master Configuration</h3>
              <p className="text-xs text-slate-500">
                Master can update HOD assignments, add custom departments, or restore canonical defaults without code redeployment.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleRestoreDefaultHods}
                className="py-2 px-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl transition flex items-center gap-1.5"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Restore Defaults
              </button>
              <button
                type="button"
                onClick={() => setShowAddHodModal(true)}
                className="py-2 px-3.5 bg-teal-700 hover:bg-teal-800 text-white font-bold text-xs rounded-xl shadow-xs transition flex items-center gap-1.5"
              >
                <PlusCircle className="w-3.5 h-3.5" />
                Add Department HOD
              </button>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-4">Department</th>
                  <th className="py-3 px-4">Assigned HOD</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {hodMappings.map((m) => {
                  const isEditing = editingHodId === m.id;
                  return (
                    <tr key={m.id} className="hover:bg-slate-50 transition-colors">
                      <td className="py-3 px-4 font-bold text-slate-900">{m.department_name}</td>
                      <td className="py-3 px-4">
                        {isEditing ? (
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={editingHodName}
                              onChange={(e) => setEditingHodName(e.target.value)}
                              placeholder="e.g. Tanveer Sir"
                              className="px-2.5 py-1.5 bg-slate-50 border border-teal-500 rounded-lg text-xs font-bold text-teal-900 focus:outline-none focus:ring-1 focus:ring-teal-500"
                            />
                            <button
                              type="button"
                              onClick={() => handleSaveHod(m.id)}
                              className="px-2.5 py-1.5 bg-teal-700 hover:bg-teal-800 text-white font-bold text-xs rounded-lg shadow-2xs"
                            >
                              Save
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingHodId(null)}
                              className="px-2 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 font-bold text-xs rounded-lg"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <span className="font-extrabold text-teal-800 bg-teal-50 px-2.5 py-1 rounded-lg border border-teal-200">
                            {m.hod_name}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${
                            m.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          {m.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        {!isEditing && (
                          <button
                            type="button"
                            onClick={() => {
                              setEditingHodId(m.id);
                              setEditingHodName(m.hod_name);
                            }}
                            className="py-1 px-2.5 bg-slate-100 hover:bg-teal-50 hover:text-teal-700 text-slate-600 font-bold text-xs rounded-lg transition"
                          >
                            Edit HOD
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Add Department HOD Modal */}
          {showAddHodModal && (
            <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-xs z-50 flex items-center justify-center p-4 animate-fade-in">
              <div className="w-full max-w-md bg-white rounded-3xl p-6 shadow-2xl border border-slate-200">
                <h3 className="text-base font-bold text-slate-900 mb-1">Add Department HOD Assignment</h3>
                <p className="text-xs text-slate-500 mb-4">Assign an HOD to a hospital department.</p>

                <form onSubmit={handleAddHodMapping} className="space-y-3.5">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                      Department Name
                    </label>
                    <input
                      type="text"
                      required
                      value={newHodDept}
                      onChange={(e) => setNewHodDept(e.target.value)}
                      placeholder="e.g. Oncology, Cardiology, Security"
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-500"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                      Assigned HOD Name
                    </label>
                    <input
                      type="text"
                      required
                      value={newHodName}
                      onChange={(e) => setNewHodName(e.target.value)}
                      placeholder="e.g. Dr. Rajesh Sir, Asha Ma'am"
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-teal-500"
                    />
                  </div>

                  <div className="flex gap-2 pt-2">
                    <button
                      type="submit"
                      className="flex-1 py-2.5 bg-teal-700 hover:bg-teal-800 text-white font-bold rounded-xl text-xs shadow-sm transition"
                    >
                      Save HOD Assignment
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowAddHodModal(false)}
                      className="py-2.5 px-4 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-xl text-xs transition"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ==================================================================== */}
      {/* 5. SETTINGS & RETENTION TAB (SECTION 44) */}
      {/* ==================================================================== */}
      {activeTab === "settings" && (
        <div className="space-y-4 animate-fade-in">
          <div>
            <h3 className="text-base font-extrabold text-slate-900">Hospital System & Retention Settings</h3>
            <p className="text-xs text-slate-500">Configure recording retention policy and consent notice.</p>
          </div>

          <div className="bg-white rounded-3xl border border-slate-200 p-6 space-y-5">
            {systemSettings.map((s) => (
              <div key={s.key} className="space-y-1.5 pb-4 border-b border-slate-100 last:border-b-0">
                <span className="font-bold text-sm text-slate-800 block capitalize">
                  {s.key.replace(/_/g, " ")}
                </span>
                <p className="text-xs text-slate-500">{s.description}</p>
                <div className="flex items-center gap-3 pt-1">
                  <input
                    type="text"
                    defaultValue={s.value}
                    onBlur={(e) => updateSetting(s.key, e.target.value)}
                    className="flex-1 max-w-lg px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-mono"
                  />
                  <span className="text-[11px] text-emerald-600 font-semibold">Auto-saves on blur</span>
                </div>
              </div>
            ))}
          </div>

          {/* Automated 12-Hour Data Retention & Cleanup Card */}
          <div className="bg-white rounded-3xl border border-amber-200 p-6 space-y-4 shadow-xs">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-sm font-extrabold text-slate-900 flex items-center gap-2">
                  <Clock className="w-4 h-4 text-amber-600" />
                  Automated 12-Hour Data Retention Policy
                </h4>
                <p className="text-xs text-slate-500 mt-1">
                  Enforces strict patient privacy: all patient recordings, transcripts, AI summaries, and identifiers are permanently purged after 12 hours.
                </p>
              </div>
              <span className="py-1 px-3 bg-emerald-100 text-emerald-800 rounded-full text-xs font-bold">
                Background Worker Active (Runs every 10 min)
              </span>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-slate-100">
              <span className="text-xs text-slate-600">
                Retention Window: <strong className="text-slate-900">12 Hours Fixed</strong>
              </span>
              <button
                type="button"
                onClick={handleTriggerPurge}
                className="py-2 px-4 bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs rounded-xl shadow-xs transition flex items-center gap-1.5"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Run Retention Purge Now
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* 6. AUDIT TRAIL TAB (SECTION 46) */}
      {/* ==================================================================== */}
      {activeTab === "audit" && (
        <div className="space-y-4 animate-fade-in">
          <div>
            <h3 className="text-base font-extrabold text-slate-900">System Audit Trail</h3>
            <p className="text-xs text-slate-500">Immutable log of logins, submissions, corrections, and exports.</p>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold uppercase tracking-wider text-[11px]">
                  <th className="py-3 px-4">Timestamp</th>
                  <th className="py-3 px-3">Actor</th>
                  <th className="py-3 px-3">Action</th>
                  <th className="py-3 px-3">Entity</th>
                  <th className="py-3 px-4">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-medium">
                {auditLogs.map((log) => (
                  <tr key={log.id} className="hover:bg-slate-50">
                    <td className="py-2.5 px-4 text-slate-500 font-mono text-[11px]">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 font-bold text-slate-800">{log.actor_username}</td>
                    <td className="py-2.5 px-3">
                      <span className="bg-slate-100 text-slate-800 px-2 py-0.5 rounded font-mono text-[10px]">
                        {log.action}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-slate-600">{log.entity_type} {log.entity_id && `(${log.entity_id})`}</td>
                    <td className="py-2.5 px-4 max-w-sm truncate text-slate-500 font-mono text-[10px]">
                      {log.details_json || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* FEEDBACK DETAIL & CORRECTION MODAL (SECTION 35 & 36) */}
      {/* ==================================================================== */}
      {showDetailModal && selectedFeedback && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in overflow-y-auto">
          <div className="bg-white w-full max-w-3xl rounded-3xl shadow-2xl border border-slate-200 overflow-hidden my-6">
            {/* Modal Header */}
            <div className="bg-sky-700 p-5 text-white flex items-center justify-between">
              <div>
                <span className="text-xs font-mono font-bold text-sky-200">
                  {selectedFeedback.feedback_id}
                </span>
                <h3 className="text-lg font-bold">
                  {selectedFeedback.patient_name} <span className="font-mono text-sm opacity-80">(UHID: {selectedFeedback.uhid})</span>
                </h3>
              </div>
              <button
                onClick={handleCloseDetail}
                className="text-white hover:bg-white/20 p-2 rounded-xl transition font-bold"
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-5 max-h-[80vh] overflow-y-auto">
              {/* Meta Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-50 p-4 rounded-2xl border border-slate-200 text-xs">
                <div>
                  <span className="text-slate-400 block">Date & Time</span>
                  <span className="font-bold text-slate-800">{selectedFeedback.date_str} {selectedFeedback.time_str}</span>
                </div>
                <div>
                  <span className="text-slate-400 block">Department</span>
                  <span className="font-bold text-sky-800">{selectedFeedback.department}</span>
                </div>
                <div>
                  <span className="text-slate-400 block">Fixed HOD</span>
                  <span className="font-bold text-teal-800">{selectedFeedback.hod_name}</span>
                </div>
                <div>
                  <span className="text-slate-400 block">Staff User</span>
                  <span className="font-bold text-slate-800">{selectedFeedback.staff_name}</span>
                </div>
              </div>

              {/* TEMPORARY VOICE RECORDING / GROUND TRUTH REVIEW */}
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Volume2 className="w-4 h-4 text-sky-600" />
                    <span className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                      Temporary Voice Recording (Ground Truth)
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-md">
                    <Clock className="w-3 h-3 text-amber-600" />
                    <span className="text-[10px] font-bold text-amber-800">
                      12-Hour Governance Rule
                    </span>
                  </div>
                </div>

                <div className="text-[11px] text-slate-600 bg-sky-50/70 p-3 rounded-xl border border-sky-100 flex items-start gap-2">
                  <Shield className="w-4 h-4 text-sky-600 mt-0.5 flex-shrink-0" />
                  <span>
                    The original voice recording is temporarily preserved on private server storage for 12 hours from submission as ground truth to verify disputed transcription, speech quality, or English translation. It is never exposed publicly and is permanently purged thereafter.
                  </span>
                </div>

                {/* Status & Expiry Bar */}
                <div className="flex items-center justify-between bg-white p-3 rounded-xl border border-slate-200 text-xs">
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase block">Audio Retention Expiry</span>
                    <span className="font-semibold text-slate-800">
                      {selectedFeedback.retention_expiry_str || selectedFeedback.audio_expiry_str || "12 hours post-submission"}
                    </span>
                  </div>
                  <div>
                    {selectedFeedback.is_audio_expired ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-red-100 text-red-700 font-bold rounded-lg text-xs">
                        <VolumeX className="w-3.5 h-3.5" /> Expired & Purged
                      </span>
                    ) : selectedFeedback.has_audio ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-emerald-100 text-emerald-800 font-bold rounded-lg text-xs">
                        <Volume2 className="w-3.5 h-3.5" /> Recording Available
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 bg-slate-100 text-slate-600 font-medium rounded-lg text-xs">
                        No Voice Audio / Direct Text
                      </span>
                    )}
                  </div>
                </div>

                {/* Player or Action */}
                {selectedFeedback.has_audio && !selectedFeedback.is_audio_expired && (
                  <div className="pt-1">
                    {audioUrl ? (
                      <div className="space-y-2 bg-white p-3 rounded-xl border border-sky-200">
                        <div className="flex items-center justify-between text-[11px] text-sky-900 font-bold">
                          <span>Secure Stream: {selectedFeedback.feedback_id} ({selectedFeedback.duration_seconds || 0}s)</span>
                          <button
                            onClick={() => {
                              if (audioUrl) URL.revokeObjectURL(audioUrl);
                              setAudioUrl(null);
                            }}
                            className="text-slate-400 hover:text-slate-600 underline font-medium text-[10px]"
                          >
                            Close Player
                          </button>
                        </div>
                        <audio controls autoPlay className="w-full h-9 rounded-lg" src={audioUrl}>
                          Your browser does not support audio playback.
                        </audio>
                      </div>
                    ) : (
                      <div className="flex items-center gap-3">
                        <button
                          onClick={async () => {
                            setAudioLoading(true);
                            setAudioError(null);
                            try {
                              const blob = await fetchAudioBlob(selectedFeedback.feedback_id);
                              const url = URL.createObjectURL(blob);
                              setAudioUrl(url);
                            } catch (err: any) {
                              setAudioError(err?.message || "Failed to load audio recording.");
                            } finally {
                              setAudioLoading(false);
                            }
                          }}
                          disabled={audioLoading}
                          className="flex items-center gap-2 py-2 px-4 bg-sky-700 hover:bg-sky-800 disabled:bg-slate-300 text-white font-bold rounded-xl text-xs transition shadow-xs"
                        >
                          <Play className="w-3.5 h-3.5" />
                          {audioLoading ? "Loading Secure Stream..." : "Listen to Ground Truth Audio"}
                        </button>
                        {audioError && (
                          <span className="text-xs text-red-600 font-medium flex items-center gap-1">
                            <AlertTriangle className="w-3.5 h-3.5" />
                            {audioError}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {selectedFeedback.is_audio_expired && (
                  <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs font-medium flex items-center gap-2">
                    <VolumeX className="w-4 h-4 flex-shrink-0" />
                    <span>Audio recording expired (&gt;12 hours) and has been permanently deleted from storage per hospital data retention policy.</span>
                  </div>
                )}
              </div>

              {/* Transcripts */}
              <div className="space-y-3">
                <div className="bg-slate-50 p-4 rounded-2xl border border-slate-200">
                  <span className="text-xs font-bold text-slate-700 uppercase tracking-wider block mb-1">
                    Original Conversation Transcript ({selectedFeedback.original_language})
                  </span>
                  <p className="text-xs text-slate-800 leading-relaxed font-sans whitespace-pre-line">
                    {selectedFeedback.original_transcript || "No transcript recorded"}
                  </p>
                </div>

                <div className="bg-sky-50 p-4 rounded-2xl border border-sky-100">
                  <span className="text-xs font-bold text-sky-900 uppercase tracking-wider block mb-1">
                    English Translation (Clinical Meaning Preserved)
                  </span>
                  <p className="text-xs text-sky-950 leading-relaxed font-medium">
                    {selectedFeedback.english_translation || "No translation"}
                  </p>
                </div>
              </div>

              {/* Controlled Correction Section (Section 36) */}
              <div className="border border-slate-200 rounded-2xl p-4 bg-slate-50 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                    Controlled Correction System
                  </h4>
                  {!isEditing ? (
                    <button
                      onClick={() => setIsEditing(true)}
                      className="py-1 px-3 bg-white border border-slate-300 rounded-lg text-xs font-bold text-sky-700 hover:bg-slate-100"
                    >
                      Edit / Correct Fields
                    </button>
                  ) : (
                    <div className="flex gap-2">
                      <button
                        onClick={handleSaveCorrection}
                        className="py-1 px-3 bg-teal-600 text-white rounded-lg text-xs font-bold hover:bg-teal-700"
                      >
                        Save Correction
                      </button>
                      <button
                        onClick={() => setIsEditing(false)}
                        className="py-1 px-3 bg-slate-200 text-slate-700 rounded-lg text-xs font-bold"
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                </div>

                {isEditing ? (
                  <div className="space-y-3 pt-2">
                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <label className="block text-[11px] font-bold text-slate-600">
                          Department(s) — Max 4 (Re-maps HOD deterministically!)
                        </label>
                        <span className="text-[10px] text-slate-500 font-bold">
                          {editForm.department ? editForm.department.split(",").map((s) => s.trim()).filter(Boolean).length : 0}/4 selected
                        </span>
                      </div>
                      {editForm.department && (
                        <div className="flex flex-wrap gap-1 mb-1.5 p-1.5 bg-slate-50 rounded-lg border border-slate-200">
                          {editForm.department.split(",").map((s) => s.trim()).filter(Boolean).map((d) => (
                            <span key={d} className="inline-flex items-center gap-1 bg-sky-600 text-white text-[10px] font-bold px-2 py-0.5 rounded-md">
                              {d}
                              <button
                                type="button"
                                onClick={() => {
                                  const current = editForm.department.split(",").map((s) => s.trim()).filter(Boolean);
                                  setEditForm({ ...editForm, department: current.filter((x) => x !== d).join(", ") });
                                }}
                                className="hover:bg-sky-700 rounded-full px-0.5"
                              >
                                ✕
                              </button>
                            </span>
                          ))}
                        </div>
                      )}
                      <select
                        value=""
                        onChange={(e) => {
                          if (e.target.value) {
                            const current = editForm.department ? editForm.department.split(",").map((s) => s.trim()).filter(Boolean) : [];
                            if (!current.includes(e.target.value)) {
                              if (current.length >= 4) {
                                alert("Maximum 4 departments can be selected.");
                                return;
                              }
                              setEditForm({ ...editForm, department: [...current, e.target.value].join(", ") });
                            }
                          }
                        }}
                        className="w-full p-2 bg-white border border-slate-300 rounded-xl text-xs font-semibold"
                      >
                        <option value="">+ Add Department (Max 4)...</option>
                        {masterData?.departments
                          .filter((d) => !(editForm.department || "").split(",").map((s) => s.trim()).includes(d.name))
                          .map((d) => (
                            <option key={d.id} value={d.name}>{d.name}</option>
                          ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-[11px] font-bold text-slate-600 mb-1">
                        Corrected Complaint Summary
                      </label>
                      <textarea
                        rows={2}
                        value={editForm.complaint_summary}
                        onChange={(e) => setEditForm({ ...editForm, complaint_summary: e.target.value })}
                        className="w-full p-2 bg-white border border-slate-300 rounded-xl text-xs"
                      />
                    </div>
                  </div>
                ) : (
                  <div className="text-xs text-slate-600">
                    <p>Complaint Summary: <strong>{selectedFeedback.complaint_summary}</strong></p>
                  </div>
                )}

                {/* History of corrections */}
                {selectedFeedback.corrections && selectedFeedback.corrections.length > 0 && (
                  <div className="pt-2 border-t border-slate-200">
                    <span className="text-[11px] font-bold text-slate-500 uppercase block mb-1">
                      Correction History Log
                    </span>
                    <div className="space-y-1">
                      {selectedFeedback.corrections.map((c) => (
                        <div key={c.id} className="text-[11px] bg-white p-2 rounded-lg border border-slate-200 text-slate-600">
                          Field: <strong>{c.field_name}</strong> | Original: <del>{c.original_value}</del> → Corrected: <ins>{c.corrected_value}</ins> by {c.corrected_by_name} ({new Date(c.created_at).toLocaleTimeString()})
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Actions Footer */}
              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={() => handleDeleteFeedback(selectedFeedback.feedback_id)}
                  className="py-2 px-3 text-red-600 hover:bg-red-50 font-bold text-xs rounded-xl transition flex items-center gap-1.5"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete Complaint Permanently
                </button>
                <button
                  onClick={handleCloseDetail}
                  className="py-2.5 px-5 bg-slate-100 hover:bg-slate-200 font-bold text-xs text-slate-700 rounded-xl transition"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* PERMANENT RETENTION / DELETE CONFIRMATION MODAL */}
      {/* ==================================================================== */}
      {deleteModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white w-full max-w-md rounded-3xl shadow-2xl border border-red-200 overflow-hidden p-6 space-y-4">
            <div className="flex items-center gap-3 text-red-600">
              <div className="w-10 h-10 rounded-2xl bg-red-100 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-6 h-6 text-red-600" />
              </div>
              <div>
                <h3 className="text-base font-extrabold text-slate-900">
                  {deleteModal.isBulk ? `Delete ${deleteModal.count} Complaints Permanently` : "Delete Complaint Permanently"}
                </h3>
                <span className="text-[11px] font-semibold text-red-600 uppercase tracking-wider">
                  Irreversible Action
                </span>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed font-medium bg-slate-50 p-3.5 rounded-2xl border border-slate-200">
              {deleteModal.isBulk
                ? `Are you sure you want to delete these ${deleteModal.count} complaints? This action will permanently remove the feedback data, transcript and associated audio.`
                : "Are you sure you want to delete this complaint? This action will permanently remove the feedback data, transcript and associated audio."}
            </p>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => setDeleteModal({ isOpen: false, isBulk: false, count: 0 })}
                disabled={isDeleting}
                className="py-2.5 px-4 bg-slate-100 hover:bg-slate-200 font-bold text-xs text-slate-700 rounded-xl transition disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleExecuteDelete}
                disabled={isDeleting}
                className="py-2.5 px-5 bg-red-600 hover:bg-red-700 active:scale-[0.99] font-extrabold text-xs text-white rounded-xl shadow-md shadow-red-600/30 transition flex items-center gap-1.5 disabled:opacity-50"
              >
                <Trash2 className="w-4 h-4" />
                {isDeleting ? "Deleting..." : "Delete Permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
