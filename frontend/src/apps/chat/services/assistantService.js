import { isSupabaseConfigured, supabase } from "../../../utils/supabaseClient.js";
import { createClientId, safeStorageGet, safeStorageSet } from "../../../utils/common.js";
import { resolveApiBase } from "../../../utils/apiConfig.js";
import { normalizeArtifacts } from "../../../utils/artifactUtils.js";
import { normalizeSources } from "../../../utils/sourceUtils.js";

const DEMO_SESSION_KEY = "diu-assistant-session-v2";
const LOCAL_CONVERSATION_PREFIX = "local:";
const LOCAL_MESSAGE_PREFIX = "diu-local-messages:";
const API_BASE = resolveApiBase(import.meta.env?.VITE_API_URL);
const MAX_SESSION_HISTORY_MESSAGES = 100;
const STREAM_TIMEOUT_MS = 180000;
const CANVAS_TIMEOUT_MS = 300000;

export function getSessionId() {
  const existing = safeStorageGet(DEMO_SESSION_KEY);
  if (existing) return existing;
  const fresh = createClientId();
  safeStorageSet(DEMO_SESSION_KEY, fresh);
  return fresh;
}

function localConversationId(sessionId) {
  return `${LOCAL_CONVERSATION_PREFIX}${sessionId}`;
}

function isLocalConversationId(conversationId) {
  return String(conversationId || "").startsWith(LOCAL_CONVERSATION_PREFIX);
}

function localMessageKey(conversationId) {
  return `${LOCAL_MESSAGE_PREFIX}${conversationId}`;
}

