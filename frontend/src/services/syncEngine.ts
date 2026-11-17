import { processAudio, submitAsyncFeedback, submitFeedback } from "./api";
import {
  getOfflineQueueItems,
  removeOfflineItem,
  updateOfflineItemStatus,
} from "./db";

let isSyncing = false;
const MAX_RETRY_ATTEMPTS = 5;

export function initSyncEngine(onSyncUpdate?: (count: number) => void) {
  const runSync = async () => {
    if (!navigator.onLine || isSyncing) return;

    try {
      isSyncing = true;
      const items = await getOfflineQueueItems();
      const pendingItems = items.filter(
        (it) => (it.status === "READY" || it.status === "FAILED") && (it.retry_count || 0) < MAX_RETRY_ATTEMPTS
      );

      if (pendingItems.length === 0) {
        if (onSyncUpdate) onSyncUpdate(items.length);
        return;
      }

      for (const item of pendingItems) {
        // Controlled exponential backoff delay based on retry_count (Section 14)
        if (item.retry_count > 0) {
          const backoffDelay = Math.min(1000 * Math.pow(2, item.retry_count - 1), 10000);
          console.log(`[SyncEngine] Applying exponential backoff delay of ${backoffDelay}ms for item ${item.client_uuid}`);
          await new Promise((res) => setTimeout(res, backoffDelay));
        }

        try {
          await updateOfflineItemStatus(item.client_uuid, "SYNCING");

          let payload = { ...item.payload };

          // If item has audio_blob, push directly to backend async endpoint so server processes in background
          if (item.audio_blob) {
            const formData = new FormData();
            formData.append("client_uuid", item.client_uuid);
            formData.append("uhid", payload.uhid);
            formData.append("patient_name", payload.patient_name);
            formData.append("department", payload.department);
            if (payload.location) formData.append("location", payload.location);
            if (payload.consultant) formData.append("consultant", payload.consultant);
            if (payload.scheme) formData.append("scheme", payload.scheme);
            if (payload.attendant_name) formData.append("attendant_name", payload.attendant_name);
            if (payload.complaint) formData.append("manual_complaint", payload.complaint);
            formData.append("audio", item.audio_blob, `${item.client_uuid}.webm`);

            await submitAsyncFeedback(formData);
          } else if (payload.complaint && payload.complaint.trim()) {
            // Manual complaint without audio - can be submitted via async or regular submission
            const formData = new FormData();
            formData.append("client_uuid", item.client_uuid);
            formData.append("uhid", payload.uhid);
            formData.append("patient_name", payload.patient_name);
            formData.append("department", payload.department);
            if (payload.location) formData.append("location", payload.location);
            if (payload.consultant) formData.append("consultant", payload.consultant);
            if (payload.scheme) formData.append("scheme", payload.scheme);
            if (payload.attendant_name) formData.append("attendant_name", payload.attendant_name);
            formData.append("manual_complaint", payload.complaint);

            await submitAsyncFeedback(formData);
          } else {
            // Fallback for pre-structured items
            await submitFeedback(payload);
          }

          // Mark completed & clean up
          await removeOfflineItem(item.client_uuid);
          window.dispatchEvent(
            new CustomEvent("sync:success", { detail: item.client_uuid })
          );
        } catch (itemErr: any) {
          console.error(`Sync failed for item ${item.client_uuid}:`, itemErr);
          await updateOfflineItemStatus(
            item.client_uuid,
            "FAILED",
            itemErr?.message || "Sync network error"
          );
        }
      }

      const remaining = await getOfflineQueueItems();
      if (onSyncUpdate) onSyncUpdate(remaining.length);
    } catch (err) {
      console.error("Sync loop error:", err);
    } finally {
      isSyncing = false;
    }
  };

  window.addEventListener("online", () => {
    console.log("[SyncEngine] Internet connection restored. Triggering auto-sync...");
    runSync();
  });

  // Check queue immediately
  runSync();

  return { triggerSync: runSync };
}
