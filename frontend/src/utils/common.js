export function createClientId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
  }

  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 11)}`;
}

export function eventHasFiles(event) {
  return Array.from(event.dataTransfer?.types ?? []).includes("Files");
}

export function safeStorageGet(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function safeStorageSet(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage can be unavailable in private/restricted browser contexts.
  }
}

export function getBestAudioMimeType() {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") {
    return "";
  }

  return [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4;codecs=mp4a.40.2",
    "audio/mp4",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/aac",
    "audio/mpeg",
  ].find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

export function canUseMediaRecorder() {
  return Boolean(
    typeof navigator !== "undefined"
    && navigator.mediaDevices?.getUserMedia
    && typeof MediaRecorder !== "undefined",
  );
}

function preferredVoiceConstraints(overrides = {}) {
  return {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    channelCount: 1,
    ...overrides,
  };
}

export async function listAudioInputDevices() {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.enumerateDevices) {
    return [];
  }

  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.filter((device) => device.kind === "audioinput");
  } catch {
    return [];
  }
}

export async function getVoiceMediaStream() {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new Error("getUserMedia unavailable");
  }

  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: preferredVoiceConstraints(),
    });
  } catch (error) {
    const code = error?.name || "";
    if (!["NotFoundError", "DevicesNotFoundError", "OverconstrainedError"].includes(code)) {
      throw error;
    }

    const audioInputs = await listAudioInputDevices();
    const fallbackInput = audioInputs.find((device) => (
      device.deviceId
      && device.deviceId !== "default"
      && device.deviceId !== "communications"
    )) || audioInputs[0];

    if (!fallbackInput?.deviceId) {
      throw error;
    }

    return navigator.mediaDevices.getUserMedia({
      audio: preferredVoiceConstraints({
        deviceId: { exact: fallbackInput.deviceId },
      }),
    });
  }
}

export async function getMicrophoneErrorMessage(error) {
  if (typeof window !== "undefined" && !window.isSecureContext) {
    return "Microphone access needs localhost or HTTPS. Open the app from a secure URL and try again.";
  }

  const code = error?.name || "";

  if (code === "NotAllowedError" || code === "SecurityError") {
    return "Microphone permission is blocked for this browser.";
  }

  if (code === "NotReadableError" || code === "TrackStartError" || code === "AbortError") {
    return "The microphone is busy or unavailable right now. Close other apps using it and try again.";
  }

  if (code === "OverconstrainedError") {
    return "This browser could not open the selected microphone. Reload the page and try again.";
  }

  if (code === "NotFoundError" || code === "DevicesNotFoundError") {
    const audioInputs = await listAudioInputDevices();
    if (audioInputs.length > 0) {
      return "A microphone was detected, but the browser could not open it. Close other apps using the mic and try again.";
    }
    return "No microphone was found for this browser.";
  }

  return "Could not start the microphone.";
}

export function getVoiceUnsupportedMessage() {
  if (typeof window !== "undefined" && !window.isSecureContext) {
    return "Microphone access needs localhost or HTTPS. Open the app at http://localhost:5173 on this computer.";
  }
  return "Voice recording is not supported in this browser.";
}

export function formatVoiceTime(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

export function appendVoiceTranscript(currentPrompt, transcript) {
  const cleanTranscript = transcript.replace(/\s+/g, " ").trim();
  if (!cleanTranscript) return currentPrompt;
  const base = currentPrompt.trimEnd();
  return base ? `${base} ${cleanTranscript}` : cleanTranscript;
}

export function buildSelectionAwarePrompt(prompt, selectedText) {
  if (!selectedText) return prompt;
  const cleanPrompt = String(prompt || "").trim();
  const cleanSelection = String(selectedText || "").replace(/\s+/g, " ").trim();
  const normalizedPrompt = normalizeQuestion(cleanPrompt);
  const exactMeaningPrompts = [
    "mean",
    "means",
    "meaning",
    "define",
    "explain",
    "মানে",
  ];
  const meaningStarters = [
    "what mean",
    "what means",
    "what meaning",
    "what does it mean",
    "what does this mean",
    "what does that mean",
    "what does selected mean",
    "what is meaning",
    "what is the meaning",
    "এর মানে",
  ];
  const asksMeaning = (
    exactMeaningPrompts.includes(normalizedPrompt)
    || meaningStarters.some((phrase) => normalizedPrompt === phrase || normalizedPrompt.startsWith(`${phrase} `))
  );

  if (asksMeaning && cleanSelection) {
    return [
      "Use this selected text from the current conversation as the primary context for the user's question:",
      `"""${cleanSelection}"""`,
      "",
      `User question: What does "${cleanSelection}" mean in this DIU context? Explain it clearly and briefly.`,
      "Important: Answer about the selected text, not about the word 'mean' or 'means'.",
    ].join("\n");
  }

  return [
    "Use this selected text from the current conversation as the primary context for the user's question:",
    `"""${cleanSelection}"""`,
    "",
    `User question: ${cleanPrompt}`,
    "Important: Prioritize the selected text when resolving this question.",
  ].join("\n");
}

function normalizeHistoryText(value) {
  return String(value || "")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_#>|-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeQuestion(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^0-9a-z\u0980-\u09ff\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function hasFollowupPronoun(tokens) {
  const pronounTokens = new Set(["it", "this", "that", "them", "those", "these", "same", "related"]);
  return tokens.some((token) => pronounTokens.has(token));
}

function looksLikeSessionFollowup(prompt) {
  const normalized = normalizeQuestion(prompt);
  const tokens = normalized.split(" ").filter(Boolean);
  if (!normalized) return false;

  const vagueFollowups = [
    "more",
    "more detail",
    "more details",
    "more detailed",
    "details",
    "detail please",
    "explain more",
    "tell me more",
    "elaborate",
    "chart",
    "table",
    "summarize it",
    "summarise it",
  ];
  if (tokens.length <= 4 && vagueFollowups.some((phrase) => normalized.includes(phrase))) {
    return true;
  }

  if (tokens.length <= 2) {
    return hasFollowupPronoun(tokens);
  }
  if (tokens.length <= 5 && hasFollowupPronoun(tokens)) {
    return true;
  }

  const followupStarters = [
    "what about",
    "how about",
    "and",
    "also",
    "then",
    "that",
    "this",
    "it",
    "them",
    "those",
    "these",
    "same",
    "related",
    "for this",
    "for that",
    "in this",
    "in that",
    "আর",
    "তাহলে",
    "এটা",
    "ওটা",
  ];
  if (followupStarters.some((starter) => normalized.startsWith(starter))) {
    return true;
  }

  return tokens.length <= 10 && hasFollowupPronoun(tokens);
}

function latestSubstantiveUserTopic(history) {
  for (let index = history.length - 1; index >= 0; index -= 1) {
    const message = history[index];
    if (message.role !== "user" || !message.content) continue;
    if (!looksLikeSessionFollowup(message.content)) {
      return index;
    }
  }

  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (history[index].role === "user" && history[index].content) {
      return index;
    }
  }

  return -1;
}

export function buildSessionAwarePrompt(prompt, messages) {
  const cleanPrompt = String(prompt || "").trim();
  if (!cleanPrompt || !looksLikeSessionFollowup(cleanPrompt)) {
    return cleanPrompt;
  }

  const history = (Array.isArray(messages) ? messages : [])
    .map((message) => ({
      role: String(message?.role || "").trim().toLowerCase(),
      content: normalizeHistoryText(message?.content || ""),
    }))
    .filter((message) => ["user", "assistant"].includes(message.role) && message.content);

  if (!history.length) return cleanPrompt;

  const topicIndex = latestSubstantiveUserTopic(history);
  const scopedHistory = topicIndex >= 0 ? history.slice(topicIndex) : history;
  const sessionTopic = topicIndex >= 0 ? history[topicIndex].content : "";
  const recentContext = scopedHistory
    .map((message) => message.content)
    .filter((content) => normalizeQuestion(content) !== normalizeQuestion(cleanPrompt))
    .slice(-20)
    .join(" | ");

  const contextSource = sessionTopic || recentContext;
  if (!contextSource) return cleanPrompt;

  return [
    cleanPrompt,
    "",
    `Session topic: ${contextSource}`,
    `Relevant recent context: ${[recentContext].filter(Boolean).join(" | ")}`,
  ].join("\n");
}

export function buildAttachmentOnlyPrompt(files) {
  const names = files.map((file) => file.name).join(", ");
  return `Summarize and answer from the uploaded file${files.length === 1 ? "" : "s"}: ${names}`;
}

export function buildUserMessageContent(prompt, files, selectedText = "") {
  const selectedBlock = selectedText ? `> ${selectedText}` : "";

  if (!files.length) {
    return [selectedBlock, prompt].filter(Boolean).join("\n\n");
  }

  const fileLines = files.map((file) => `- ${file.name}`).join("\n");

  if (!prompt.trim()) {
    return [selectedBlock, `Uploaded file${files.length === 1 ? "" : "s"}:\n${fileLines}`]
      .filter(Boolean)
      .join("\n\n");
  }

  return [selectedBlock, `${prompt.trim()}\n\nUploaded file${files.length === 1 ? "" : "s"}:\n${fileLines}`]
    .filter(Boolean)
    .join("\n\n");
}

export function triggerHaptic(duration = 8) {
  if (typeof navigator !== "undefined" && navigator.vibrate) {
    navigator.vibrate(duration);
  }
}

export function fileExtensionForMime(mimeType = "") {
  const normalized = String(mimeType).toLowerCase();
  const knownExtensions = {
    "application/json": "json",
    "application/pdf": "pdf",
    "image/avif": "avif",
    "image/gif": "gif",
    "image/heic": "heic",
    "image/heif": "heif",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "text/markdown": "md",
    "text/plain": "txt",
  };
  if (knownExtensions[normalized]) return knownExtensions[normalized];
  const subtype = normalized.split("/")[1] || "";
  return subtype.replace(/[^a-z0-9]+/g, "") || "bin";
}

export function ensureNamedFile(file, index, sourceLabel) {
  if (!(file instanceof Blob)) return null;
  const fallbackName = `${sourceLabel}-${Date.now()}-${index + 1}.${fileExtensionForMime(file.type)}`;
  const nextName = file instanceof File && file.name?.trim() ? file.name.trim() : fallbackName;
  if (file instanceof File && file.name === nextName) return file;
  if (typeof File === "undefined") return file;
  return new File([file], nextName, {
    type: file.type || "",
    lastModified: file instanceof File ? file.lastModified : Date.now(),
  });
}

export function createUploadDescriptor(file, index, sourceLabel) {
  const normalizedFile = ensureNamedFile(file, index, sourceLabel);
  if (!normalizedFile) return null;

  return {
    id: `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 11)}`,
    name: normalizedFile.name,
    mimeType: normalizedFile.type || "",
    rawFile: normalizedFile,
    size: normalizedFile.size || 0,
    previewUrl: isImageFile({
      name: normalizedFile.name,
      mimeType: normalizedFile.type || "",
    }) && typeof URL !== "undefined"
      ? URL.createObjectURL(normalizedFile)
      : "",
  };
}

export function isImageFile(file) {
  const mimeType = String(file.mimeType || "");
  if (mimeType.startsWith("image/")) return true;
  return /\.(avif|gif|heic|heif|jpe?g|png|webp)$/i.test(file.name || "");
}

export function isAudioFile(file) {
  const mimeType = String(file.mimeType || "");
  if (mimeType.startsWith("audio/")) return true;
  return /\.(mp3|wav|m4a|aac|ogg|flac)$/i.test(file.name || "");
}

export function isVideoFile(file) {
  const mimeType = String(file.mimeType || "");
  if (mimeType.startsWith("video/")) return true;
  return /\.(mp4|mpeg|mov|avi|webm|wmv|mpg|flv)$/i.test(file.name || "");
}