function loadLocalMessages(conversationId) {
  const raw = safeStorageGet(localMessageKey(conversationId));
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveLocalMessages(conversationId, messages) {
  safeStorageSet(localMessageKey(conversationId), JSON.stringify(messages));
}

export async function ensureConversation(sessionId) {
  if (!isSupabaseConfigured) return localConversationId(sessionId);

  try {
    const { data: existing, error: findError } = await supabase
      .from("conversations")
      .select("id")
      .eq("session_id", sessionId)
      .maybeSingle();

    if (findError) throw findError;
    if (existing?.id) return existing.id;

    const { data, error } = await supabase
      .from("conversations")
      .insert({ session_id: sessionId, title: "DIU Assistant" })
      .select("id")
      .single();

    if (error) throw error;
    return data.id;
  } catch {
    return localConversationId(sessionId);
  }
}

export async function listMessages(conversationId) {
  if (!conversationId) return [];
  if (!isSupabaseConfigured || isLocalConversationId(conversationId)) {
    return loadLocalMessages(conversationId);
  }

  try {
    const { data, error } = await supabase
      .from("messages")
      .select("id,role,mode,content,sources,created_at")
      .eq("conversation_id", conversationId)
      .order("created_at", { ascending: true });

    if (error) throw error;
    return data ?? [];
  } catch {
    return [];
  }
}

export async function saveMessage(conversationId, message) {
  if (!conversationId) return null;
  if (!isSupabaseConfigured || isLocalConversationId(conversationId)) {
    const next = [...loadLocalMessages(conversationId), message];
    saveLocalMessages(conversationId, next);
    return message;
  }

  try {
    const { data, error } = await supabase
      .from("messages")
      .insert({
        conversation_id: conversationId,
        role: message.role,
        mode: message.mode,
        content: message.content,
        sources: message.sources ?? [],
      })
      .select("id,role,mode,content,sources,created_at")
      .single();

    if (error) throw error;
    return data;
  } catch {
    const fallbackConversationId = localConversationId(getSessionId());
    const next = [...loadLocalMessages(fallbackConversationId), message];
    saveLocalMessages(fallbackConversationId, next);
    return message;
  }
}

export async function truncateMessagesAfter(conversationId, messageId) {
  if (!conversationId || !messageId) return;

  if (!isSupabaseConfigured || isLocalConversationId(conversationId)) {
    const messages = loadLocalMessages(conversationId);
    const index = messages.findIndex((m) => m.id === messageId);
    if (index !== -1) {
      const truncated = messages.slice(0, index + 1);
      saveLocalMessages(conversationId, truncated);
    }
    return;
  }

  try {
    // Get the timestamp of the message to delete everything after it
    const { data: targetMsg } = await supabase
      .from("messages")
      .select("created_at")
      .eq("id", messageId)
      .single();

    if (targetMsg?.created_at) {
      await supabase
        .from("messages")
        .delete()
        .eq("conversation_id", conversationId)
        .gt("created_at", targetMsg.created_at);
    }
  } catch (error) {
    console.error("Failed to truncate messages:", error);
  }
}

export async function clearConversation(conversationId) {
  if (!conversationId) return;

  if (!isSupabaseConfigured || isLocalConversationId(conversationId)) {
    saveLocalMessages(conversationId, []);
    return;
  }

  try {
    await supabase.from("messages").delete().eq("conversation_id", conversationId);
  } catch (error) {
    console.error("Failed to clear conversation:", error);
  }
}


export async function answerWithBackendStreaming({
  prompt,
  mode,
  sessionId,
  history = [],
  directFiles = [],
  context = [],
  onChunk,
}) {
  const effectiveHistory = mode === "assistant" ? [] : history;
  const directUploadFiles = directFiles
    .map(originalFileForUpload)
    .filter(Boolean)
    .slice(0, 8);
  const directPayloadFiles = directUploadFiles.length
    ? await Promise.all(directUploadFiles.map(fileToPayload))
    : [];
  const requestBody = {
    message: prompt,
    mode,
    allow_local_grounding: true,
    session_id: sessionId,
    history: effectiveHistory,
    attached_files: directUploadFiles.map((file) => file.name).filter(Boolean),
    direct_files: directPayloadFiles,
    context,
    stream: true,
  };
  const nonStreamingRequestBody = {
    ...requestBody,
    stream: false,
  };

  function finishPayload(payload) {
    const sources = normalizeSources(payload.sources);
    const artifacts = normalizeArtifacts(payload.artifacts, API_BASE);
    return {
      content: payload.answer,
      sources,
      artifacts,
      metadata: buildResponseMetadata(payload, {
        sourceCount: Math.min(sources.length, 3),
      }),
    };
  }

  function looksTruncatedAnswer(answer) {
    const text = String(answer || "").replace(/\s+/g, " ").trim();
    if (text.length < 50) return false;
    if (/([.!?]|<\/\w+>|```)\s*["')\]]*\s*$/i.test(text)) return false;
    if (/[,:;\/\-(]$/.test(text)) return true;
    const lastWord = text.match(/([A-Za-z]+)\s*$/)?.[1]?.toLowerCase() || "";
    return [
      "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
      "in", "into", "is", "of", "on", "or", "the", "to", "under", "with",
      "if", "that", "this", "these", "those",
    ].includes(lastWord);
  }

  async function requestStreamOnce() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), STREAM_TIMEOUT_MS);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(requestBody),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!response.ok) {
        const text = await response.text();
        throw new Error(cleanBackendText(text) || "The assistant backend could not answer right now.");
      }

      if (!response.body) {
        throw new Error("The assistant backend returned an empty response stream.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finalPayload = null;
      let sawStreamActivity = false;

      function handlePayload(payload) {
        if (!payload || typeof payload !== "object") return null;
        sawStreamActivity = true;
        if (payload.error) {
          const error = new Error(payload.error);
          error.noJsonRetry = true;
          throw error;
        }
        if (payload.chunk) {
          onChunk(payload.chunk);
          return null;
        }
        if (payload.status) {
          onChunk(payload);
          return null;
        }
        if (payload.done || typeof payload.answer === "string") {
          if (looksTruncatedAnswer(payload.answer)) {
            throw new Error("The assistant stream ended before the final sentence completed.");
          }
          finalPayload = payload;
          return finishPayload(payload);
        }
        return null;
      }

      function parseStreamLine(line) {
        const trimmed = String(line || "").trim();
        if (!trimmed) return null;
        const jsonText = trimmed.startsWith("data:")
          ? trimmed.slice(5).trim()
          : trimmed;
        if (!jsonText || jsonText === "[DONE]") return null;
        return JSON.parse(jsonText);
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          let payload = null;
          try {
            payload = parseStreamLine(line);
          } catch (e) {
            console.error("Failed to parse stream line:", line, e);
            continue;
          }
          if (!payload) continue;
          const result = handlePayload(payload);
          if (result) return result;
        }
      }

      if (buffer.trim()) {
        let payload = null;
        try {
          payload = parseStreamLine(buffer);
        } catch (e) {
          console.error("Failed to parse final stream payload:", buffer, e);
        }
        if (payload) {
          const result = handlePayload(payload);
          if (result) return result;
        }
      }

      if (finalPayload) {
        return finishPayload(finalPayload);
      }

      if (sawStreamActivity) {
        throw new Error("The assistant stream ended before the final answer arrived.");
      }

      throw new Error("The assistant backend returned no answer.");
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async function requestJsonOnce() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), STREAM_TIMEOUT_MS);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(nonStreamingRequestBody),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      const data = await response.json().catch(() => ({}));
      if (!response.ok || data?.error) {
        throw new Error(cleanBackendText(data?.error) || "The assistant backend could not answer right now.");
      }

      if (typeof data?.answer !== "string" || !data.answer.trim()) {
        throw new Error("The assistant backend returned no answer.");
      }
      if (looksTruncatedAnswer(data.answer)) {
        throw new Error("The assistant answer ended early. Please retry.");
      }

      return finishPayload(data);
    } finally {
      clearTimeout(timeoutId);
    }
  }

  let lastError = null;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      if (attempt === 0) {
        return await requestStreamOnce();
      }
      return await requestJsonOnce();
    } catch (error) {
      lastError = error;
      console.error(`Streaming attempt ${attempt + 1} failed:`, error);
      if (error?.noJsonRetry) break;
      if (attempt === 0) {
        await new Promise((resolve) => setTimeout(resolve, 600));
        continue;
      }
    }
  }

  return {
    content: lastError?.message || "The assistant backend could not answer right now.",
    sources: [],
    artifacts: [],
    metadata: buildClientMetadata({
      provider: "browser",
      foundMatch: false,
    }),
    shouldFallback: true,
  };
}

export async function createCanvasWebsite({
  sourceContent,
  mode,
  sessionId,
  title = "",
}) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), CANVAS_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE}/api/canvas`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        artifact_type: "website",
        source_content: sourceContent,
        sourceContent,
        session_id: sessionId,
        sessionId,
        mode,
        title,
        allow_local_grounding: true,
      }),
      signal: controller.signal,
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok || data?.error) {
      throw new Error(cleanBackendText(data?.error || data?.answer) || "The website canvas could not be generated.");
    }

    const sources = normalizeSources(data.sources);
    const artifacts = normalizeArtifacts(data.artifacts, API_BASE);
    if (!artifacts.length) {
      throw new Error("The website canvas did not include a valid HTML artifact.");
    }

    return {
      content: data.answer || "Here is your website canvas. Open the canvas to explore it.",
      sources,
      artifacts,
      metadata: buildResponseMetadata(data, {
        sourceCount: Math.min(sources.length, 3),
      }),
    };
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function transcribeVoiceInput({ audioBlob, language }) {
  if (!audioBlob?.size) {
    return "";
  }

  const response = await fetch(`${API_BASE}/api/transcribe`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      audio_base64: await blobToBase64(audioBlob),
      mime_type: audioBlob.type || "audio/webm",
      language,
    }),
  });

  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || "Voice transcription failed.");
  }

  const transcript = String(data.transcript || "").trim();
  if (!transcript) return "";
  return transcript;
}

