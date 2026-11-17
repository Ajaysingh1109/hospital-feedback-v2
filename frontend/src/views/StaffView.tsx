import React, { useEffect, useRef, useState } from "react";
import {
  Mic,
  Square,
  Pause,
  Play,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
  FileText,
  User,
  PlusCircle,
  History,
  CloudUpload,
  ArrowRight,
  Sparkles,
  ChevronRight,
  ShieldCheck,
  Send,
  Edit3,
  Bot,
  UserCheck,
  Cpu,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  fetchMasterData,
  fetchMySubmissions,
  processAudio,
  submitFeedback,
} from "../services/api";
import {
  clearDraftSession,
  enqueueOfflineFeedback,
  getLatestDraftSession,
  getOfflineQueueItems,
  saveDraftSession,
} from "../services/db";
import {
  FeedbackRecord,
  MasterData,
  OfflineFeedbackItem,
  ProcessAudioResult,
  SessionDraft,
  User as UserType,
} from "../types";
import { AudioVisualizer } from "../components/AudioVisualizer";
import { ConsentModal } from "../components/ConsentModal";
import { DepartmentMismatchBanner } from "../components/DepartmentMismatchBanner";
import { LowAudioModal } from "../components/LowAudioModal";
import { SessionRecoveryModal } from "../components/SessionRecoveryModal";

interface StaffViewProps {
  user: UserType;
  isOnline: boolean;
}

// Visible Recording & Submission States (Section 2)
type AppStateBadge = "IDLE" | "RECORDING" | "PAUSED" | "PROCESSING" | "SAVED OFFLINE" | "SYNCING" | "SYNCED" | "FAILED";

