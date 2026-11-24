import { AudioVaultItem, OfflineFeedbackItem, SessionDraft } from "../types";

const DB_NAME = "HospitalFeedbackDB";
const DB_VERSION = 2;

let dbPromise: Promise<IDBDatabase> | null = null;

// ============================================================================
// LIGHTWEIGHT LOCAL AES-GCM CRYPTO LAYER (SECTION 13)
// ============================================================================

const LOCAL_KEY_STORAGE = "hf_local_device_key_v1";

async function getOrCreateDeviceKey(): Promise<CryptoKey> {
  const existingKeyJwk = localStorage.getItem(LOCAL_KEY_STORAGE);
  if (existingKeyJwk) {
    try {
      const jwk = JSON.parse(existingKeyJwk);
      return await crypto.subtle.importKey(
        "jwk",
        jwk,
        { name: "AES-GCM", length: 256 },
        true,
        ["encrypt", "decrypt"]
      );
    } catch (_) {}
  }

  // Generate new 256-bit AES-GCM key bound to this device browser
  const newKey = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    true,
    ["encrypt", "decrypt"]
  );
  const exported = await crypto.subtle.exportKey("jwk", newKey);
  localStorage.setItem(LOCAL_KEY_STORAGE, JSON.stringify(exported));
  return newKey;
}

async function encryptData(plainText: string): Promise<{ cipherHex: string; ivHex: string }> {
  try {
    const key = await getOrCreateDeviceKey();
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const encoded = new TextEncoder().encode(plainText);

    const cipherBuffer = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      key,
      encoded
    );

    const cipherHex = Array.from(new Uint8Array(cipherBuffer))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
    const ivHex = Array.from(iv)
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");

    return { cipherHex, ivHex };
  } catch (err) {
    // Fallback to base64 if subtle is blocked
    return { cipherHex: btoa(unescape(encodeURIComponent(plainText))), ivHex: "plain" };
  }
}

async function decryptData(cipherHex: string, ivHex: string): Promise<string> {
  try {
    if (ivHex === "plain") {
      return decodeURIComponent(escape(atob(cipherHex)));
    }
    const key = await getOrCreateDeviceKey();
    const iv = new Uint8Array(ivHex.match(/.{1,2}/g)!.map((byte) => parseInt(byte, 16)));
    const cipherBytes = new Uint8Array(cipherHex.match(/.{1,2}/g)!.map((byte) => parseInt(byte, 16)));

    const decryptedBuffer = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv },
      key,
      cipherBytes
    );
    return new TextDecoder().decode(decryptedBuffer);
  } catch (err) {
    console.warn("Local decryption fallback warning:", err);
    return "";
  }
}

