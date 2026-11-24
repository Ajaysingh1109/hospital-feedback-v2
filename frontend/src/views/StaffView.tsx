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
  X,
  RefreshCw,
  Clock,
  Loader2,
  Layers,
  Check,
  HardDrive,
  Trash2,
  Download,
  Volume2,
} from "lucide-react";
import {
  fetchMasterData,
  fetchMySubmissions,
  fetchQueueStatus,
  processAudio,
  processText,
  submitAsyncFeedback,
  submitFeedback,
} from "../services/api";
import {
  clearDraftSession,
  enqueueOfflineFeedback,
  getLatestDraftSession,
  getOfflineQueueItems,
  saveDraftSession,
  saveToAudioVault,
  updateAudioVaultStatus,
  getAudioVaultItems,
  deleteFromAudioVault,
  purgeExpiredAudioVault,
} from "../services/db";
import {
  AudioVaultItem,
  FeedbackRecord,
  MasterData,
  OfflineFeedbackItem,
  ProcessAudioResult,
  QueueJobItem,
  QueueStatusResponse,
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

export const normalizeLocationInput = (raw: string): string => {
  if (!raw) return "";
  const trimmed = raw.trim();
  if (/^pvt\.?(\s*room)?$/i.test(trimmed)) {
    return "Private Room";
  }
  const match = trimmed.match(/^pvt\.?\s*(\d+)$/i);
  if (match) {
    return `Private Room ${match[1]}`;
  }
  const match2 = trimmed.match(/^pvt\.?\s*room\s*(\d+)$/i);
  if (match2) {
    return `Private Room ${match2[1]}`;
  }
  if (/^gw1$/i.test(trimmed)) return "General Ward 1";
  if (/^gw2$/i.test(trimmed)) return "General Ward 2";
  if (/^gw3$/i.test(trimmed)) return "General Ward 3";
  return raw;
};

const AudioVaultPlayer: React.FC<{ blob: Blob }> = ({ blob }) => {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    const objUrl = URL.createObjectURL(blob);
    setUrl(objUrl);
    return () => {
      URL.revokeObjectURL(objUrl);
    };
  }, [blob]);

  if (!url) return null;
  return (
    <audio
      controls
      controlsList="nodownload"
      src={url}
      className="w-full h-8 mt-1 rounded-lg"
    />
  );
};