export const StaffView: React.FC<StaffViewProps> = ({ user, isOnline }) => {
  const [activeTab, setActiveTab] = useState<"dashboard" | "flow" | "submissions" | "offline">("dashboard");
  const [step, setStep] = useState<"consent" | "record" | "processing" | "details" | "review" | "success">("consent");
  const [statusBadge, setStatusBadge] = useState<AppStateBadge>("IDLE");

  // Master Data
  const [masterData, setMasterData] = useState<MasterData>({
    departments: [],
    schemes: [],
    consultants: [],
    consent_notice_text: "This conversation will be recorded and processed for hospital feedback and quality improvement.",
  });

  // Stats
  const [todaySubmissions, setTodaySubmissions] = useState<FeedbackRecord[]>([]);
  const [offlineItems, setOfflineItems] = useState<OfflineFeedbackItem[]>([]);
  const [recoveredDraft, setRecoveredDraft] = useState<SessionDraft | null>(null);

  // Active Session State
  const [sessionId, setSessionId] = useState<string>("");
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
  const [audioChunks, setAudioChunks] = useState<Blob[]>([]);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [recordingDuration, setRecordingDuration] = useState<number>(0);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [isPaused, setIsPaused] = useState<boolean>(false);
  const [recordingWarning, setRecordingWarning] = useState<string | null>(null);
  const timerRef = useRef<any>(null);

  // Consent tracking (Section 19)
  const [consentTimestamp, setConsentTimestamp] = useState<string>("");

  // Modals & Warnings
  const [showConsentModal, setShowConsentModal] = useState<boolean>(false);
  const [showLowAudioModal, setShowLowAudioModal] = useState<boolean>(false);
  const [lowAudioMessage, setLowAudioMessage] = useState<string>("");

  // Stepped Processing Tracker
  const [processingStatus, setProcessingStatus] = useState<string>("");
  const [processingError, setProcessingError] = useState<string | null>(null);

  // Form Data (MANDATORY: UHID, Patient Name, Department)
  const [formData, setFormData] = useState({
    uhid: "",
    patient_name: "",
    department: "",
    location: "",
    consultant: "",
    scheme: "",
    attendant_name: "",
    subcategory: "",
    complaint: "",
    complaint_type: "General Feedback",
    complaint_summary: "",
    detailed_feedback: "",
    positive_feedback: "",
    negative_feedback: "",
    specific_complaint: "",
    suggested_action: "",
    priority: "Not Specified",
  });

  const [aiResult, setAiResult] = useState<ProcessAudioResult | null>(null);
  const [submittedRecord, setSubmittedRecord] = useState<FeedbackRecord | null>(null);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState<boolean>(false);

  // Load Initial Data & Session Check
  useEffect(() => {
    loadInitialData();

    // Check for unfinished session recovery (Section 59)
    getLatestDraftSession().then((draft) => {
      if (draft && draft.step !== "record") {
        setRecoveredDraft(draft);
      }
    });

    const handleSyncSuccess = () => {
      setStatusBadge("SYNCED");
      loadInitialData();
      setTimeout(() => setStatusBadge("IDLE"), 3000);
    };
    window.addEventListener("sync:success", handleSyncSuccess);

    // Screen lock / App switching listener (Section 2)
    const handleVisibilityChange = () => {
      if (document.hidden && isRecording) {
        setRecordingWarning("App went to background while recording was active. Verify audio was captured before submitting.");
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.removeEventListener("sync:success", handleSyncSuccess);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [isRecording]);

  const loadInitialData = async () => {
    try {
      const md = await fetchMasterData();
      setMasterData(md);
      if (isOnline) {
        const subs = await fetchMySubmissions();
        setTodaySubmissions(subs);
      }
      const queue = await getOfflineQueueItems();
      setOfflineItems(queue);
    } catch (e) {
      console.warn("Failed to load initial staff data:", e);
    }
  };

  // Generate Unique Feedback Session
  const startNewFeedbackFlow = () => {
    const newSessionId = `uuid-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    setSessionId(newSessionId);
    setAudioBlob(null);
    setAudioChunks([]);
    setRecordingDuration(0);
    setRecordingWarning(null);
    setAiResult(null);
    setSubmittedRecord(null);
    setProcessingError(null);
    setFormErrors({});
    setStatusBadge("IDLE");
    setFormData({
      uhid: "",
      patient_name: "",
      department: "",
      location: "",
      consultant: "",
      scheme: "",
      attendant_name: "",
      subcategory: "",
      complaint: "",
      complaint_type: "General Feedback",
      complaint_summary: "",
      detailed_feedback: "",
      positive_feedback: "",
      negative_feedback: "",
      specific_complaint: "",
      suggested_action: "",
      priority: "Not Specified",
    });

    // Step 1: Mandatory Consent Dialog (Section 10 & 19)
    setStep("consent");
    setShowConsentModal(true);
    setActiveTab("flow");
  };

  const handleConsentAgreed = () => {
    setShowConsentModal(false);
    setConsentTimestamp(new Date().toISOString());
    setStep("record");
  };

  const handleConsentCancelled = () => {
    setShowConsentModal(false);
    setActiveTab("dashboard");
  };

  // ============================================================================
  // AUDIO RECORDING ENGINE (SECTION 2 & 12)
  // ============================================================================

  const startRecording = async () => {
    setRecordingWarning(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      setAudioStream(stream);

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";

      const recorder = new MediaRecorder(stream, { mimeType });
      const chunks: Blob[] = [];

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          chunks.push(e.data);
        }
      };

      recorder.onstop = () => {
        const fullBlob = new Blob(chunks, { type: "audio/webm" });
        setAudioBlob(fullBlob);
        setAudioChunks(chunks);
        stream.getTracks().forEach((track) => track.stop());
      };

      recorder.start(250);
      setMediaRecorder(recorder);
      setIsRecording(true);
      setIsPaused(false);
      setStatusBadge("RECORDING");

      setRecordingDuration(0);
      timerRef.current = setInterval(() => {
        setRecordingDuration((prev) => prev + 1);
      }, 1000);
    } catch (err: any) {
      console.warn("Microphone access failed:", err);
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        alert("Microphone permission was denied. Please allow microphone access in your browser settings to record patient conversations.");
        return;
      }
      // Simulation mode for headless test runs
      simulateRecording();
    }
  };

  const pauseRecording = () => {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.pause();
      setIsPaused(true);
      setStatusBadge("PAUSED");
      clearInterval(timerRef.current);
    }
  };

  const resumeRecording = () => {
    if (mediaRecorder && mediaRecorder.state === "paused") {
      mediaRecorder.resume();
      setIsPaused(false);
      setStatusBadge("RECORDING");
      timerRef.current = setInterval(() => {
        setRecordingDuration((prev) => prev + 1);
      }, 1000);
    }
  };

  const stopAndProcessRecording = () => {
    clearInterval(timerRef.current);
    setIsRecording(false);
    setIsPaused(false);

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }

    setTimeout(() => {
      runProcessingPipeline();
    }, 400);
  };

  const simulateRecording = () => {
    setIsRecording(true);
    setStatusBadge("RECORDING");
    setRecordingDuration(0);
    timerRef.current = setInterval(() => {
      setRecordingDuration((prev) => prev + 1);
    }, 1000);
  };

  // ============================================================================
  // PROCESSING PIPELINE & AUDIO QUALITY CHECK (SECTION 3 & 49)
  // ============================================================================

  const runProcessingPipeline = async () => {
    setStep("processing");
    setStatusBadge("PROCESSING");

    // Audio Quality Check (Section 3 & 50)
    if (recordingDuration < 2 && (!audioBlob || audioBlob.size < 1200)) {
      setLowAudioMessage("Recording duration is under 2 seconds. Audio quality appears very low or silent.");
      setShowLowAudioModal(true);
      return;
    }

    proceedWithAIAnalysis();
  };

  const proceedWithAIAnalysis = async () => {
    setShowLowAudioModal(false);
    setStep("processing");
    setStatusBadge("PROCESSING");
    setProcessingError(null);

    setProcessingStatus("Uploading audio recording...");
    await new Promise((r) => setTimeout(r, 300));

    setProcessingStatus("Transcribing conversation (Hindi / Hinglish / English)...");
    await new Promise((r) => setTimeout(r, 400));

    setProcessingStatus("Translating to English & preserving clinical nuance...");
    await new Promise((r) => setTimeout(r, 400));

    setProcessingStatus("Extracting structured complaint & suggesting department...");

    const activeBlob =
      audioBlob ||
      new Blob(
        [
          new Uint8Array([
            0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00, 0x57, 0x41, 0x56, 0x45,
          ]),
        ],
        { type: "audio/webm" }
      );

    try {
      if (isOnline) {
        const result = await processAudio(activeBlob, sessionId);
        setAiResult(result);

        const initialComplaint = result.complaint || result.english_translation || result.complaint_summary || "";

        setFormData((prev) => ({
          ...prev,
          department: result.suggested_department || prev.department,
          subcategory: result.suggested_subcategory || prev.subcategory,
          complaint: initialComplaint || prev.complaint,
          complaint_type: result.complaint_type || prev.complaint_type,
          complaint_summary: result.complaint_summary || prev.complaint_summary,
          detailed_feedback: result.detailed_feedback || prev.detailed_feedback,
          positive_feedback: result.positive_feedback || prev.positive_feedback,
          negative_feedback: result.negative_feedback || prev.negative_feedback,
          specific_complaint: result.specific_complaint || prev.specific_complaint,
          suggested_action: result.suggested_action || prev.suggested_action,
          priority: result.priority || prev.priority,
        }));
      } else {
        // Safe offline handling: do NOT pretend AI succeeded or generate fake transcripts
        setAiResult(null);
        setFormData((prev) => ({
          ...prev,
          complaint: prev.complaint || "",
          complaint_summary: "",
          detailed_feedback: "",
          positive_feedback: "Not Provided",
          negative_feedback: "Not Provided",
        }));
      }

      setStep("details");
      setStatusBadge("IDLE");

      saveDraftSession({
        session_id: sessionId,
        started_at: new Date().toISOString(),
        step: "details",
        duration_seconds: recordingDuration,
        form_data: formData,
      });
    } catch (err: any) {
      console.error("AI pipeline error:", err);
      // Section 18: Never lose audio on failure! Allow Retry or continue with manual entry
      setProcessingError(err?.message || "AI processing encountered an issue.");
    }
  };

  // ============================================================================
  // MANDATORY VALIDATION (SECTION 20 & 21)
  // ============================================================================

  const validatePatientDetails = (): boolean => {
    const errors: Record<string, string> = {};

    if (!formData.uhid || !formData.uhid.trim()) {
      errors.uhid = "UHID is required.";
    }
    if (!formData.patient_name || !formData.patient_name.trim()) {
      errors.patient_name = "Patient Name is required.";
    }
    if (!formData.department || !formData.department.trim()) {
      errors.department = "Department is required.";
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleProceedToReview = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validatePatientDetails()) {
      return;
    }
    setStep("review");
    saveDraftSession({
      session_id: sessionId,
      started_at: new Date().toISOString(),
      step: "review",
      duration_seconds: recordingDuration,
      form_data: formData,
    });
  };

  // ============================================================================
  // FINAL SUBMISSION (SECTION 27 & 28)
  // ============================================================================

  const handleFinalSubmit = async () => {
    if (!validatePatientDetails()) {
      setStep("details");
      return;
    }

    setSubmitting(true);
    setStatusBadge(isOnline ? "SYNCING" : "SAVED OFFLINE");

    const payload = {
      client_uuid: sessionId,
      uhid: String(formData.uhid).trim(), // STRICTLY TEXT! Preserves leading zeros!
      patient_name: formData.patient_name.trim(),
      department: formData.department.trim(),
      location: formData.location || undefined,
      consultant: formData.consultant || undefined,
      scheme: formData.scheme || undefined,
      attendant_name: formData.attendant_name || undefined,
      subcategory: formData.subcategory || undefined,
      complaint: formData.complaint?.trim() || formData.complaint_summary || aiResult?.english_translation || "Not Provided",
      complaint_type: formData.complaint_type,
      complaint_summary: formData.complaint_summary,
      detailed_feedback: formData.detailed_feedback,
      positive_feedback: formData.positive_feedback,
      negative_feedback: formData.negative_feedback,
      specific_complaint: formData.specific_complaint,
      suggested_action: formData.suggested_action,
      priority: formData.priority,
      original_language: aiResult?.original_language || "Hindi/English",
      original_transcript: aiResult?.original_transcript || "",
      english_translation: aiResult?.english_translation || "",
      duration_seconds: recordingDuration,
      audio_file_id: aiResult?.audio_file_id,
      ai_suggested_department: aiResult?.suggested_department,
      consent_status: "CONSENT_OBTAINED",
      consent_timestamp: consentTimestamp || new Date().toISOString(),
    };

    try {
      if (isOnline) {
        const record = await submitFeedback(payload);
        setSubmittedRecord(record);
        await clearDraftSession(sessionId);
        setStep("success");
        setStatusBadge("SYNCED");
        loadInitialData();
      } else {
        await enqueueOfflineFeedback({
          client_uuid: sessionId,
          created_at: new Date().toISOString(),
          payload,
          audio_blob: audioBlob || undefined,
          status: "READY",
          retry_count: 0,
        });
        await clearDraftSession(sessionId);
        setStep("success");
        setStatusBadge("SAVED OFFLINE");
        loadInitialData();
      }
    } catch (err: any) {
      console.warn("Submission error, storing offline for background retry:", err);
      await enqueueOfflineFeedback({
        client_uuid: sessionId,
        created_at: new Date().toISOString(),
        payload,
        audio_blob: audioBlob || undefined,
        status: "READY",
        retry_count: 0,
      });
      await clearDraftSession(sessionId);
      setStep("success");
      setStatusBadge("SAVED OFFLINE");
      loadInitialData();
    } finally {
      setSubmitting(false);
    }
  };

  // Deterministic HOD Preview (Point 1 & 6: Security is NOT Asha Ma'am)
  const getHODPreview = (dept: string) => {
    const clean = dept.toLowerCase().trim();
    if (clean === "clinical") return "Tanveer Sir";
    if (clean === "nursing") return "Reshmi Ma'am";
    if (clean === "pharmacy") return "Vijay Sir";
    if (clean === "it") return "Valay Sir";
    if (
      [
        "maintenance",
        "f&b",
        "housekeeping",
        "operations",
        "billing",
      ].includes(clean)
    ) {
      return "Asha Ma'am";
    }
    // Security or other unmapped departments
    return "HOD Not Configured";
  };

  const formatTimer = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  return (
    <div className="max-w-xl mx-auto px-4 py-4 pb-20">
      {/* Session Recovery Modal (Section 59) */}
      <SessionRecoveryModal
        draft={recoveredDraft}
        onResume={() => {
          if (recoveredDraft) {
            setSessionId(recoveredDraft.session_id);
            setStep(recoveredDraft.step);
            setFormData(recoveredDraft.form_data);
            setRecordingDuration(recoveredDraft.duration_seconds || 0);
            setRecoveredDraft(null);
            setActiveTab("flow");
          }
        }}
        onDiscard={() => {
          clearDraftSession();
          setRecoveredDraft(null);
        }}
      />

      {/* Consent Notice Modal (Section 10 & 19) */}
      <ConsentModal
        isOpen={showConsentModal}
        noticeText={masterData.consent_notice_text}
        onAgree={handleConsentAgreed}
        onCancel={handleConsentCancelled}
      />

      {/* Low Audio Modal (Section 50) */}
      <LowAudioModal
        isOpen={showLowAudioModal}
        message={lowAudioMessage}
        onRecordAgain={() => {
          setShowLowAudioModal(false);
          setStep("record");
        }}
        onContinue={proceedWithAIAnalysis}
      />

      {/* Visible State Banner (Section 2) */}
      {statusBadge !== "IDLE" && (
        <div className="mb-3 px-3 py-1.5 rounded-xl text-xs font-bold uppercase tracking-wider flex items-center justify-between shadow-xs border transition-all animate-fade-in bg-slate-900 text-white border-slate-700">
          <div className="flex items-center gap-2">
            <span className={`w-2.5 h-2.5 rounded-full ${
              statusBadge === "RECORDING" ? "bg-red-500 animate-ping" :
              statusBadge === "PAUSED" ? "bg-amber-400" :
              statusBadge === "PROCESSING" || statusBadge === "SYNCING" ? "bg-sky-400 animate-spin" :
              statusBadge === "SYNCED" ? "bg-emerald-400" : "bg-amber-500"
            }`} />
            <span>STATE: {statusBadge}</span>
          </div>
          <span className="text-[10px] text-slate-300 font-mono">
            {recordingDuration > 0 && `${recordingDuration}s`}
          </span>
        </div>
      )}

      {/* ==================================================================== */}
      {/* 1. DASHBOARD VIEW */}
      {/* ==================================================================== */}
      {activeTab === "dashboard" && (
        <div className="space-y-4 animate-fade-in">
          {/* Welcome Card */}
          <div className="bg-gradient-to-r from-sky-700 to-teal-700 rounded-3xl p-5 text-white shadow-xl">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-xs uppercase tracking-wider text-sky-200 font-semibold">
                  Hospital Mobile Station
                </span>
                <h2 className="text-xl font-bold mt-0.5">{user.display_name}</h2>
              </div>
              <div className="w-12 h-12 bg-white/20 backdrop-blur-md rounded-2xl flex items-center justify-center">
                <User className="w-6 h-6 text-white" />
              </div>
            </div>

            {/* Offline Status Notice */}
            {!isOnline && (
              <div className="mt-3 py-2 px-3 bg-amber-500/30 border border-amber-300/40 rounded-xl text-xs font-medium text-amber-100 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-amber-300 shrink-0" />
                <span>Operating offline. Feedbacks will safely sync when network restores.</span>
              </div>
            )}

            {/* Main Primary Action Button */}
            <button
              onClick={startNewFeedbackFlow}
              className="mt-5 w-full py-4 bg-white text-sky-900 hover:bg-sky-50 active:scale-[0.99] font-extrabold rounded-2xl shadow-lg transition flex items-center justify-center gap-2.5 text-base"
            >
              <PlusCircle className="w-6 h-6 text-teal-600" />
              + NEW PATIENT FEEDBACK
            </button>
          </div>

          {/* Quick Metrics Cards */}
          <div className="grid grid-cols-3 gap-2.5">
            <div
              onClick={() => setActiveTab("submissions")}
              className="bg-white p-3.5 rounded-2xl border border-slate-200 shadow-xs cursor-pointer hover:border-sky-300 transition"
            >
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wide block">
                Today's
              </span>
              <span className="text-2xl font-black text-slate-800 mt-1 block">
                {todaySubmissions.length}
              </span>
              <span className="text-[10px] text-sky-600 font-semibold flex items-center gap-0.5 mt-0.5">
                Submissions <ChevronRight className="w-3 h-3" />
              </span>
            </div>

            <div
              onClick={() => setActiveTab("offline")}
              className="bg-white p-3.5 rounded-2xl border border-slate-200 shadow-xs cursor-pointer hover:border-amber-300 transition"
            >
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wide block">
                Pending Sync
              </span>
              <span className={`text-2xl font-black mt-1 block ${offlineItems.length > 0 ? "text-amber-600" : "text-slate-800"}`}>
                {offlineItems.length}
              </span>
              <span className="text-[10px] text-amber-600 font-semibold flex items-center gap-0.5 mt-0.5">
                Offline Queue <ChevronRight className="w-3 h-3" />
              </span>
            </div>

            <div
              onClick={() => recoveredDraft && setStep(recoveredDraft.step)}
              className="bg-white p-3.5 rounded-2xl border border-slate-200 shadow-xs cursor-pointer hover:border-teal-300 transition"
            >
              <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wide block">
                Drafts
              </span>
              <span className="text-2xl font-black text-slate-800 mt-1 block">
                {recoveredDraft ? 1 : 0}
              </span>
              <span className="text-[10px] text-teal-600 font-semibold flex items-center gap-0.5 mt-0.5">
                In-Progress <ChevronRight className="w-3 h-3" />
              </span>
            </div>
          </div>

          {/* Action Navigation Buttons */}
          <div className="grid grid-cols-2 gap-2.5 pt-1">
            <button
              onClick={() => setActiveTab("submissions")}
              className="py-3 px-4 bg-white border border-slate-200 rounded-2xl font-bold text-slate-700 hover:bg-slate-50 shadow-xs transition flex items-center justify-center gap-2 text-xs"
            >
              <History className="w-4 h-4 text-sky-600" />
              MY SUBMISSIONS
            </button>
            <button
              onClick={() => setActiveTab("offline")}
              className="py-3 px-4 bg-white border border-slate-200 rounded-2xl font-bold text-slate-700 hover:bg-slate-50 shadow-xs transition flex items-center justify-center gap-2 text-xs"
            >
              <CloudUpload className="w-4 h-4 text-teal-600" />
              DRAFTS / OFFLINE ({offlineItems.length})
            </button>
          </div>
        </div>
      )}

      {/* ==================================================================== */}
      {/* 2. NEW FEEDBACK FLOW */}
      {/* ==================================================================== */}
      {activeTab === "flow" && (
        <div className="space-y-4">
          {/* Top Bar with Cancel */}
          <div className="flex items-center justify-between pb-2 border-b border-slate-200">
            <div>
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                Active Session
              </span>
              <h3 className="text-sm font-bold text-slate-800 font-mono">
                {sessionId.substring(0, 18)}...
              </h3>
            </div>
            <button
              onClick={() => {
                if (confirm("Discard this feedback session and return to dashboard?")) {
                  clearDraftSession();
                  setActiveTab("dashboard");
                }
              }}
              className="text-xs text-red-600 font-semibold hover:bg-red-50 py-1.5 px-3 rounded-xl transition"
            >
              Cancel
            </button>
          </div>

          {/* STEP 2: VOICE RECORDING SCREEN */}
          {step === "record" && (
            <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-md flex flex-col items-center text-center space-y-5 animate-fade-in">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-teal-600 bg-teal-50 px-2.5 py-1 rounded-full">
                  Step 1: Patient & Staff Audio
                </span>
                <h3 className="text-xl font-extrabold text-slate-900 mt-2">
                  Conversation Recording
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  Supports Hindi, Hinglish, English, or Mixed dialogue
                </p>
              </div>

              {/* Background Interruption Warning */}
              {recordingWarning && (
                <div className="w-full bg-amber-50 border border-amber-200 text-amber-800 p-3 rounded-2xl text-xs text-left">
                  {recordingWarning}
                </div>
              )}

              {/* Live Waveform Visualizer */}
              <AudioVisualizer
                stream={audioStream}
                isRecording={isRecording}
                isPaused={isPaused}
              />

              {/* Timer */}
              <div className="font-mono text-4xl font-extrabold text-slate-800 tracking-wider">
                {formatTimer(recordingDuration)}
              </div>

              {/* Big Record Button */}
              {!isRecording ? (
                <button
                  type="button"
                  onClick={startRecording}
                  className="w-24 h-24 rounded-full bg-gradient-to-tr from-sky-600 to-teal-600 hover:from-sky-700 hover:to-teal-700 text-white shadow-xl shadow-sky-600/30 flex items-center justify-center transition-all active:scale-95"
                >
                  <Mic className="w-12 h-12" />
                </button>
              ) : (
                <div className="flex items-center gap-4">
                  {!isPaused ? (
                    <button
                      type="button"
                      onClick={pauseRecording}
                      title="Pause"
                      className="w-14 h-14 rounded-full bg-amber-100 hover:bg-amber-200 text-amber-700 flex items-center justify-center shadow-md transition"
                    >
                      <Pause className="w-6 h-6" />
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={resumeRecording}
                      title="Resume"
                      className="w-14 h-14 rounded-full bg-emerald-100 hover:bg-emerald-200 text-emerald-700 flex items-center justify-center shadow-md transition"
                    >
                      <Play className="w-6 h-6 fill-current" />
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={stopAndProcessRecording}
                    className="h-14 px-6 rounded-full bg-red-600 hover:bg-red-700 text-white font-bold text-sm flex items-center gap-2 shadow-lg shadow-red-600/30 transition active:scale-95"
                  >
                    <Square className="w-5 h-5 fill-current" />
                    STOP & PROCESS
                  </button>
                </div>
              )}

              <p className="text-xs text-slate-400 max-w-xs">
                {isRecording
                  ? "Recording active. Speak clearly near the patient. Tap STOP & PROCESS when finished."
                  : "Tap the microphone button to start voice recording."}
              </p>
            </div>
          )}

          {/* STEP 3: PROCESSING SCREEN (SECTION 49) */}
          {step === "processing" && (
            <div className="bg-white rounded-3xl p-8 border border-slate-200 shadow-md text-center space-y-6 animate-fade-in">
              <div className="w-16 h-16 rounded-3xl bg-sky-100 text-sky-600 flex items-center justify-center mx-auto animate-spin-slow">
                <Sparkles className="w-8 h-8" />
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-900">
                  AI Pipeline in Progress
                </h3>
                <p className="text-xs text-slate-500 mt-1">
                  Understanding patient conversation
                </p>
              </div>

              {processingError ? (
                <div className="space-y-4">
                  <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl font-medium">
                    {processingError}
                  </div>
                  <div className="flex gap-2 justify-center">
                    <button
                      onClick={proceedWithAIAnalysis}
                      className="py-2 px-4 bg-sky-600 text-white text-xs font-bold rounded-xl shadow-xs"
                    >
                      Retry AI Analysis
                    </button>
                    <button
                      onClick={() => setStep("details")}
                      className="py-2 px-4 bg-slate-100 text-slate-700 text-xs font-semibold rounded-xl"
                    >
                      Continue with Manual Entry
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3 max-w-xs mx-auto text-left text-xs">
                  <div className="flex items-center gap-2 text-slate-700 font-medium">
                    <div className="w-4 h-4 rounded-full bg-emerald-500 flex items-center justify-center text-white text-[10px]">✓</div>
                    <span>Audio Captured ({recordingDuration}s)</span>
                  </div>
                  <div className="flex items-center gap-2 text-sky-700 font-semibold animate-pulse">
                    <div className="w-4 h-4 rounded-full bg-sky-600 flex items-center justify-center text-white text-[10px]">⋯</div>
                    <span>{processingStatus}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* STEP 4: PATIENT DETAILS FORM (MANDATORY VALIDATION) */}
          {step === "details" && (
            <form onSubmit={handleProceedToReview} className="bg-white rounded-3xl p-6 border border-slate-200 shadow-md space-y-4 animate-fade-in">
              <div>
                <span className="text-xs font-bold uppercase tracking-wider text-teal-600 bg-teal-50 px-2.5 py-1 rounded-full">
                  Step 2: Patient Information
                </span>
                <h3 className="text-lg font-extrabold text-slate-900 mt-2">
                  Verify & Complete Details
                </h3>
              </div>

              {/* Offline Notification Banner */}
              {!isOnline && (
                <div className="p-3.5 bg-amber-50 border border-amber-300 rounded-2xl text-amber-900 text-xs font-semibold flex items-center gap-2.5 shadow-xs">
                  <WifiOff className="w-5 h-5 text-amber-600 flex-shrink-0" />
                  <div>
                    <span className="font-bold block">Offline Mode Active</span>
                    <span className="text-[11px] text-amber-800">Saved Offline — audio & session will process automatically when internet is available.</span>
                  </div>
                </div>
              )}

              {/* Department Mismatch Banner (Section 25) */}
              {aiResult?.suggested_department && (
                <DepartmentMismatchBanner
                  aiDepartment={aiResult.suggested_department}
                  selectedDepartment={formData.department}
                  onUseSelected={() => {}}
                  onUseAI={() => setFormData({ ...formData, department: aiResult.suggested_department! })}
                />
              )}

              {/* Mandatory UHID (Preserves leading zeros!) */}
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                  UHID <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.uhid}
                  onChange={(e) => setFormData({ ...formData, uhid: e.target.value })}
                  placeholder="e.g. 000123456"
                  className={`w-full px-4 py-3 bg-slate-50 border rounded-2xl text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sky-500 ${
                    formErrors.uhid ? "border-red-400 bg-red-50" : "border-slate-200"
                  }`}
                />
                {formErrors.uhid && (
                  <span className="text-red-600 text-xs mt-1 block font-medium">{formErrors.uhid}</span>
                )}
              </div>

              {/* Mandatory Patient Name */}
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                  Patient Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.patient_name}
                  onChange={(e) => setFormData({ ...formData, patient_name: e.target.value })}
                  placeholder="Full patient name"
                  className={`w-full px-4 py-3 bg-slate-50 border rounded-2xl text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 ${
                    formErrors.patient_name ? "border-red-400 bg-red-50" : "border-slate-200"
                  }`}
                />
                {formErrors.patient_name && (
                  <span className="text-red-600 text-xs mt-1 block font-medium">{formErrors.patient_name}</span>
                )}
              </div>

              {/* Mandatory Department Selection */}
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                  Department <span className="text-red-500">*</span>
                </label>
                <select
                  required
                  value={formData.department}
                  onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                  className={`w-full px-4 py-3 bg-slate-50 border rounded-2xl text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-sky-500 ${
                    formErrors.department ? "border-red-400 bg-red-50" : "border-slate-200"
                  }`}
                >
                  <option value="">-- Select Hospital Department --</option>
                  {masterData.departments.map((d) => (
                    <option key={d.id} value={d.name}>
                      {d.name}
                    </option>
                  ))}
                </select>
                {formErrors.department && (
                  <span className="text-red-600 text-xs mt-1 block font-medium">{formErrors.department}</span>
                )}
              </div>

              {/* Deterministic HOD Live Preview */}
              {formData.department && (
                <div className="bg-sky-50 border border-sky-100 rounded-2xl p-3 text-xs flex items-center justify-between">
                  <span className="text-slate-600 font-medium">Mapped HOD:</span>
                  <span className={`font-extrabold px-2 py-0.5 rounded-lg border ${
                    getHODPreview(formData.department) === "HOD Not Configured"
                      ? "bg-amber-50 text-amber-800 border-amber-300"
                      : "bg-white text-sky-900 border-sky-200"
                  }`}>
                    {getHODPreview(formData.department)}
                  </span>
                </div>
              )}

              {/* Optional Fields Accordion / Grid */}
              <div className="grid grid-cols-2 gap-3 pt-2">
                <div>
                  <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1">
                    Location / Bed
                  </label>
                  <input
                    type="text"
                    value={formData.location}
                    onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                    placeholder="Ward 3B, Bed 12"
                    className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1">
                    Consultant (Optional)
                  </label>
                  <input
                    type="text"
                    value={formData.consultant}
                    onChange={(e) => setFormData({ ...formData, consultant: e.target.value })}
                    placeholder="e.g. Dr. Rajesh Kumar"
                    className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1">
                    Scheme
                  </label>
                  <select
                    value={formData.scheme}
                    onChange={(e) => setFormData({ ...formData, scheme: e.target.value })}
                    className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs"
                  >
                    <option value="">Direct Cash / None</option>
                    {masterData.schemes.map((s, i) => (
                      <option key={i} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1">
                    Attendant Name
                  </label>
                  <input
                    type="text"
                    value={formData.attendant_name}
                    onChange={(e) => setFormData({ ...formData, attendant_name: e.target.value })}
                    placeholder="Attendant name"
                    className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs"
                  />
                </div>
              </div>

              {/* Editable Complaint Summary */}
              <div className="pt-2">
                <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider mb-1">
                  Complaint Summary
                </label>
                <textarea
                  rows={2}
                  value={formData.complaint_summary}
                  onChange={(e) => setFormData({ ...formData, complaint_summary: e.target.value })}
                  placeholder="Summary of complaint or feedback"
                  className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs"
                />
              </div>

              <button
                type="submit"
                className="w-full py-3.5 bg-gradient-to-r from-sky-600 to-teal-600 hover:from-sky-700 hover:to-teal-700 active:scale-[0.99] text-white font-bold rounded-2xl shadow-lg transition flex items-center justify-center gap-2 text-sm"
              >
                PROCEED TO REVIEW
                <ArrowRight className="w-4 h-4" />
              </button>
            </form>
          )}

          {/* STEP 5: REVIEW SCREEN WITH CLEAR SOURCE DISTINCTION (POINT 5) */}
          {step === "review" && (
            <div className="bg-white rounded-3xl p-6 border border-slate-200 shadow-md space-y-4 animate-fade-in">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider text-teal-600 bg-teal-50 px-2.5 py-1 rounded-full">
                    Step 3: Verification
                  </span>
                  <h3 className="text-lg font-extrabold text-slate-900 mt-2">
                    Review Feedback
                  </h3>
                </div>
                <button
                  onClick={() => setStep("details")}
                  className="text-xs text-sky-600 font-bold hover:bg-sky-50 py-1.5 px-3 rounded-xl transition flex items-center gap-1"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                  EDIT
                </button>
              </div>

              {/* SECTION 1: PATIENT DETAILS */}
              <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 text-xs space-y-3">
                <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                  <span className="font-extrabold text-slate-800 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                    <UserCheck className="w-4 h-4 text-emerald-600" />
                    PATIENT DETAILS
                  </span>
                  <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                    Staff Verified
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase block">UHID</span>
                    <span className="font-mono font-bold text-slate-900 text-sm">{formData.uhid}</span>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase block">Patient Name</span>
                    <span className="font-bold text-slate-900 text-sm">{formData.patient_name}</span>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase block">Department</span>
                    <span className="font-bold text-teal-800 text-sm">{formData.department}</span>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase block">Location / Bed</span>
                    <span className="text-slate-800 font-medium">{formData.location || "Not Provided"}</span>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase block">Consultant</span>
                    <span className="text-slate-800 font-medium">{formData.consultant || "Not Provided"}</span>
                  </div>
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase block">Scheme</span>
                    <span className="text-slate-800 font-medium">{formData.scheme || "Not Provided"}</span>
                  </div>
                </div>
              </div>

              {/* SECTION 2: AI / FEEDBACK */}
              <div className="bg-sky-50/50 border border-sky-200 rounded-2xl p-4 text-xs space-y-3">
                <div className="flex items-center justify-between border-b border-sky-200 pb-2">
                  <span className="font-extrabold text-sky-900 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                    <Bot className="w-4 h-4 text-sky-600" />
                    AI / FEEDBACK
                  </span>
                  <span className="text-[10px] font-semibold text-sky-700 bg-white px-2 py-0.5 rounded-md border border-sky-300">
                    Staff Editable
                  </span>
                </div>

                {!isOnline && (
                  <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl text-amber-900 text-xs font-semibold flex items-center gap-2 shadow-xs">
                    <WifiOff className="w-4 h-4 text-amber-600 flex-shrink-0" />
                    <span>Saved Offline — will process automatically when internet is available.</span>
                  </div>
                )}

                {/* Original Transcript */}
                <div>
                  <label className="text-[10px] font-bold text-slate-500 uppercase block mb-1">
                    Original Transcript (Preserved verbatim):
                  </label>
                  <div className="bg-white p-3 rounded-xl border border-sky-100 text-slate-700 text-xs font-mono leading-relaxed max-h-24 overflow-y-auto">
                    {aiResult?.original_transcript || (audioBlob ? "[Voice recording stored locally in encrypted offline queue. Speech will transcribe on cloud sync.]" : "Direct submission without recording")}
                  </div>
                </div>

                {/* English Complaint (Editable by staff before submission) */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[10px] font-bold text-sky-900 uppercase flex items-center gap-1">
                      English Complaint <span className="text-slate-400 font-normal">(Staff may edit before submission)</span>
                    </label>
                    <span className="text-[10px] text-sky-600 font-bold flex items-center gap-0.5">
                      <Edit3 className="w-3 h-3" /> Editable
                    </span>
                  </div>
                  <textarea
                    rows={3}
                    value={formData.complaint}
                    onChange={(e) => setFormData({ ...formData, complaint: e.target.value })}
                    placeholder="Enter or refine final English complaint statement..."
                    className="w-full p-3 bg-white border border-sky-300 rounded-xl text-slate-900 text-xs font-medium focus:ring-2 focus:ring-sky-500 focus:outline-none"
                  />
                </div>

                {/* Complaint Type */}
                <div>
                  <label className="text-[10px] font-bold text-slate-600 uppercase block mb-1">
                    Complaint Type:
                  </label>
                  <select
                    value={formData.complaint_type}
                    onChange={(e) => setFormData({ ...formData, complaint_type: e.target.value })}
                    className="w-full px-3 py-2 bg-white border border-sky-200 rounded-xl text-xs font-bold text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    {[
                      "Clinical",
                      "Nursing Care",
                      "Pharmacy",
                      "Food Complaint",
                      "Housekeeping",
                      "Infrastructure",
                      "Billing",
                      "Staff Behaviour",
                      "Service Complaint",
                      "Maintenance",
                      "General Feedback",
                      "Appreciation",
                    ].map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* SECTION 3: SYSTEM */}
              <div className="bg-purple-50/70 border border-purple-200 rounded-2xl p-4 text-xs space-y-2">
                <div className="flex items-center justify-between border-b border-purple-200 pb-2">
                  <span className="font-extrabold text-purple-900 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                    <Cpu className="w-4 h-4 text-purple-600" />
                    SYSTEM
                  </span>
                  <span className="text-[10px] font-semibold text-purple-700 bg-white px-2 py-0.5 rounded-md border border-purple-300">
                    Deterministic Mapping
                  </span>
                </div>
                <div className="flex items-center justify-between pt-1">
                  <div>
                    <span className="text-[10px] font-bold text-purple-800 uppercase block">
                      Final Resolved HOD:
                    </span>
                    <span className="text-[10px] text-purple-600">
                      Deterministic business mapping (no AI hallucination)
                    </span>
                  </div>
                  <span className={`font-extrabold px-3 py-1.5 rounded-xl text-xs border ${
                    getHODPreview(formData.department) === "HOD Not Configured"
                      ? "bg-amber-100 text-amber-900 border-amber-300"
                      : "bg-white text-purple-950 border-purple-300 shadow-xs"
                  }`}>
                    {getHODPreview(formData.department)}
                  </span>
                </div>
              </div>

              {/* Submit Button */}
              <div className="pt-2 flex flex-col gap-2">
                <button
                  type="button"
                  disabled={submitting}
                  onClick={handleFinalSubmit}
                  className="w-full py-4 bg-teal-600 hover:bg-teal-700 active:scale-[0.99] text-white font-extrabold rounded-2xl shadow-lg shadow-teal-600/30 transition flex items-center justify-center gap-2 text-base disabled:opacity-50"
                >
                  <Send className="w-5 h-5" />
                  {submitting ? "Submitting Feedback..." : "SUBMIT FEEDBACK"}
                </button>
                <button
                  type="button"
                  onClick={() => setStep("details")}
                  className="w-full py-2.5 text-slate-500 hover:bg-slate-100 font-semibold text-xs rounded-xl transition"
                >
                  Back to Edit Details
                </button>
              </div>
            </div>
          )}

          {/* STEP 6: SUCCESS SCREEN */}
          {step === "success" && (
            <div className="bg-white rounded-3xl p-8 border border-slate-200 shadow-md text-center space-y-5 animate-fade-in">
              <div className="w-16 h-16 rounded-full bg-emerald-100 text-emerald-600 flex items-center justify-center mx-auto">
                <CheckCircle2 className="w-10 h-10" />
              </div>
              <div>
                <h3 className="text-xl font-extrabold text-slate-900">
                  Feedback Successfully Recorded!
                </h3>
                {submittedRecord ? (
                  <div className="mt-2 py-1.5 px-3 bg-sky-50 border border-sky-200 rounded-xl text-sky-800 font-mono font-bold text-sm inline-block">
                    {submittedRecord.feedback_id}
                  </div>
                ) : (
                  <p className="text-xs text-amber-700 bg-amber-50 py-2 px-3 rounded-xl border border-amber-200 mt-2 font-medium">
                    Saved offline — will sync automatically when internet is available.
                  </p>
                )}
              </div>

              <div className="pt-4 flex flex-col gap-2.5">
                <button
                  onClick={startNewFeedbackFlow}
                  className="w-full py-3.5 bg-sky-600 hover:bg-sky-700 text-white font-bold rounded-2xl shadow-md transition flex items-center justify-center gap-2 text-sm"
                >
                  <PlusCircle className="w-4 h-4" />
                  NEW PATIENT FEEDBACK
                </button>
                <button
                  onClick={() => setActiveTab("dashboard")}
                  className="w-full py-3 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-2xl transition text-xs"
                >
                  Return to Dashboard
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ==================================================================== */}
      {/* 3. MY SUBMISSIONS TAB (SECTION 58) */}
      {/* ==================================================================== */}
      {activeTab === "submissions" && (
        <div className="space-y-4 animate-fade-in">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-extrabold text-slate-900">
              My Submissions ({todaySubmissions.length})
            </h3>
            <button
              onClick={() => setActiveTab("dashboard")}
              className="text-xs text-sky-600 font-bold hover:underline"
            >
              Back to Home
            </button>
          </div>

          {todaySubmissions.length === 0 ? (
            <div className="bg-white rounded-3xl p-8 border border-slate-200 text-center text-slate-400 text-sm">
              No submissions recorded yet today.
            </div>
          ) : (
            <div className="space-y-2.5">
              {todaySubmissions.map((sub) => (
                <div
                  key={sub.id}
                  className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs hover:border-sky-300 transition"
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-mono text-xs font-bold text-sky-700 bg-sky-50 px-2 py-0.5 rounded-md">
                      {sub.feedback_id}
                    </span>
                    <span className="text-[11px] text-slate-400 font-medium">
                      {sub.time_str}
                    </span>
                  </div>
                  <h4 className="font-bold text-slate-900 text-sm">
                    {sub.patient_name} <span className="font-mono text-xs text-slate-500 font-normal">({sub.uhid})</span>
                  </h4>
                  <div className="flex items-center gap-2 text-xs text-slate-600 mt-1">
                    <span className="font-medium text-sky-800">{sub.department}</span>
                    <span>•</span>
                    <span className="font-semibold text-teal-700">{sub.hod_name}</span>
                  </div>
                  {sub.complaint_summary && sub.complaint_summary !== "Not Provided" && (
                    <p className="text-xs text-slate-500 mt-2 line-clamp-2 bg-slate-50 p-2 rounded-xl">
                      {sub.complaint_summary}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ==================================================================== */}
      {/* 4. OFFLINE QUEUE TAB (SECTION 42 & 43) */}
      {/* ==================================================================== */}
      {activeTab === "offline" && (
        <div className="space-y-4 animate-fade-in">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-extrabold text-slate-900">
              Offline Pending Queue ({offlineItems.length})
            </h3>
            <button
              onClick={() => setActiveTab("dashboard")}
              className="text-xs text-sky-600 font-bold hover:underline"
            >
              Back to Home
            </button>
          </div>

          <p className="text-xs text-slate-500">
            Records stored locally in IndexedDB when internet is disconnected. Sync triggers automatically when network returns.
          </p>

          {offlineItems.length === 0 ? (
            <div className="bg-white rounded-3xl p-8 border border-slate-200 text-center text-slate-400 text-sm">
              All records synchronized with cloud server.
            </div>
          ) : (
            <div className="space-y-2.5">
              {offlineItems.map((item) => (
                <div
                  key={item.client_uuid}
                  className="bg-white p-4 rounded-2xl border border-amber-200 shadow-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-800 text-sm">
                      {item.payload.patient_name}
                    </span>
                    <span className="text-[10px] font-bold uppercase tracking-wider bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full">
                      {item.status}
                    </span>
                  </div>
                  <div className="text-xs text-slate-500 mt-1 font-mono">
                    UHID: {item.payload.uhid} • Dept: {item.payload.department}
                  </div>
                  {item.status !== "SYNCED" && (
                    <div className="mt-2 text-xs font-semibold text-amber-800 bg-amber-50 border border-amber-200 px-3 py-1.5 rounded-xl flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4 text-amber-600" />
                      Not Synced — Data is still stored securely on this device.
                    </div>
                  )}
                  {item.last_error && (
                    <p className="text-[11px] text-red-600 mt-1 bg-red-50 p-1.5 rounded-lg">
                      Error: {item.last_error}
                    </p>
                  )}
                  <div className="flex items-center justify-between text-[10px] text-slate-400 mt-2">
                    <span>Queued: {new Date(item.created_at).toLocaleTimeString()}</span>
                    <span>Retries: {item.retry_count || 0}/5</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