function getDB(): Promise<IDBDatabase> {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (e) => {
        const db = req.result;
        if (!db.objectStoreNames.contains("drafts")) {
          db.createObjectStore("drafts", { keyPath: "session_id" });
        }
        if (!db.objectStoreNames.contains("offline_queue")) {
          db.createObjectStore("offline_queue", { keyPath: "client_uuid" });
        }
        if (!db.objectStoreNames.contains("audio_blobs")) {
          db.createObjectStore("audio_blobs", { keyPath: "uuid" });
        }
        if (!db.objectStoreNames.contains("audio_vault")) {
          db.createObjectStore("audio_vault", { keyPath: "id" });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  return dbPromise;
}

// ============================================================================
// DRAFT SESSION (FOR SESSION RECOVERY - SECTION 59)
// ============================================================================

export async function saveDraftSession(draft: SessionDraft): Promise<void> {
  const db = await getDB();
  const encryptedPayload = await encryptData(JSON.stringify(draft.form_data));

  return new Promise((resolve, reject) => {
    const tx = db.transaction("drafts", "readwrite");
    const store = tx.objectStore("drafts");
    store.put({
      session_id: draft.session_id,
      started_at: draft.started_at,
      step: draft.step,
      duration_seconds: draft.duration_seconds,
      enc_form: encryptedPayload,
    });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getLatestDraftSession(): Promise<SessionDraft | null> {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("drafts", "readonly");
    const store = tx.objectStore("drafts");
    const req = store.getAll();
    req.onsuccess = async () => {
      const items = req.result as any[];
      if (items && items.length > 0) {
        const latest = items[items.length - 1];
        let form_data = {};
        if (latest.enc_form) {
          try {
            const dec = await decryptData(latest.enc_form.cipherHex, latest.enc_form.ivHex);
            form_data = JSON.parse(dec);
          } catch (_) {}
        }
        resolve({
          session_id: latest.session_id,
          started_at: latest.started_at,
          step: latest.step,
          duration_seconds: latest.duration_seconds,
          form_data: form_data as any,
        });
      } else {
        resolve(null);
      }
    };
    req.onerror = () => reject(req.error);
  });
}

export async function clearDraftSession(sessionId?: string): Promise<void> {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("drafts", "readwrite");
    const store = tx.objectStore("drafts");
    if (sessionId) {
      store.delete(sessionId);
    } else {
      store.clear();
    }
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// ============================================================================
// OFFLINE SYNC QUEUE WITH LOCAL ENCRYPTION (SECTION 13 & 42)
// ============================================================================

export async function enqueueOfflineFeedback(item: OfflineFeedbackItem): Promise<void> {
  const db = await getDB();

  // If there's an audio blob, store in audio_blobs store
  if (item.audio_blob) {
    const audioTx = db.transaction("audio_blobs", "readwrite");
    audioTx.objectStore("audio_blobs").put({
      uuid: item.client_uuid,
      blob: item.audio_blob,
      created_at: new Date().toISOString(),
    });
  }

  // Encrypt payload before saving to disk
  const encryptedPayload = await encryptData(JSON.stringify(item.payload));

  return new Promise((resolve, reject) => {
    const tx = db.transaction("offline_queue", "readwrite");
    const store = tx.objectStore("offline_queue");
    store.put({
      client_uuid: item.client_uuid,
      created_at: item.created_at,
      status: item.status,
      retry_count: item.retry_count || 0,
      last_error: item.last_error,
      enc_payload: encryptedPayload,
    });
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getOfflineQueueItems(): Promise<OfflineFeedbackItem[]> {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(["offline_queue", "audio_blobs"], "readonly");
    const queueStore = tx.objectStore("offline_queue");
    const audioStore = tx.objectStore("audio_blobs");

    const req = queueStore.getAll();
    req.onsuccess = async () => {
      const records = req.result as any[];
      const enriched: OfflineFeedbackItem[] = [];

      for (const rec of records) {
        let payload: any = {};
        if (rec.enc_payload) {
          try {
            const dec = await decryptData(rec.enc_payload.cipherHex, rec.enc_payload.ivHex);
            payload = JSON.parse(dec);
          } catch (_) {}
        } else if (rec.payload) {
          payload = rec.payload;
        }

        const item: OfflineFeedbackItem = {
          client_uuid: rec.client_uuid,
          created_at: rec.created_at,
          status: rec.status,
          retry_count: rec.retry_count || 0,
          last_error: rec.last_error,
          payload,
        };

        // Attach audio blob if present
        const blobReq = audioStore.get(rec.client_uuid);
        await new Promise<void>((r) => {
          blobReq.onsuccess = () => {
            if (blobReq.result && blobReq.result.blob) {
              item.audio_blob = blobReq.result.blob;
            }
            r();
          };
          blobReq.onerror = () => r();
        });

        enriched.push(item);
      }
      resolve(enriched);
    };
    req.onerror = () => reject(req.error);
  });
}

export async function updateOfflineItemStatus(
  clientUuid: string,
  status: OfflineFeedbackItem["status"],
  errorMsg?: string
): Promise<void> {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("offline_queue", "readwrite");
    const store = tx.objectStore("offline_queue");
    const req = store.get(clientUuid);
    req.onsuccess = () => {
      const item = req.result;
      if (item) {
        item.status = status;
        if (status === "FAILED") {
          item.retry_count = (item.retry_count || 0) + 1;
          item.last_error = errorMsg;
        }
        store.put(item);
      }
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function removeOfflineItem(clientUuid: string): Promise<void> {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(["offline_queue", "audio_blobs"], "readwrite");
    tx.objectStore("offline_queue").delete(clientUuid);
    tx.objectStore("audio_blobs").delete(clientUuid);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// ============================================================================
// 12-HOUR AUDIO VAULT (OFFLINE RECORDING SAFEGUARD & AUTO-PURGE)
// ============================================================================

const TWELVE_HOURS_MS = 12 * 60 * 60 * 1000;

export async function saveToAudioVault(item: AudioVaultItem): Promise<void> {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("audio_vault", "readwrite");
    const store = tx.objectStore("audio_vault");
    store.put(item);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function updateAudioVaultStatus(
  id: string,
  status: AudioVaultItem["status"],
  updates?: Partial<AudioVaultItem>
): Promise<void> {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("audio_vault", "readwrite");
    const store = tx.objectStore("audio_vault");
    const req = store.get(id);
    req.onsuccess = () => {
      const item = req.result as AudioVaultItem;
      if (item) {
        item.status = status;
        if (updates) {
          Object.assign(item, updates);
        }
        store.put(item);
      }
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getAudioVaultItems(): Promise<AudioVaultItem[]> {
  const db = await getDB();
  // Auto-purge any items older than 12 hours first
  await purgeExpiredAudioVault();

  return new Promise((resolve, reject) => {
    const tx = db.transaction("audio_vault", "readonly");
    const store = tx.objectStore("audio_vault");
    const req = store.getAll();
    req.onsuccess = () => {
      const items = (req.result as AudioVaultItem[]) || [];
      // Sort newest first
      items.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      resolve(items);
    };
    req.onerror = () => reject(req.error);
  });
}

export async function deleteFromAudioVault(id: string): Promise<void> {
  const db = await getDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("audio_vault", "readwrite");
    const store = tx.objectStore("audio_vault");
    store.delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function purgeExpiredAudioVault(): Promise<number> {
  try {
    const db = await getDB();
    const now = Date.now();
    return new Promise((resolve) => {
      const tx = db.transaction("audio_vault", "readwrite");
      const store = tx.objectStore("audio_vault");
      const req = store.getAll();
      let purgedCount = 0;

      req.onsuccess = () => {
        const items = (req.result as AudioVaultItem[]) || [];
        for (const item of items) {
          const itemTime = new Date(item.created_at).getTime();
          if (now - itemTime > TWELVE_HOURS_MS) {
            store.delete(item.id);
            purgedCount++;
          }
        }
      };

      tx.oncomplete = () => resolve(purgedCount);
      tx.onerror = () => resolve(0);
    });
  } catch (_) {
    return 0;
  }
}