export const StaffView: React.FC<StaffViewProps> = ({ user, isOnline }) => {
  const [activeTab, setActiveTab] = useState<"dashboard" | "flow" | "submissions" | "vault" | "offline">("dashboard");
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

  // 12-Hour Audio Vault State
  const [audioVaultItems, setAudioVaultItems] = useState<AudioVaultItem[]>([]);

  // Background Processing Queue & Notification State (Section 2, 7)
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [showQueueDrawer, setShowQueueDrawer] = useState<boolean>(false);
  const [queueStatus, setQueueStatus] = useState<QueueStatusResponse>({
    processing_count: 0,
    completed_count: 0,
    needs_review_count: 0,
    items: [],
  });

  // Active Session State
  const [sessionId, setSessionId] = useState<string>("");
  const [audioStream, setAudioStream] = useState<MediaStream | null>(null);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
  const [audioChunks, setAudioChunks] = useState<Blob[]>([]);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const audioBlobRef = useRef<Blob | null>(null);
  const [recordingDuration, setRecordingDuration] = useState<number>(0);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [isPaused, setIsPaused] = useState<boolean>(false);
  const [recordingWarning, setRecordingWarning] = useState<string | null>(null);
  const timerRef = useRef<any>(null);

  // Developer / Test Mode State (Section 9)
  const [developerText, setDeveloperText] = useState<string>(
    "GW1 ke patient ko subah se breakfast nahi mila aur attendant bol raha hai ki abhi tak nahi aaya."
  );
  const [showDevTextMode, setShowDevTextMode] = useState<boolean>(false);

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
    complaint_type: "Complaint",
    complaint_summary: "",
    detailed_feedback: "",
    positive_feedback: "",
    negative_feedback: "",
    specific_complaint: "",
    suggested_action: "",
    priority: "Not Specified",
    original_transcript: "",
    english_translation: "",
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

  const refreshQueueStatus = async () => {
    if (!isOnline) return;
    try {
      const q = await fetchQueueStatus();
      setQueueStatus(q);
    } catch (_) {}
  };

  useEffect(() => {
    if (isOnline) {
      refreshQueueStatus();
      const interval = setInterval(refreshQueueStatus, 6000);
      return () => clearInterval(interval);
    }
  }, [isOnline]);

  const loadAudioVault = async () => {
    try {
      await purgeExpiredAudioVault();
      const items = await getAudioVaultItems();
      setAudioVaultItems(items);
    } catch (e) {
      console.warn("Failed to load audio vault:", e);
    }
  };

  const handleDownloadVaultAudio = (item: AudioVaultItem) => {
    const url = URL.createObjectURL(item.blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Audio_Vault_${item.patient_name || "recording"}_${item.session_id.substring(0, 8)}.webm`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const handleRetryVaultItem = async (item: AudioVaultItem) => {
    setSessionId(item.session_id);
    if (item.patient_name) {
      setFormData((prev) => ({
        ...prev,
        patient_name: item.patient_name || prev.patient_name,
        uhid: item.uhid || prev.uhid,
        department: item.department || prev.department,
      }));
    }
    audioBlobRef.current = item.blob;
    setAudioBlob(item.blob);
    setActiveTab("flow");
    await proceedWithCapturedBlob(item.blob);
  };

  const handleDeleteVaultItem = async (id: string) => {
    if (window.confirm("Are you sure you want to delete this recorded audio from the vault?")) {
      await deleteFromAudioVault(id);
      await loadAudioVault();
    }
  };

  const handleUseVaultItemManual = (item: AudioVaultItem) => {
    setSessionId(item.session_id);
    audioBlobRef.current = item.blob;
    setAudioBlob(item.blob);
    if (item.patient_name) {
      setFormData((prev) => ({
        ...prev,
        patient_name: item.patient_name || prev.patient_name,
        uhid: item.uhid || prev.uhid,
        department: item.department || prev.department,
        original_transcript: item.original_transcript || prev.original_transcript,
        english_translation: item.english_translation || prev.english_translation,
      }));
    }
    setActiveTab("flow");
    setStep("review");
  };

  const loadInitialData = async () => {
    try {
      const md = await fetchMasterData();
      setMasterData(md);
      if (isOnline) {
        const subs = await fetchMySubmissions();
        setTodaySubmissions(subs);
        refreshQueueStatus();
      }
      const queue = await getOfflineQueueItems();
      setOfflineItems(queue);
      await loadAudioVault();
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
      complaint_type: "Complaint",
      complaint_summary: "",
      detailed_feedback: "",
      positive_feedback: "",
      negative_feedback: "",
      specific_complaint: "",
      suggested_action: "",
      priority: "Not Specified",
      original_transcript: "",
      english_translation: "",
    });

    // Step 1: Mandatory Consent Dialog (Section 10 & 19)
    setStep("consent");
    setShowConsentModal(true);
    setActiveTab("flow");
  };

  const handleConsentAgreed = () => {
    setShowConsentModal(false);
    setConsentTimestamp(new Date().toISOString());
    setStep("details");
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
    audioBlobRef.current = null;
    setAudioBlob(null);
    setAudioChunks([]);
    console.log("VOICE_DEBUG: recording_started=true");

    // Secure HTTPS Pre-flight check (Section 9 & Fix 9)
    const isInsecureNonLocalhost =
      window.location.protocol === "http:" &&
      window.location.hostname !== "localhost" &&
      window.location.hostname !== "127.0.0.1";

    if (isInsecureNonLocalhost) {
      alert("Secure HTTPS connection is required for microphone recording.");
      setRecordingWarning("Secure HTTPS connection is required for microphone recording.");
      return;
    }

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
        audioBlobRef.current = fullBlob;
        setAudioBlob(fullBlob);
        setAudioChunks(chunks);
        console.log(`VOICE_DEBUG: recorder_onstop mime_type=${fullBlob.type} size_bytes=${fullBlob.size}`);
        stream.getTracks().forEach((track) => track.stop());
        setStatusBadge("IDLE");

        // Instant safe storage in Audio Vault (12-hour offline safety)
        if (fullBlob.size > 0) {
          saveToAudioVault({
            id: sessionId,
            session_id: sessionId,
            created_at: new Date().toISOString(),
            duration_seconds: recordingDuration,
            blob: fullBlob,
            patient_name: formData.patient_name || undefined,
            uhid: formData.uhid || undefined,
            department: formData.department || undefined,
            status: isOnline ? "RECORDED" : "OFFLINE",
          }).then(() => loadAudioVault()).catch(() => {});
        }

        if (step === "record") {
          setStep("details");
        }
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
      alert("Microphone permission was denied or microphone unavailable. Please allow microphone access in your browser settings to record audio.");
      setIsRecording(false);
      setStatusBadge("IDLE");
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

  const stopRecording = () => {
    clearInterval(timerRef.current);
    setIsRecording(false);
    setIsPaused(false);
    setStatusBadge("IDLE");

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
  };

  const stopAndProcessRecording = () => {
    stopRecording();
  };

  const discardRecording = () => {
    clearInterval(timerRef.current);
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      try { mediaRecorder.stop(); } catch (_) {}
    }
    if (audioStream) {
      audioStream.getTracks().forEach((t) => t.stop());
    }
    audioBlobRef.current = null;
    setAudioBlob(null);
    setAudioChunks([]);
    setRecordingDuration(0);
    setIsRecording(false);
    setIsPaused(false);
    setStatusBadge("IDLE");
  };

  // ============================================================================
  // PROCESSING PIPELINE & AUDIO QUALITY CHECK (SECTION 3 & 49)
  // ============================================================================

  const proceedWithCapturedBlob = async (blob: Blob) => {
    // Audio Quality Check
    if (blob.size < 1500) {
      setLowAudioMessage(`Audio is silent or too short (${blob.size} bytes). Please record again speaking clearly into the microphone.`);
      setShowLowAudioModal(true);
      return;
    }

    // 1. Instantly save to local Audio Vault before any network attempt
    await saveToAudioVault({
      id: sessionId,
      session_id: sessionId,
      created_at: new Date().toISOString(),
      duration_seconds: recordingDuration,
      blob,
      patient_name: formData.patient_name || undefined,
      uhid: formData.uhid || undefined,
      department: formData.department || undefined,
      status: isOnline ? "RECORDED" : "OFFLINE",
    }).catch(() => {});
    loadAudioVault();

    // 2. If completely offline, do NOT hang or trap staff on loading spinner!
    if (!isOnline) {
      setAiResult(null);
      setToastMessage("📶 Offline: Audio safely saved in Audio Vault. Proceeding to review for offline saving.");
      setTimeout(() => setToastMessage(null), 5000);
      setStep("review");
      setStatusBadge("IDLE");
      return;
    }

    setStep("processing");
    setStatusBadge("PROCESSING");
    setProcessingError(null);
    setProcessingStatus(`Connecting & uploading audio (${Math.round(blob.size / 1024)} KB)...`);
    console.log(`VOICE_DEBUG: upload_started=true size_bytes=${blob.size}`);

    try {
      setProcessingStatus("Transcribing conversation (Hindi / Hinglish / English)...");
      const result = await processAudio(blob, sessionId);
      setAiResult(result);
      applyAIResultToForm(result);

      updateAudioVaultStatus(sessionId, "PROCESSED", {
        original_transcript: result.original_transcript,
        english_translation: result.english_translation,
      }).catch(() => {});

      setStep("review");
      setStatusBadge("IDLE");

      saveDraftSession({
        session_id: sessionId,
        started_at: new Date().toISOString(),
        step: "review",
        duration_seconds: recordingDuration,
        form_data: formData,
      });
    } catch (err: any) {
      console.error("AI pipeline error:", err);
      updateAudioVaultStatus(sessionId, "FAILED", {
        last_error: err?.message || "Network / processing failure",
      }).catch(() => {});
      const isNet = err?.message?.includes("timed out") || err?.message?.includes("internet") || err?.message?.includes("connect");
      setProcessingError(
        isNet
          ? "⚠️ Network timed out or internet is disconnected. Audio is safely stored in your Audio Vault! You can continue to review and submit offline, or retry AI processing."
          : (err?.message || "AI processing encountered an issue. Audio is safely stored in your Audio Vault.")
      );
    }
  };

  const applyAIResultToForm = (result: ProcessAudioResult) => {
    const initialComplaint = result.complaint || result.english_translation || result.complaint_summary || "";
    setFormData((prev) => ({
      ...prev,
      original_transcript: result.original_transcript || prev.original_transcript,
      english_translation: result.english_translation || prev.english_translation,
      department: prev.department ? prev.department : (result.suggested_department || ""),
      subcategory: prev.subcategory ? prev.subcategory : (result.suggested_subcategory || ""),
      location: prev.location ? prev.location : (result.suggested_location || ""),
      complaint: initialComplaint || prev.complaint,
      complaint_type: result.complaint_type || prev.complaint_type || "Complaint",
      complaint_summary: result.complaint_summary || prev.complaint_summary,
      detailed_feedback: result.detailed_feedback || prev.detailed_feedback,
      positive_feedback: result.positive_feedback || prev.positive_feedback,
      negative_feedback: result.negative_feedback || prev.negative_feedback,
      specific_complaint: result.specific_complaint || prev.specific_complaint,
      suggested_action: result.suggested_action || prev.suggested_action,
      priority: result.priority || prev.priority,
    }));
  };

  const handleProcessDeveloperText = async () => {
    if (!developerText.trim()) return;
    setStep("processing");
    setStatusBadge("PROCESSING");
    setProcessingError(null);
    setProcessingStatus("Processing text in developer conversion mode...");
    try {
      const result = await processText(developerText.trim(), sessionId);
      setAiResult(result);
      applyAIResultToForm(result);
      setStep("details");
      setStatusBadge("IDLE");
    } catch (err: any) {
      console.error("Developer text conversion error:", err);
      setProcessingError(err?.message || "Text conversion encountered an issue.");
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
  // ASYNC "SAVE & NEXT PATIENT" WORKFLOW (SECTION 1, 2, 3)
  // ============================================================================

  const handleSaveAndNextPatient = async () => {
    // 1. Validate mandatory fields
    const errors: Record<string, string> = {};
    const cleanUhid = String(formData.uhid).trim();
    const cleanName = formData.patient_name.trim();
    const cleanDept = formData.department.trim();
    const currentAudio = audioBlobRef.current || audioBlob;
    const cleanComplaint = formData.complaint.trim();

    if (!cleanUhid) errors.uhid = "UHID is required.";
    if (!cleanName) errors.patient_name = "Patient Name is required.";
    if (!cleanDept) errors.department = "Department is required.";
    if (!currentAudio && !cleanComplaint) {
      errors.audio = "Please record audio feedback or enter a complaint description.";
    }

    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }

    // 2. Capture atomic snapshot before instant state reset
    const activeUuid = sessionId || `uuid-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    const snapshotFormData = {
      ...formData,
      location: normalizeLocationInput(formData.location),
    };
    const snapshotAudio = currentAudio;

    // Stop active recording if running
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      try { mediaRecorder.stop(); } catch (_) {}
    }
    if (audioStream) {
      audioStream.getTracks().forEach((t) => t.stop());
    }
    clearInterval(timerRef.current);

    // 3. INSTANT FORM RESET (<100ms UI response)
    const nextSessionId = `uuid-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    setSessionId(nextSessionId);
    audioBlobRef.current = null;
    setAudioBlob(null);
    setAudioChunks([]);
    setRecordingDuration(0);
    setIsRecording(false);
    setIsPaused(false);
    setFormErrors({});
    setAiResult(null);
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
      complaint_type: "Complaint",
      complaint_summary: "",
      detailed_feedback: "",
      positive_feedback: "",
      negative_feedback: "",
      specific_complaint: "",
      suggested_action: "",
      priority: "Not Specified",
      original_transcript: "",
      english_translation: "",
    });
    setStep("details");
    setStatusBadge("IDLE");
    clearDraftSession();

    // 4. NON-INTRUSIVE NOTIFICATION
    const label = cleanName ? `${cleanName} (${cleanUhid})` : cleanUhid;
    if (isOnline) {
      setToastMessage(`✓ Feedback Saved for ${label} — Processing in Background`);
    } else {
      setToastMessage(`✓ Feedback Saved Offline for ${label} — Will Sync When Online`);
    }
    setTimeout(() => {
      setToastMessage(null);
    }, 4000);

    // 5. SERVER ASYNC DISPATCH (NON-BLOCKING)
    if (isOnline) {
      const fd = new FormData();
      fd.append("client_uuid", activeUuid);
      fd.append("uhid", cleanUhid);
      fd.append("patient_name", cleanName);
      fd.append("department", cleanDept);
      if (snapshotFormData.location?.trim()) fd.append("location", snapshotFormData.location.trim());
      if (snapshotFormData.consultant?.trim()) fd.append("consultant", snapshotFormData.consultant.trim());
      if (snapshotFormData.scheme?.trim()) fd.append("scheme", snapshotFormData.scheme.trim());
      if (snapshotFormData.attendant_name?.trim()) fd.append("attendant_name", snapshotFormData.attendant_name.trim());
      if (cleanComplaint) fd.append("manual_complaint", cleanComplaint);
      if (snapshotAudio) {
        fd.append("audio", snapshotAudio, `${activeUuid}.webm`);
      }

      submitAsyncFeedback(fd)
        .then(() => {
          refreshQueueStatus();
        })
        .catch((err) => {
          console.warn("Async submission error, fallback to local offline queue:", err);
          enqueueOfflineFeedback({
            client_uuid: activeUuid,
            created_at: new Date().toISOString(),
            payload: {
              client_uuid: activeUuid,
              uhid: cleanUhid,
              patient_name: cleanName,
              department: cleanDept,
              location: snapshotFormData.location?.trim(),
              consultant: snapshotFormData.consultant?.trim(),
              scheme: snapshotFormData.scheme?.trim(),
              attendant_name: snapshotFormData.attendant_name?.trim(),
              complaint: cleanComplaint || undefined,
            },
            audio_blob: snapshotAudio || undefined,
            status: "READY",
            retry_count: 0,
            last_error: err?.message,
          }).then(() => {
            getOfflineQueueItems().then(setOfflineItems);
          });
        });
    } else {
      enqueueOfflineFeedback({
        client_uuid: activeUuid,
        created_at: new Date().toISOString(),
        payload: {
          client_uuid: activeUuid,
          uhid: cleanUhid,
          patient_name: cleanName,
          department: cleanDept,
          location: snapshotFormData.location?.trim(),
          consultant: snapshotFormData.consultant?.trim(),
          scheme: snapshotFormData.scheme?.trim(),
          attendant_name: snapshotFormData.attendant_name?.trim(),
          complaint: cleanComplaint || undefined,
        },
        audio_blob: snapshotAudio || undefined,
        status: "READY",
        retry_count: 0,
      }).then(() => {
        getOfflineQueueItems().then(setOfflineItems);
      });
    }
  };

  const handleReviewManually = async () => {
    if (!validatePatientDetails()) {
      return;
    }
    const currentAudio = audioBlobRef.current || audioBlob;
    if (currentAudio) {
      proceedWithCapturedBlob(currentAudio);
    } else {
      setStep("review");
      saveDraftSession({
        session_id: sessionId,
        started_at: new Date().toISOString(),
        step: "review",
        duration_seconds: recordingDuration,
        form_data: formData,
      });
    }
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
      location: normalizeLocationInput(formData.location) || undefined,
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
      original_transcript: formData.original_transcript || aiResult?.original_transcript || "",
      english_translation: formData.english_translation || formData.complaint || aiResult?.english_translation || "",
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
  // Supports single or multi-department selection (up to 4)
  const getHODPreview = (dept: string) => {
    if (!dept || !dept.trim()) return "HOD Not Configured";
    const depts = dept
      .split(",")
      .map((d) => d.trim().toLowerCase())
      .filter(Boolean);
    if (depts.length === 0) return "HOD Not Configured";

    const mappedHods: string[] = [];
    for (const clean of depts) {
      let hod = "HOD Not Configured";
      if (clean === "clinical") hod = "Tanveer Sir";
      else if (clean === "nursing") hod = "Reshmi Ma'am";
      else if (clean === "pharmacy") hod = "Vijay Sir";
      else if (clean === "it") hod = "Valay Sir";
      else if (
        [
          "maintenance",
          "f&b",
          "housekeeping",
          "operations",
          "billing",
        ].includes(clean)
      ) {
        hod = "Asha Ma'am";
      }
      if (!mappedHods.includes(hod)) {
        mappedHods.push(hod);
      }
    }
    return mappedHods.join(", ") || "HOD Not Configured";
  };

  // Selected departments array (max 4)
  const selectedDepts = formData.department
    ? formData.department
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
    : [];

  const handleToggleDepartment = (deptName: string) => {
    const trimmed = deptName.trim();
    if (!trimmed) return;
    if (selectedDepts.includes(trimmed)) {
      const updated = selectedDepts.filter((d) => d !== trimmed).join(", ");
      setFormData({ ...formData, department: updated });
    } else {
      if (selectedDepts.length >= 4) {
        alert("Maximum 4 departments can be selected.");
        return;
      }
      const updated = [...selectedDepts, trimmed].join(", ");
      setFormData({ ...formData, department: updated });
      if (formErrors.department) {
        setFormErrors({ ...formErrors, department: "" });
      }
    }
  };

  const handleRemoveDepartment = (deptName: string) => {
    const trimmed = deptName.trim();
    const updated = selectedDepts.filter((d) => d !== trimmed).join(", ");
    setFormData({ ...formData, department: updated });
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
            setFormData({
              ...recoveredDraft.form_data,
              original_transcript: recoveredDraft.form_data.original_transcript || "",
              english_translation: recoveredDraft.form_data.english_translation || "",
            });
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
        onContinue={() => {
          setShowLowAudioModal(false);
          if (audioBlobRef.current) {
            proceedWithCapturedBlob(audioBlobRef.current);
          } else {
            setStep("details");
          }
        }}
      />

      {/* Non-intrusive Toast Notification Banner (Section 2, 7) */}
      {toastMessage && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 max-w-md w-full px-4 pointer-events-none animate-fade-in">
          <div className="bg-emerald-900/95 backdrop-blur-md text-white px-4 py-3 rounded-2xl shadow-2xl flex items-center gap-3 border border-emerald-500">
            <CheckCircle2 className="w-5 h-5 text-emerald-300 shrink-0" />
            <span className="text-xs font-bold leading-snug">{toastMessage}</span>
          </div>
        </div>
      )}

      {/* Queue Status Top Bar Indicator (Section 7) */}
      <div
        onClick={() => setShowQueueDrawer(true)}
        className="mb-3 px-3.5 py-2 rounded-2xl bg-slate-900 text-white shadow-md border border-slate-700 flex items-center justify-between cursor-pointer hover:bg-slate-800 transition"
      >
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${
            queueStatus.processing_count > 0 ? "bg-sky-400 animate-ping" : "bg-emerald-400"
          }`} />
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1">
            <Layers className="w-3.5 h-3.5 text-sky-400" />
            Queue:
          </span>
        </div>
        <div className="flex items-center gap-2 text-[11px] font-semibold">
          <span className="px-2 py-0.5 rounded-md bg-sky-900/60 text-sky-200 border border-sky-700">
            Proc: {queueStatus.processing_count}
          </span>
          <span className="px-2 py-0.5 rounded-md bg-emerald-900/60 text-emerald-200 border border-emerald-700">
            Done: {queueStatus.completed_count}
          </span>
          {queueStatus.needs_review_count > 0 && (
            <span className="px-2 py-0.5 rounded-md bg-red-900/70 text-red-200 border border-red-700 font-bold animate-pulse">
              Review: {queueStatus.needs_review_count}
            </span>
          )}
          {offlineItems.length > 0 && (
            <span className="px-2 py-0.5 rounded-md bg-amber-900/60 text-amber-200 border border-amber-700 font-bold">
              Offline: {offlineItems.length}
            </span>
          )}
          {audioVaultItems.length > 0 && (
            <span
              onClick={(e) => {
                e.stopPropagation();
                loadAudioVault();
                setActiveTab("vault");
              }}
              className="px-2 py-0.5 rounded-md bg-indigo-900/70 text-indigo-200 border border-indigo-700 font-bold hover:bg-indigo-800 transition flex items-center gap-1"
            >
              <HardDrive className="w-3 h-3 text-indigo-300" />
              Vault: {audioVaultItems.length}
            </span>
          )}
        </div>
      </div>

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
          {/* Welcome Card & Mobile Branding (Section 21) */}
          <div className="bg-gradient-to-br from-teal-800 via-teal-700 to-emerald-700 rounded-3xl p-5 text-white shadow-xl">
            <div className="flex items-center justify-between">
              <div>
                <span className="text-[10px] font-extrabold tracking-widest uppercase text-emerald-200 block">
                  POWERED BY SAARTHI-ONE
                </span>
                <h1 className="text-2xl font-black text-white mt-0.5 tracking-tight">
                  FEEDBACK MAC
                </h1>
                <p className="text-xs text-teal-100 font-medium mt-0.5">
                  Station: {user.display_name}
                </p>
              </div>
              <div className="flex flex-col items-end gap-1.5">
                <div className="w-11 h-11 bg-white/15 backdrop-blur-md rounded-2xl flex items-center justify-center">
                  <User className="w-6 h-6 text-white" />
                </div>
                {/* Network Status Indicator */}
                <div className={`px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider flex items-center gap-1 border ${
                  isOnline
                    ? "bg-emerald-500/30 text-emerald-100 border-emerald-400/50"
                    : "bg-amber-500/40 text-amber-100 border-amber-300/50 animate-pulse"
                }`}>
                  {isOnline ? (
                    <>
                      <Wifi className="w-3 h-3 text-emerald-200" />
                      <span>ONLINE</span>
                    </>
                  ) : (
                    <>
                      <WifiOff className="w-3 h-3 text-amber-200" />
                      <span>OFFLINE</span>
                    </>
                  )}
                </div>
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
              className="mt-5 w-full py-4 bg-white text-teal-950 hover:bg-teal-50 active:scale-[0.99] font-black rounded-2xl shadow-lg transition flex items-center justify-center gap-2.5 text-base"
            >
              <PlusCircle className="w-6 h-6 text-emerald-600" />
              + NEW FEEDBACK
            </button>
          </div>

          {/* Quick Metrics Cards: Processing | Completed | Needs Review (Section 21) */}
          <div className="grid grid-cols-3 gap-2.5">
            <div
              onClick={() => setShowQueueDrawer(true)}
              className="bg-white p-3.5 rounded-2xl border border-slate-200 shadow-xs cursor-pointer hover:border-sky-300 transition text-center"
            >
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide block">
                Processing
              </span>
              <span className="text-2xl font-black text-sky-700 mt-1 block">
                {queueStatus.processing_count}
              </span>
              <span className="text-[10px] text-sky-600 font-semibold flex items-center justify-center gap-0.5 mt-0.5">
                Active <ChevronRight className="w-3 h-3" />
              </span>
            </div>

            <div
              onClick={() => setActiveTab("submissions")}
              className="bg-white p-3.5 rounded-2xl border border-slate-200 shadow-xs cursor-pointer hover:border-emerald-300 transition text-center"
            >
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide block">
                Completed
              </span>
              <span className="text-2xl font-black text-emerald-700 mt-1 block">
                {queueStatus.completed_count}
              </span>
              <span className="text-[10px] text-emerald-600 font-semibold flex items-center justify-center gap-0.5 mt-0.5">
                Verified <ChevronRight className="w-3 h-3" />
              </span>
            </div>

            <div
              onClick={() => setShowQueueDrawer(true)}
              className={`bg-white p-3.5 rounded-2xl border shadow-xs cursor-pointer transition text-center ${
                queueStatus.needs_review_count > 0 ? "border-red-300 bg-red-50/20" : "border-slate-200 hover:border-red-300"
              }`}
            >
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide block">
                Needs Review
              </span>
              <span className={`text-2xl font-black mt-1 block ${queueStatus.needs_review_count > 0 ? "text-red-600" : "text-slate-800"}`}>
                {queueStatus.needs_review_count}
              </span>
              <span className="text-[10px] text-red-600 font-semibold flex items-center justify-center gap-0.5 mt-0.5">
                Inspect <ChevronRight className="w-3 h-3" />
              </span>
            </div>
          </div>

          {/* Action Navigation Buttons */}
          <div className="grid grid-cols-3 gap-2 pt-1">
            <button
              onClick={() => setActiveTab("submissions")}
              className="py-3 px-2 bg-white border border-slate-200 rounded-2xl font-bold text-slate-700 hover:bg-slate-50 shadow-xs transition flex flex-col items-center justify-center gap-1 text-[11px]"
            >
              <History className="w-4 h-4 text-sky-600" />
              <span>SUBMISSIONS</span>
            </button>
            <button
              onClick={() => {
                loadAudioVault();
                setActiveTab("vault");
              }}
              className="py-3 px-2 bg-white border border-indigo-200 rounded-2xl font-bold text-indigo-900 hover:bg-indigo-50/50 shadow-xs transition flex flex-col items-center justify-center gap-1 text-[11px] relative"
            >
              <HardDrive className="w-4 h-4 text-indigo-600" />
              <span>AUDIO VAULT</span>
              {audioVaultItems.length > 0 && (
                <span className="absolute -top-1.5 -right-1.5 bg-indigo-600 text-white text-[9px] font-black w-5 h-5 rounded-full flex items-center justify-center shadow-xs">
                  {audioVaultItems.length}
                </span>
              )}
            </button>
            <button
              onClick={() => setActiveTab("offline")}
              className="py-3 px-2 bg-white border border-slate-200 rounded-2xl font-bold text-slate-700 hover:bg-slate-50 shadow-xs transition flex flex-col items-center justify-center gap-1 text-[11px] relative"
            >
              <CloudUpload className="w-4 h-4 text-teal-600" />
              <span>OFFLINE ({offlineItems.length})</span>
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

              {/* Developer / QA Test Mode (Section 9) */}
              <div className="w-full pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowDevTextMode(!showDevTextMode)}
                  className="text-xs font-semibold text-slate-500 hover:text-sky-600 flex items-center justify-center gap-1.5 mx-auto"
                >
                  <Cpu className="w-3.5 h-3.5" />
                  {showDevTextMode ? "Hide Developer Test Mode" : "Developer Test Mode (Direct Text Conversion)"}
                </button>

                {showDevTextMode && (
                  <div className="mt-3 p-4 bg-slate-50 border border-slate-200 rounded-2xl text-left space-y-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-slate-700 uppercase tracking-wide">
                        Isolate AI Conversion from Microphone
                      </span>
                      <span className="text-[10px] bg-sky-100 text-sky-700 font-bold px-2 py-0.5 rounded-full">
                        QA Test
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500">
                      Tests faithful transcription, Hindi/Hinglish translation, shorthand normalization (GW1 &rarr; General Ward 1), and structuring directly without microphone capture.
                    </p>
                    <textarea
                      value={developerText}
                      onChange={(e) => setDeveloperText(e.target.value)}
                      rows={2}
                      className="w-full text-xs p-2.5 bg-white border border-slate-300 rounded-xl focus:ring-2 focus:ring-sky-500 font-medium"
                      placeholder="Enter raw Hindi or Hinglish spoken text..."
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={handleProcessDeveloperText}
                        className="py-2 px-4 bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs rounded-xl shadow-xs transition"
                      >
                        Run Text-to-English Conversion &rarr;
                      </button>
                    </div>
                  </div>
                )}
              </div>
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
                  <div className="flex flex-wrap gap-2 justify-center">
                    <button
                      onClick={() => {
                        setAudioBlob(null);
                        setProcessingError(null);
                        setStep("record");
                      }}
                      className="py-2 px-4 bg-teal-600 text-white text-xs font-bold rounded-xl shadow-xs hover:bg-teal-700 transition"
                    >
                      Record Again
                    </button>
                    <button
                      onClick={() => {
                        if (audioBlobRef.current) {
                          proceedWithCapturedBlob(audioBlobRef.current);
                        } else {
                          setStep("record");
                        }
                      }}
                      className="py-2 px-4 bg-sky-600 text-white text-xs font-bold rounded-xl shadow-xs hover:bg-sky-700 transition"
                    >
                      Retry AI Analysis
                    </button>
                    <button
                      onClick={() => setStep("review")}
                      className="py-2 px-4 bg-emerald-600 text-white text-xs font-bold rounded-xl shadow-xs hover:bg-emerald-700 transition"
                    >
                      ✓ Continue to Review & Submit Offline
                    </button>
                    <button
                      onClick={() => {
                        loadAudioVault();
                        setActiveTab("vault");
                      }}
                      className="py-2 px-4 bg-indigo-50 border border-indigo-200 text-indigo-700 text-xs font-semibold rounded-xl hover:bg-indigo-100 transition flex items-center gap-1"
                    >
                      <HardDrive className="w-3.5 h-3.5" />
                      View in Audio Vault
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
                  onUseAI={() => {
                    const aiDept = aiResult.suggested_department!;
                    if (!selectedDepts.includes(aiDept)) {
                      if (selectedDepts.length < 4) {
                        const updated = [...selectedDepts, aiDept].join(", ");
                        setFormData({ ...formData, department: updated });
                      } else {
                        setFormData({ ...formData, department: aiDept });
                      }
                    }
                  }}
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

              {/* Mandatory Department Selection (Supports up to 4 departments) */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Department(s) <span className="text-red-500">*</span>
                    <span className="text-[10px] font-normal text-slate-500 lowercase ml-1">
                      (max 4)
                    </span>
                  </label>
                  <span
                    className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full transition ${
                      selectedDepts.length >= 4
                        ? "bg-amber-100 text-amber-800 border border-amber-300"
                        : selectedDepts.length > 0
                        ? "bg-sky-100 text-sky-800 border border-sky-200"
                        : "bg-slate-100 text-slate-500 border border-slate-200"
                    }`}
                  >
                    {selectedDepts.length}/4 Selected
                  </span>
                </div>

                {/* Selected Department Badges */}
                {selectedDepts.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mb-2.5 p-2 bg-sky-50/70 rounded-2xl border border-sky-200 animate-fade-in">
                    {selectedDepts.map((d) => (
                      <span
                        key={d}
                        className="inline-flex items-center gap-1.5 bg-sky-600 text-white text-xs font-bold px-2.5 py-1 rounded-xl shadow-xs"
                      >
                        {d}
                        <button
                          type="button"
                          onClick={() => handleRemoveDepartment(d)}
                          className="hover:bg-sky-700 rounded-full p-0.5 transition"
                          title={`Remove ${d}`}
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                )}

                {/* Dropdown Selector */}
                <select
                  value=""
                  onChange={(e) => {
                    if (e.target.value) {
                      handleToggleDepartment(e.target.value);
                    }
                  }}
                  disabled={selectedDepts.length >= 4}
                  className={`w-full px-4 py-3 bg-slate-50 border rounded-2xl text-sm font-semibold focus:outline-none focus:ring-2 focus:ring-sky-500 ${
                    formErrors.department ? "border-red-400 bg-red-50" : "border-slate-200"
                  } ${selectedDepts.length >= 4 ? "opacity-60 cursor-not-allowed" : ""}`}
                >
                  <option value="">
                    {selectedDepts.length >= 4
                      ? "Maximum 4 departments reached"
                      : selectedDepts.length === 0
                      ? "-- Select Hospital Department (Max 4) --"
                      : "+ Add Another Department (Up to 4)..."}
                  </option>
                  {masterData.departments
                    .filter((d) => !selectedDepts.includes(d.name))
                    .map((d) => (
                      <option key={d.id} value={d.name}>
                        {d.name}
                      </option>
                    ))}
                </select>

                {/* Quick Touch Chips for Mobile Staff */}
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {masterData.departments.map((d) => {
                    const isSelected = selectedDepts.includes(d.name);
                    return (
                      <button
                        key={d.id}
                        type="button"
                        onClick={() => handleToggleDepartment(d.name)}
                        className={`text-xs px-2.5 py-1 rounded-xl font-medium transition flex items-center gap-1 ${
                          isSelected
                            ? "bg-sky-700 text-white font-bold shadow-xs ring-1 ring-sky-500"
                            : "bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200"
                        }`}
                      >
                        {isSelected && <Check className="w-3 h-3" />}
                        {d.name}
                      </button>
                    );
                  })}
                </div>

                {formErrors.department && (
                  <span className="text-red-600 text-xs mt-1.5 block font-medium">
                    {formErrors.department}
                  </span>
                )}
              </div>

              {/* Deterministic HOD Live Preview */}
              {formData.department && (
                <div className="bg-sky-50 border border-sky-100 rounded-2xl p-3 text-xs flex items-center justify-between">
                  <span className="text-slate-600 font-medium">
                    {selectedDepts.length > 1 ? "Mapped HODs:" : "Mapped HOD:"}
                  </span>
                  <span className={`font-extrabold px-2.5 py-1 rounded-lg border text-right ${
                    getHODPreview(formData.department).includes("HOD Not Configured")
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
                    onBlur={(e) => {
                      const norm = normalizeLocationInput(e.target.value);
                      if (norm !== e.target.value) {
                        setFormData((prev) => ({ ...prev, location: norm }));
                      }
                    }}
                    placeholder="Ward 3B, Bed 12 (or 'pvt')"
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

              {/* VOICE RECORDING & AUDIO CAPTURE CARD (SECTION 1, 2) */}
              <div className="pt-2 border-t border-slate-200">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-slate-700 uppercase tracking-wider flex items-center gap-1.5">
                    <Mic className="w-4 h-4 text-teal-600" />
                    Patient Voice Feedback <span className="text-slate-400 font-normal">(Hindi / Hinglish / English)</span>
                  </span>
                  {audioBlob && (
                    <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                      ✓ Audio Attached
                    </span>
                  )}
                </div>

                {isRecording ? (
                  <div className="p-4 bg-red-50/50 border border-red-200 rounded-2xl flex flex-col items-center space-y-3">
                    <div className="flex items-center gap-2 text-red-600 font-extrabold text-xs uppercase tracking-wider animate-pulse">
                      <span className="w-2.5 h-2.5 rounded-full bg-red-600 animate-ping" />
                      Listening... ({formatTimer(recordingDuration)})
                    </div>
                    <AudioVisualizer
                      stream={audioStream}
                      isRecording={isRecording}
                      isPaused={isPaused}
                    />
                    <div className="flex items-center gap-3">
                      {!isPaused ? (
                        <button
                          type="button"
                          onClick={pauseRecording}
                          className="py-2 px-3.5 bg-amber-100 hover:bg-amber-200 text-amber-800 text-xs font-bold rounded-xl flex items-center gap-1"
                        >
                          <Pause className="w-3.5 h-3.5" /> Pause
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={resumeRecording}
                          className="py-2 px-3.5 bg-emerald-100 hover:bg-emerald-200 text-emerald-800 text-xs font-bold rounded-xl flex items-center gap-1"
                        >
                          <Play className="w-3.5 h-3.5 fill-current" /> Resume
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={stopRecording}
                        className="py-2.5 px-5 bg-red-600 hover:bg-red-700 text-white font-extrabold text-xs rounded-xl shadow-md flex items-center gap-1.5"
                      >
                        <Square className="w-3.5 h-3.5 fill-current" /> STOP RECORDING
                      </button>
                    </div>
                  </div>
                ) : audioBlob ? (
                  <div className="p-3.5 bg-teal-50/60 border border-teal-200 rounded-2xl space-y-2">
                    <div className="flex items-center justify-between text-xs font-medium text-teal-900">
                      <span className="flex items-center gap-1.5 font-bold">
                        <CheckCircle2 className="w-4 h-4 text-teal-600" />
                        Audio Captured ({recordingDuration}s, {Math.round(audioBlob.size / 1024)} KB)
                      </span>
                      <button
                        type="button"
                        onClick={discardRecording}
                        className="text-xs font-bold text-red-600 hover:bg-red-50 px-2 py-1 rounded-lg transition"
                      >
                        Re-record
                      </button>
                    </div>
                    <audio
                      src={URL.createObjectURL(audioBlob)}
                      controls
                      className="w-full h-8"
                    />
                  </div>
                ) : (
                  <div className="p-4 bg-slate-50 border border-slate-200 rounded-2xl flex flex-col items-center text-center space-y-2">
                    <button
                      type="button"
                      onClick={startRecording}
                      className="w-full py-3.5 bg-gradient-to-r from-sky-600 to-teal-600 hover:from-sky-700 hover:to-teal-700 text-white font-extrabold rounded-xl shadow-md transition flex items-center justify-center gap-2 text-xs"
                    >
                      <Mic className="w-4 h-4" />
                      RECORD PATIENT / ATTENDANT VOICE
                    </button>
                    <span className="text-[11px] text-slate-400">
                      Tap to record spoken Hindi, Hinglish, or English complaint
                    </span>
                  </div>
                )}

                {formErrors.audio && (
                  <span className="text-red-600 text-xs mt-1.5 block font-medium">
                    {formErrors.audio}
                  </span>
                )}
              </div>

              {/* FEEDBACK CATEGORY / TYPE: Complaint | Suggestion | Request */}
              <div className="pt-2">
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1.5">
                  Feedback Type <span className="text-red-500">*</span>
                </label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { type: "Complaint", label: "⚠️ Complaint", activeClass: "bg-red-600 text-white border-red-600 shadow-sm" },
                    { type: "Suggestion", label: "💡 Suggestion", activeClass: "bg-amber-600 text-white border-amber-600 shadow-sm" },
                    { type: "Request", label: "📋 Request", activeClass: "bg-sky-600 text-white border-sky-600 shadow-sm" },
                  ].map((item) => {
                    const isSelected = formData.complaint_type === item.type;
                    return (
                      <button
                        key={item.type}
                        type="button"
                        onClick={() => setFormData({ ...formData, complaint_type: item.type })}
                        className={`py-2 px-2 text-xs font-bold rounded-xl border transition text-center ${
                          isSelected
                            ? item.activeClass
                            : "bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200"
                        }`}
                      >
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Optional Manual Complaint / Notes Text */}
              <div className="pt-2">
                <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider mb-1">
                  Manual Complaint / Notes <span className="text-slate-400 font-normal">(Optional if voice recorded)</span>
                </label>
                <textarea
                  rows={2}
                  value={formData.complaint}
                  onChange={(e) => setFormData({ ...formData, complaint: e.target.value })}
                  placeholder="Type notes or direct complaint if not speaking..."
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-sky-500 focus:outline-none"
                />
              </div>

              {/* ACTION BUTTONS: PRIMARY FAST ASYNC PATH VS MANUAL REVIEW */}
              <div className="pt-3 space-y-2">
                <button
                  type="button"
                  onClick={handleSaveAndNextPatient}
                  className="w-full py-4 bg-gradient-to-r from-teal-600 to-emerald-600 hover:from-teal-700 hover:to-emerald-700 active:scale-[0.99] text-white font-black rounded-2xl shadow-xl shadow-teal-600/30 transition flex items-center justify-center gap-2 text-base"
                >
                  <CheckCircle2 className="w-5 h-5 text-teal-200" />
                  SAVE & NEXT PATIENT
                </button>
                <button
                  type="button"
                  onClick={handleReviewManually}
                  className="w-full py-2.5 text-slate-500 hover:text-sky-700 hover:bg-sky-50 font-semibold text-xs rounded-xl transition flex items-center justify-center gap-1.5"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                  Review Manually (Optional)
                </button>
              </div>
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

              {/* BLOCK 1: STAFF-ENTERED INFORMATION */}
              <div className="bg-emerald-50/30 border border-emerald-200 rounded-2xl p-4 text-xs space-y-3">
                <div className="flex items-center justify-between border-b border-emerald-200 pb-2">
                  <span className="font-extrabold text-slate-800 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                    <UserCheck className="w-4 h-4 text-emerald-600" />
                    1. Patient Details
                  </span>
                  <span className="text-[10px] font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-md border border-emerald-300">
                    [Staff Entered]
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

              {/* BLOCK 2: ORIGINAL SPEECH / TRANSCRIPT (WITHOUT TRANSLATE - EDITABLE) */}
              <div className="bg-amber-50/40 border border-amber-200 rounded-2xl p-4 text-xs space-y-2">
                <div className="flex items-center justify-between border-b border-amber-200 pb-2">
                  <span className="font-extrabold text-amber-950 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                    <Mic className="w-4 h-4 text-amber-600" />
                    2. Original Speech / Transcript (Without Translate)
                  </span>
                  <span className="text-[10px] font-bold text-amber-800 bg-amber-100 px-2 py-0.5 rounded-md border border-amber-300 flex items-center gap-1">
                    <Edit3 className="w-3 h-3 text-amber-700" /> Editable
                  </span>
                </div>
                <div>
                  <span className="text-[10px] text-slate-500 block mb-1">
                    Verbatim spoken conversation preserved (Staff may edit Hindi/Hinglish speech):
                  </span>
                  <textarea
                    rows={3}
                    value={formData.original_transcript || (aiResult?.original_transcript || "")}
                    onChange={(e) => setFormData({ ...formData, original_transcript: e.target.value })}
                    placeholder="Verbatim spoken conversation in Hindi, Hinglish, or English..."
                    className="w-full p-2.5 bg-white border border-amber-300 rounded-xl text-slate-800 text-xs font-mono leading-relaxed focus:ring-2 focus:ring-amber-500 focus:outline-none"
                  />
                </div>
              </div>

              {/* BLOCK 3: AI-GENERATED CONTENT (EDITABLE) */}
              <div className="bg-sky-50/50 border border-sky-200 rounded-2xl p-4 text-xs space-y-3">
                <div className="flex items-center justify-between border-b border-sky-200 pb-2">
                  <span className="font-extrabold text-sky-900 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                    <Bot className="w-4 h-4 text-sky-600" />
                    3. AI-Generated Content
                  </span>
                  <span className="text-[10px] font-bold text-sky-800 bg-sky-100 px-2 py-0.5 rounded-md border border-sky-300">
                    [AI Generated - Editable]
                  </span>
                </div>

                {aiResult?.diagnostics && (
                  <div className="bg-white/80 p-2 rounded-xl border border-sky-100 flex flex-wrap items-center gap-2 text-[10px] text-slate-600 font-mono">
                    <span className="font-bold text-sky-800">DIAGNOSTICS:</span>
                    <span className={aiResult.diagnostics.STT_SUCCESS ? "text-emerald-700" : "text-amber-700"}>
                      STT_SUCCESS={String(aiResult.diagnostics.STT_SUCCESS)}
                    </span>
                    <span className={aiResult.diagnostics.TRANSCRIPT_PRESENT ? "text-emerald-700" : "text-red-700"}>
                      TRANSCRIPT_PRESENT={String(aiResult.diagnostics.TRANSCRIPT_PRESENT)}
                    </span>
                    <span className={aiResult.diagnostics.TRANSLATION_SUCCESS ? "text-emerald-700" : "text-red-700"}>
                      TRANSLATION_SUCCESS={String(aiResult.diagnostics.TRANSLATION_SUCCESS)}
                    </span>
                    <span className={aiResult.diagnostics.AI_ANALYSIS_SUCCESS ? "text-emerald-700" : "text-red-700"}>
                      AI_ANALYSIS_SUCCESS={String(aiResult.diagnostics.AI_ANALYSIS_SUCCESS)}
                    </span>
                  </div>
                )}

                {!isOnline && (
                  <div className="p-3 bg-amber-50 border border-amber-300 rounded-xl text-amber-900 text-xs font-semibold flex items-center gap-2 shadow-xs">
                    <WifiOff className="w-4 h-4 text-amber-600 flex-shrink-0" />
                    <span>Saved Offline — will process automatically when internet is available.</span>
                  </div>
                )}

                {/* Professional English Complaint / Translation */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[10px] font-bold text-sky-900 uppercase flex items-center gap-1">
                      Professional English Complaint (With Translate - Editable)
                    </label>
                    <span className="text-[10px] text-sky-600 font-bold flex items-center gap-0.5">
                      <Edit3 className="w-3 h-3" /> Editable
                    </span>
                  </div>
                  <textarea
                    rows={3}
                    value={formData.complaint || formData.english_translation || (aiResult?.english_translation || "")}
                    onChange={(e) => setFormData({ ...formData, complaint: e.target.value, english_translation: e.target.value })}
                    placeholder="Enter or refine final English complaint statement..."
                    className="w-full p-3 bg-white border border-sky-300 rounded-xl text-slate-900 text-xs font-medium focus:ring-2 focus:ring-sky-500 focus:outline-none"
                  />
                </div>

                {/* Short Summary (Editable by staff) */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[10px] font-bold text-sky-900 uppercase flex items-center gap-1">
                      Short Summary <span className="text-slate-400 font-normal">(1-sentence factual summary of spoken issue only)</span>
                    </label>
                    <span className="text-[10px] text-sky-600 font-bold flex items-center gap-0.5">
                      <Edit3 className="w-3 h-3" /> Editable
                    </span>
                  </div>
                  <textarea
                    rows={2}
                    value={formData.complaint_summary}
                    onChange={(e) => setFormData({ ...formData, complaint_summary: e.target.value })}
                    placeholder="1-sentence factual summary..."
                    className="w-full p-2.5 bg-white border border-sky-300 rounded-xl text-slate-900 text-xs font-medium focus:ring-2 focus:ring-sky-500 focus:outline-none"
                  />
                </div>

                {/* Feedback Type: Complaint | Suggestion | Request */}
                <div>
                  <label className="text-[10px] font-bold text-slate-600 uppercase block mb-1.5">
                    Feedback Type:
                  </label>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { type: "Complaint", label: "⚠️ Complaint", activeClass: "bg-red-600 text-white border-red-600 shadow-sm" },
                      { type: "Suggestion", label: "💡 Suggestion", activeClass: "bg-amber-600 text-white border-amber-600 shadow-sm" },
                      { type: "Request", label: "📋 Request", activeClass: "bg-sky-600 text-white border-sky-600 shadow-sm" },
                    ].map((item) => {
                      const isSelected = formData.complaint_type === item.type;
                      return (
                        <button
                          key={item.type}
                          type="button"
                          onClick={() => setFormData({ ...formData, complaint_type: item.type })}
                          className={`py-2 px-2 text-xs font-bold rounded-xl border transition text-center ${
                            isSelected
                              ? item.activeClass
                              : "bg-white hover:bg-slate-50 text-slate-700 border-slate-200"
                          }`}
                        >
                          {item.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* BLOCK 4: SYSTEM-CONTROLLED */}
              <div className="bg-purple-50/70 border border-purple-200 rounded-2xl p-4 text-xs space-y-2">
                <div className="flex items-center justify-between border-b border-purple-200 pb-2">
                  <span className="font-extrabold text-purple-900 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                    <Cpu className="w-4 h-4 text-purple-600" />
                    4. System-Controlled
                  </span>
                  <span className="text-[10px] font-bold text-purple-800 bg-purple-100 px-2 py-0.5 rounded-md border border-purple-300">
                    [System Resolved]
                  </span>
                </div>
                <div className="flex items-center justify-between pt-1">
                  <div>
                    <span className="text-[10px] font-bold text-purple-800 uppercase block">
                      Final Resolved HOD:
                    </span>
                    <span className="text-[10px] text-purple-600">
                      Deterministic business mapping strictly from selected department (no AI guessing)
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

      {/* ==================================================================== */}
      {/* 5. AUDIO VAULT TAB (12-HOUR AUTO PURGE & OFFLINE SAFETY) */}
      {/* ==================================================================== */}
      {activeTab === "vault" && (
        <div className="space-y-4 animate-fade-in">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-extrabold text-slate-900 flex items-center gap-2">
                <HardDrive className="w-5 h-5 text-indigo-600" />
                Audio Recording Vault ({audioVaultItems.length})
              </h3>
              <p className="text-[11px] text-slate-500 font-medium">
                12-Hour Auto Purge • Local Device Storage • Offline Safe
              </p>
            </div>
            <button
              onClick={() => setActiveTab("dashboard")}
              className="text-xs text-sky-600 font-bold hover:underline"
            >
              Back to Home
            </button>
          </div>

          <div className="bg-indigo-50 border border-indigo-200 rounded-2xl p-3 text-xs text-indigo-950 flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-indigo-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold">Offline Protected Audio Vault:</span>
              <p className="text-[11px] text-indigo-800 mt-0.5 leading-relaxed">
                If the internet disconnects during recording or AI analysis, your audio is safe here. Recordings are automatically deleted after 12 hours to conserve device storage.
              </p>
            </div>
          </div>

          {audioVaultItems.length === 0 ? (
            <div className="bg-white rounded-3xl p-8 border border-slate-200 text-center text-slate-400 text-sm">
              <HardDrive className="w-10 h-10 text-slate-300 mx-auto mb-2" />
              <p className="font-semibold text-slate-600">No audios currently stored in vault.</p>
              <p className="text-xs text-slate-400 mt-1">
                Every voice recording is automatically backed up here for 12 hours.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {audioVaultItems.map((item) => {
                const ageMs = Date.now() - new Date(item.created_at).getTime();
                const total12h = 12 * 60 * 60 * 1000;
                const msLeft = Math.max(0, total12h - ageMs);
                const hoursLeft = Math.floor(msLeft / (60 * 60 * 1000));
                const minsLeft = Math.floor((msLeft % (60 * 60 * 1000)) / (60 * 1000));

                return (
                  <div
                    key={item.id}
                    className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs hover:border-indigo-300 transition"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[11px] font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-md">
                          {item.session_id.substring(0, 14)}...
                        </span>
                        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                          item.status === "PROCESSED"
                            ? "bg-emerald-100 text-emerald-800"
                            : item.status === "FAILED"
                            ? "bg-red-100 text-red-800"
                            : item.status === "OFFLINE"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-sky-100 text-sky-800"
                        }`}>
                          {item.status}
                        </span>
                      </div>
                      <span className="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full flex items-center gap-1">
                        <Clock className="w-3 h-3 text-amber-600" />
                        Expires in {hoursLeft}h {minsLeft}m
                      </span>
                    </div>

                    <div className="flex items-center justify-between mt-2">
                      <h4 className="font-bold text-slate-900 text-sm">
                        {item.patient_name || "Voice Recording"}
                        {item.uhid && (
                          <span className="font-mono text-xs text-slate-500 font-normal ml-1">
                            ({item.uhid})
                          </span>
                        )}
                      </h4>
                      <span className="text-[11px] text-slate-500 font-medium">
                        {new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} • {item.duration_seconds || 0}s ({Math.round(item.blob.size / 1024)} KB)
                      </span>
                    </div>

                    {item.department && (
                      <div className="text-xs text-slate-600 mt-0.5">
                        <span className="font-medium text-sky-800">Dept: {item.department}</span>
                      </div>
                    )}

                    {/* Audio Player */}
                    <div className="mt-2.5">
                      <AudioVaultPlayer blob={item.blob} />
                    </div>

                    {/* Transcript preview if processed */}
                    {item.original_transcript && (
                      <div className="mt-2 p-2 bg-slate-50 border border-slate-100 rounded-xl text-xs text-slate-600">
                        <span className="font-bold text-slate-700 block text-[10px] uppercase tracking-wide">Transcript:</span>
                        <p className="line-clamp-2 italic">"{item.original_transcript}"</p>
                      </div>
                    )}

                    {/* Error message if failed */}
                    {item.last_error && (
                      <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded-xl text-[11px] text-red-700">
                        <span className="font-bold block">Last Network / AI Error:</span>
                        {item.last_error}
                      </div>
                    )}

                    {/* Action Buttons */}
                    <div className="flex items-center justify-between gap-2 mt-3 pt-2.5 border-t border-slate-100">
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => handleRetryVaultItem(item)}
                          disabled={!isOnline}
                          className={`py-1.5 px-3 rounded-xl font-bold text-xs flex items-center gap-1 transition ${
                            isOnline
                              ? "bg-sky-600 text-white hover:bg-sky-700 shadow-xs"
                              : "bg-slate-100 text-slate-400 cursor-not-allowed"
                          }`}
                          title={isOnline ? "Send to AI for transcription" : "Requires internet"}
                        >
                          <Sparkles className="w-3.5 h-3.5" />
                          Retry AI
                        </button>
                        <button
                          onClick={() => handleUseVaultItemManual(item)}
                          className="py-1.5 px-3 bg-emerald-600 text-white hover:bg-emerald-700 font-bold text-xs rounded-xl shadow-xs transition flex items-center gap-1"
                        >
                          <FileText className="w-3.5 h-3.5" />
                          Use for Review
                        </button>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => handleDownloadVaultAudio(item)}
                          className="p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition"
                          title="Download Audio to Device"
                        >
                          <Download className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteVaultItem(item.id)}
                          className="p-1.5 text-red-500 hover:text-red-700 hover:bg-red-50 rounded-xl transition"
                          title="Delete from Vault"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Background Processing Queue Drawer / Slide-Over (Section 7) */}
      {showQueueDrawer && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex justify-end animate-fade-in">
          <div className="bg-white w-full max-w-md h-full shadow-2xl flex flex-col p-5 overflow-hidden">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2">
                <Layers className="w-5 h-5 text-sky-600" />
                <h3 className="font-extrabold text-slate-900 text-base">Background Queue</h3>
              </div>
              <button
                onClick={() => setShowQueueDrawer(false)}
                className="p-1 rounded-xl text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="grid grid-cols-3 gap-2 py-3 border-b text-center">
              <div className="bg-sky-50 p-2 rounded-xl border border-sky-200">
                <span className="text-[10px] font-bold text-sky-700 uppercase block">Processing</span>
                <span className="text-lg font-black text-sky-900">{queueStatus.processing_count}</span>
              </div>
              <div className="bg-emerald-50 p-2 rounded-xl border border-emerald-200">
                <span className="text-[10px] font-bold text-emerald-700 uppercase block">Completed</span>
                <span className="text-lg font-black text-emerald-900">{queueStatus.completed_count}</span>
              </div>
              <div className="bg-red-50 p-2 rounded-xl border border-red-200">
                <span className="text-[10px] font-bold text-red-700 uppercase block">Needs Review</span>
                <span className="text-lg font-black text-red-900">{queueStatus.needs_review_count}</span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto py-3 space-y-2.5">
              {queueStatus.items.length === 0 ? (
                <div className="text-center py-12 text-slate-400 text-xs">
                  No background jobs in recent history.
                </div>
              ) : (
                queueStatus.items.map((job) => (
                  <div
                    key={job.feedback_id}
                    className={`p-3 rounded-2xl border text-xs ${
                      job.status === "NEEDS_REVIEW"
                        ? "bg-red-50/60 border-red-200 text-red-900"
                        : job.status === "COMPLETED"
                        ? "bg-emerald-50/40 border-emerald-200 text-slate-800"
                        : "bg-sky-50/40 border-sky-200 text-slate-800"
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono">
                      <span className="font-bold">{job.feedback_id}</span>
                      <span className="text-[10px] text-slate-400">{job.time_str}</span>
                    </div>
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-slate-600 font-medium">UHID: {job.uhid_short}</span>
                      <span className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-md ${
                        job.status === "NEEDS_REVIEW"
                          ? "bg-red-200 text-red-800"
                          : job.status === "COMPLETED"
                          ? "bg-emerald-200 text-emerald-800"
                          : "bg-sky-200 text-sky-800 animate-pulse"
                      }`}>
                        {job.status}
                      </span>
                    </div>
                    {job.processing_error && (
                      <div className="mt-2 p-2 bg-red-100/70 border border-red-300 rounded-xl text-[11px] text-red-800">
                        <span className="font-bold block">Issue:</span>
                        {job.processing_error}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            <button
              onClick={() => {
                refreshQueueStatus();
              }}
              className="w-full py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-xs rounded-xl transition flex items-center justify-center gap-1.5"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Refresh Queue
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