export async function buildAssistantReply({
  mode,
  prompt,
  sessionId,
  history = [],
  directFiles = [],
  context = [],
  onChunk = () => {},
}) {
  const backendReply = await answerWithBackendStreaming({
    prompt,
    mode,
    sessionId,
    history,
    directFiles,
    context,
    onChunk,
  });
  if (backendReply && !backendReply.shouldFallback) return backendReply;

  return await buildBackendUnavailableReply({
    directFiles,
    backendMessage: backendReply?.content || "",
  });
}

export async function uploadFilesToBackend({
  sessionId,
  directFiles = [],
}) {
  const directUploadFiles = directFiles
    .map(originalFileForUpload)
    .filter(Boolean)
    .slice(0, 8);
  if (!directUploadFiles.length) return [];

  const files = await Promise.all(directUploadFiles.map(fileToPayload));
  const response = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: sessionId,
      return_text: true,
      files,
    }),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.error) {
    const message = cleanBackendText(data.error || (Array.isArray(data.errors) ? data.errors.join(" ") : ""));
    throw new Error(message || "Uploaded files could not be prepared for follow-up answers.");
  }

  return (Array.isArray(data.files) ? data.files : [])
    .map((item) => {
      const content = String(item?.text || "").trim();
      const title = String(item?.filename || "").trim();
      if (!content || !title) return null;
      return {
        title,
        source: title,
        content,
      };
    })
    .filter(Boolean);
}

function normalizeHistoryMessage(message) {
  if (!message || typeof message !== "object") return null;
  const role = String(message.role || "").trim().toLowerCase();
  if (!["user", "assistant"].includes(role)) return null;
  const content = String(message.content || "").trim();
  if (!content) return null;
  const mode = String(message.mode || "").trim();
  return {
    role,
    mode,
    content,
  };
}

export function buildSessionHistory(messages) {
  const normalized = (Array.isArray(messages) ? messages : [])
    .map(normalizeHistoryMessage)
    .filter(Boolean);

  if (!normalized.length) return [];

  const firstUserIndex = normalized.findIndex((message) => message.role === "user");
  const tailStartIndex = Math.max(0, normalized.length - MAX_SESSION_HISTORY_MESSAGES);
  const history = [];

  if (firstUserIndex >= 0 && firstUserIndex < tailStartIndex) {
    history.push(normalized[firstUserIndex]);
  }

  history.push(...normalized.slice(tailStartIndex));
  return history;
}

function buildClientMetadata(overrides = {}) {
  return {
    provider: "browser",
    model: null,
    models: [],
    usedModel: false,
    foundMatch: false,
    elapsedMs: null,
    sourceCount: 0,
    usedDocuments: false,
    retryAfterSeconds: null,
    ...overrides,
  };
}

function buildResponseMetadata(data, overrides = {}) {
  const retryAfterSeconds = parseRetryAfterSeconds(
    typeof data?.answer === "string" ? data.answer : typeof data?.error === "string" ? data.error : "",
  );
  return buildClientMetadata({
    provider: data?.provider ?? "gemini",
    model: data?.model ?? null,
    models: Array.isArray(data?.models) ? data.models : [],
    usedModel: Boolean(data?.used_model),
    foundMatch: Boolean(data?.found_match),
    elapsedMs: Number.isFinite(data?.elapsed_ms) ? data.elapsed_ms : null,
    sourceCount: Math.min(Array.isArray(data?.sources) ? data.sources.length : 0, 3),
    usedDocuments: Boolean(data?.used_documents),
    retryAfterSeconds,
    ...overrides,
  });
}

function cleanBackendText(text) {
  const value = String(text || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return value.slice(0, 240);
}

async function fileToPayload(file) {
  return {
    filename: file.name,
    mime_type: file.type || "",
    content_base64: await blobToBase64(file),
  };
}

function originalFileForUpload(upload) {
  const file = upload?.rawFile || upload?.file || upload;
  return file && typeof file.arrayBuffer === "function" ? file : null;
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || "");
      resolve(value.includes(",") ? value.split(",").pop() : value);
    };
    const label = typeof File !== "undefined" && blob instanceof File ? blob.name : "the recorded audio";
    reader.onerror = () => reject(reader.error || new Error(`Could not read ${label}.`));
    reader.readAsDataURL(blob);
  });
}

function buildDirectFileFallbackReply(files) {
  const names = files.map((file) => file.name).filter(Boolean);
  const listed = names.length ? names.join(", ") : "the uploaded file";
  const containsImage = files.some((file) => /\.(avif|gif|heic|heif|jpe?g|png|webp)$/i.test(file.name || ""));

  return {
    content: containsImage
      ? `I received ${listed}, but this browser-only build does not include on-device image understanding yet. Live image analysis will work once the DIU file-analysis backend is reachable.`
      : `I received ${listed}, but this browser-only build cannot analyze uploaded files without the live DIU file-analysis service.`,
    sources: [],
    artifacts: [],
    metadata: buildClientMetadata({
      provider: "browser",
    }),
  };
}

async function buildBackendUnavailableReply({
  directFiles = [],
  backendMessage = "",
} = {}) {
  if (backendMessage && backendMessage.length > 10) {
    return {
      content: backendMessage,
      sources: [],
      artifacts: [],
      metadata: buildClientMetadata({
        provider: "browser",
        retryAfterSeconds: parseRetryAfterSeconds(backendMessage),
      }),
    };
  }

  if (directFiles.length) {
    return buildDirectFileFallbackReply(directFiles);
  }

  return {
    content: backendMessage
      || "The live DIU Assistant is unavailable right now. Please try again when the backend is reachable.",
    sources: [],
    artifacts: [],
    metadata: buildClientMetadata({
      provider: "browser",
      retryAfterSeconds: parseRetryAfterSeconds(backendMessage),
    }),
  };
}

function parseRetryAfterSeconds(message) {
  const match = String(message || "").match(/try again in about\s+(\d+)\s+seconds?/i);
  if (!match) return null;
  const seconds = Number.parseInt(match[1], 10);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : null;
}
