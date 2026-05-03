import { useCallback, useEffect, useRef, useState } from "react";
import {
  buildAssistantReply,
  buildSessionHistory,
  clearConversation,
  createCanvasWebsite,
  ensureConversation,
  getSessionId,
  listMessages,
  saveMessage,
  truncateMessagesAfter,
  uploadFilesToBackend,
} from "../services/assistantService";
import {
  ASSISTANT_MODE,
  ASSISTANT_MODES,
  MAX_DIRECT_UPLOAD_BYTES,
  VOICE_DRAFT_READY_STATUS,
} from "../../../utils/constants";
import {
  appendVoiceTranscript,
  buildAttachmentOnlyPrompt,
  buildSessionAwarePrompt,
  buildSelectionAwarePrompt,
  buildUserMessageContent,
  createClientId,
  createUploadDescriptor,
  safeStorageGet,
  safeStorageSet,
  triggerHaptic,
} from "../../../utils/common.js";
import {
  buildOpenCanvasState,
  loadOpenCanvasState,
  persistOpenCanvasState,
} from "../../../utils/openCanvas";
import { useCompactViewport } from "../../layout/hooks/useCompactViewport";
import { useVoiceRecorder } from "../../voice/hooks/useVoiceRecorder";

function mergeUploadedContexts(current, incoming) {
  const merged = Array.isArray(current) ? [...current] : [];
  for (const item of Array.isArray(incoming) ? incoming : []) {
    if (!item || typeof item !== "object") continue;
    const title = String(item.title || "").trim();
    const content = String(item.content || "").trim();
    if (!title || !content) continue;
    const index = merged.findIndex((existing) => String(existing?.title || "").trim() === title);
    if (index >= 0) merged[index] = { ...merged[index], ...item };
    else merged.push(item);
  }
  return merged;
}

export function useAssistant() {
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [sessionId, setSessionId] = useState(() => getSessionId());
  const [theme, setTheme] = useState(() => safeStorageGet("diu_theme") || "light");
  const [activeModeKey, setActiveModeKey] = useState(() => {
    const stored = safeStorageGet("diu_assistant_mode") || ASSISTANT_MODE;
    return (ASSISTANT_MODES.find(m => m.key === stored) || ASSISTANT_MODES[0]).key;
  });
  const [isModePickerOpen, setIsModePickerOpen] = useState(false);
  const [status, setStatus] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const [animatingMessageId, setAnimatingMessageId] = useState(null);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [uploadedContexts, setUploadedContexts] = useState([]);
  const [dropState, setDropState] = useState("idle");
  const [selectedContext, setSelectedContext] = useState(null);
  const [isCanvasPanelManualOpen, setIsCanvasPanelManualOpen] = useState(false);
  const isCompactViewport = useCompactViewport();
  const [isGeneratingArtifact, setIsGeneratingArtifact] = useState(false);
  const [openCanvasState, setOpenCanvasState] = useState(null);
  const [canvasPanelWidth, setCanvasPanelWidth] = useState(() => {
    const stored = Number.parseFloat(safeStorageGet("diu_canvas_panel_width") || "58");
    return Number.isFinite(stored) ? Math.min(72, Math.max(42, stored)) : 58;
  });
  const [editingMessageId, setEditingMessageId] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [busyStatus, setBusyStatus] = useState(null);

  const promptRef = useRef("");
  const textareaRef = useRef(null);
  const messagesRef = useRef(null);
  const chatLayoutRef = useRef(null);
  const isBusyRef = useRef(false);
  const isTranscribingRef = useRef(false);
  const voiceReadyStatusTimeoutRef = useRef(null);
  const bottomRef = useRef(null);

  const activeMode = ASSISTANT_MODES.find(m => m.key === activeModeKey) || ASSISTANT_MODES[0];

  const {
    isListening,
    isTranscribing,
    voiceElapsedSeconds,
    voiceLevel,
    handleVoiceInput,
    stopVoiceInput,
  } = useVoiceRecorder({
    isBusy,
    onTranscript: useCallback((transcript) => {
      const combinedPrompt = appendVoiceTranscript(promptRef.current, transcript);
      if (!combinedPrompt.trim()) {
        setStatus("");
        return;
      }

      setPrompt(combinedPrompt);
      if (voiceReadyStatusTimeoutRef.current) {
        window.clearTimeout(voiceReadyStatusTimeoutRef.current);
      }

      setStatus(VOICE_DRAFT_READY_STATUS);
      voiceReadyStatusTimeoutRef.current = window.setTimeout(() => {
        setStatus((current) => (current === VOICE_DRAFT_READY_STATUS ? "" : current));
        voiceReadyStatusTimeoutRef.current = null;
      }, 2200);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }, []),
    setStatus,
  });

  useEffect(() => {
    isTranscribingRef.current = isTranscribing;
  }, [isTranscribing]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    safeStorageSet("diu_theme", theme);
  }, [theme]);

  useEffect(() => {
    safeStorageSet("diu_canvas_panel_width", String(canvasPanelWidth));
  }, [canvasPanelWidth]);

  useEffect(() => {
    safeStorageSet("diu_assistant_mode", activeModeKey);
  }, [activeModeKey]);

  useEffect(() => {
    let isMounted = true;
    async function boot() {
      try {
        const id = await ensureConversation(sessionId);
        if (!isMounted) return;
        setConversationId(id);
        const saved = await listMessages(id);
        if (isMounted && saved.length) {
          setMessages(saved);
        }
      } catch (error) {
        setStatus(error.message);
      }
    }
    boot();
    return () => { isMounted = false; };
  }, [sessionId]);

  useEffect(() => {
    if (!conversationId) {
      setOpenCanvasState(null);
      return;
    }
    setOpenCanvasState((current) => {
      const baseState = current?.conversationId === conversationId ? current : loadOpenCanvasState(conversationId);
      const nextState = buildOpenCanvasState(baseState, messages, conversationId);
      persistOpenCanvasState(conversationId, nextState);
      return JSON.stringify(current ?? null) === JSON.stringify(nextState ?? null) ? current : nextState;
    });
  }, [conversationId, messages]);

  useEffect(() => {
    promptRef.current = prompt;
  }, [prompt]);

  useEffect(() => {
    isBusyRef.current = isBusy;
  }, [isBusy]);

  const addMessage = useCallback(async (message) => {
    const optimistic = { id: createClientId(), created_at: new Date().toISOString(), ...message };
    if (optimistic.role === "assistant") setAnimatingMessageId(optimistic.id);
    setMessages((current) => [...current, optimistic]);
    if (conversationId) {
      const saved = await saveMessage(conversationId, optimistic);
      return saved ?? optimistic;
    }
    return optimistic;
  }, [conversationId]);

  const submitComposer = useCallback(async ({
    promptOverride = null,
    allowWhileTranscribing = false,
    userMessageOverride = null,
    historyOverride = null,
    hideUserMessage = false,
  } = {}) => {
    triggerHaptic(10);
    const cleanPrompt = String(promptOverride ?? promptRef.current).trim();
    const directFiles = [...uploadedFiles];
    let assistantMessageId = null;
    let assistantMessage = null;

    if ((!cleanPrompt && !directFiles.length) || isBusyRef.current || (isTranscribingRef.current && !allowWhileTranscribing)) {
      return false;
    }

    stopVoiceInput();
    setPrompt("");
    setIsBusy(true);
    setBusyStatus(null);
    setStatus("");

    try {
      const queryPrompt = cleanPrompt || buildAttachmentOnlyPrompt(directFiles);
      const selectedText = selectedContext?.text || "";
      const sessionAwarePrompt = buildSessionAwarePrompt(queryPrompt, historyOverride ?? messages);
      const modelPrompt = buildSelectionAwarePrompt(sessionAwarePrompt, selectedText);
      const userContent = String(userMessageOverride || "").trim() || buildUserMessageContent(cleanPrompt, directFiles, selectedText);
      const sessionHistory = buildSessionHistory(historyOverride ?? messages);
      let rememberedContexts = uploadedContexts;

      if (directFiles.length) {
        try {
          const extractedContexts = await uploadFilesToBackend({
            sessionId,
            directFiles,
          });
          if (extractedContexts.length) {
            rememberedContexts = mergeUploadedContexts(uploadedContexts, extractedContexts);
            setUploadedContexts(rememberedContexts);
          }
        } catch (error) {
          console.error("Failed to remember uploaded document context:", error);
        }
      }

      await addMessage({
        role: "user",
        mode: activeMode.key,
        content: userContent,
        sources: [],
        ...(hideUserMessage ? { _hidden: true } : {}),
      });

      setUploadedFiles([]);
      setSelectedContext(null);
      window.getSelection?.()?.removeAllRanges();

      assistantMessageId = createClientId();
      assistantMessage = { id: assistantMessageId, role: "assistant", mode: activeMode.key, content: "", sources: [], created_at: new Date().toISOString(), _pending: true };
      setAnimatingMessageId(assistantMessageId);
      setMessages((current) => [...current, assistantMessage]);

      const reply = await buildAssistantReply({
        mode: activeMode.key,
        prompt: modelPrompt,
        sessionId,
        history: sessionHistory,
        directFiles,
        context: rememberedContexts,
        onChunk: (chunk) => {
          if (chunk && typeof chunk === "object") {
            if (chunk.status === "generating_artifact") setIsGeneratingArtifact(true);
            setBusyStatus(chunk);
            return;
          }
          setMessages((current) => current.map((msg) => {
            if (msg.id === assistantMessageId) return { ...msg, _pending: false, content: msg.content + String(chunk || "") };
            return msg;
          }));
        },
      });

      setIsGeneratingArtifact(false);
      setMessages((current) => current.map((msg) => {
        if (msg.id === assistantMessageId) return { ...msg, ...reply, _pending: false };
        return msg;
      }));
      setAnimatingMessageId((current) => (current === assistantMessageId ? null : current));

      if (conversationId) await saveMessage(conversationId, { ...assistantMessage, ...reply });
      return true;
    } catch (error) {
      const fallbackMessage = {
        role: "assistant",
        mode: activeMode.key,
        content: `The assistant hit a local error: ${error.message}`,
        sources: [],
      };
      setAnimatingMessageId((current) => (current === assistantMessageId ? null : current));
      if (assistantMessageId && assistantMessage) {
        const completedFallback = { ...assistantMessage, ...fallbackMessage, _pending: false };
        setMessages((current) => current.map((msg) => (
          msg.id === assistantMessageId ? completedFallback : msg
        )));
        if (conversationId) await saveMessage(conversationId, completedFallback);
      } else {
        await addMessage(fallbackMessage);
      }
      return false;
    } finally {
      setIsBusy(false);
      setBusyStatus(null);
    }
  }, [activeMode, addMessage, conversationId, messages, sessionId, stopVoiceInput, uploadedContexts, uploadedFiles, selectedContext]);

  const createCanvasFromContent = useCallback(async (content) => {
    const sourceContent = String(content || "").trim();
    if (!sourceContent || isBusyRef.current) return false;

    triggerHaptic(10);
    stopVoiceInput();
    setIsCanvasPanelManualOpen(true);
    setIsGeneratingArtifact(true);
    isBusyRef.current = true;
    setIsBusy(true);
    setBusyStatus({ status: "generating_artifact" });
    setStatus("");

    const assistantMessageId = createClientId();
    const pendingMessage = {
      id: assistantMessageId,
      role: "assistant",
      mode: activeMode.key,
      content: "",
      sources: [],
      artifacts: [],
      created_at: new Date().toISOString(),
      _pending: true,
    };
    setAnimatingMessageId(assistantMessageId);
    setMessages((current) => [...current, pendingMessage]);

    try {
      const reply = await createCanvasWebsite({
        sourceContent,
        mode: activeMode.key,
        sessionId,
      });
      setMessages((current) => current.map((msg) => (
        msg.id === assistantMessageId ? { ...msg, ...reply, _pending: false } : msg
      )));
      setAnimatingMessageId((current) => (current === assistantMessageId ? null : current));
      if (conversationId) await saveMessage(conversationId, { ...pendingMessage, ...reply });
      return true;
    } catch (error) {
      const fallback = {
        content: `The website canvas could not be generated: ${error.message}`,
        sources: [],
        artifacts: [],
        metadata: {},
      };
      setMessages((current) => current.map((msg) => (
        msg.id === assistantMessageId ? { ...msg, ...fallback, _pending: false } : msg
      )));
      setAnimatingMessageId((current) => (current === assistantMessageId ? null : current));
      if (conversationId) await saveMessage(conversationId, { ...pendingMessage, ...fallback });
      return false;
    } finally {
      isBusyRef.current = false;
      setIsBusy(false);
      setIsGeneratingArtifact(false);
      setBusyStatus(null);
    }
  }, [activeMode.key, conversationId, sessionId, stopVoiceInput]);

  const handleUpload = useCallback(async (fileList, sourceLabel = "upload") => {
    const files = Array.from(fileList ?? []).filter(Boolean);
    if (!files.length || isTranscribing) {
      setDropState("idle");
      return;
    }

    const eligible = files.filter((file) => file.size <= MAX_DIRECT_UPLOAD_BYTES);
    if (!eligible.length) {
      setDropState("idle");
      setStatus(`File too large. Limit is ${Math.round(MAX_DIRECT_UPLOAD_BYTES / (1024 * 1024))} MB.`);
      return;
    }

    const attached = eligible.map((file, index) => createUploadDescriptor(file, index, sourceLabel)).filter(Boolean);
    setUploadedFiles((current) => {
      const existingKeys = new Set(current.map((file) => `${file.name}:${file.size}:${file.mimeType}`));
      const dedupedIncoming = attached.filter((file) => !existingKeys.has(`${file.name}:${file.size}:${file.mimeType}`));
      return [...dedupedIncoming, ...current].slice(0, 12);
    });
    setDropState("success");
    setStatus(`${eligible.length} file(s) attached.`);
    window.setTimeout(() => setDropState("idle"), 600);
  }, [isTranscribing]);

  const resetWorkspaceSession = useCallback(() => {
    stopVoiceInput();
    setMessages([]);
    setUploadedFiles([]);
    setUploadedContexts([]);
    setSelectedContext(null);
    setStatus("");
    setAnimatingMessageId(null);
    setOpenCanvasState(null);
    setIsCanvasPanelManualOpen(false);
    const fresh = createClientId();
    safeStorageSet("diu-assistant-session-v2", fresh);
    setSessionId(fresh);
  }, [stopVoiceInput]);

  const handleRetry = useCallback(async (messageId) => {
    if (isBusy) return;
    const index = messages.findIndex((m) => m.id === messageId);
    if (index === -1) return;
    for (let i = index - 1; i >= 0; i--) {
      if (messages[i].role === "user") {
        const userPrompt = messages[i].content;
        triggerHaptic(10);
        const truncatedMessages = messages.slice(0, i);
        setMessages(() => truncatedMessages);
        if (conversationId) {
          if (i === 0) void clearConversation(conversationId);
          else void truncateMessagesAfter(conversationId, messages[i - 1].id);
        }
        void submitComposer({ promptOverride: userPrompt, historyOverride: truncatedMessages });
        return;
      }
    }
  }, [conversationId, isBusy, messages, submitComposer]);

  const handleSaveEdit = useCallback(async (messageId) => {
    if (isBusy) return;
    const index = messages.findIndex((m) => m.id === messageId);
    if (index === -1) return;
    const newContent = editValue.trim();
    if (!newContent) return;
    triggerHaptic(10);
    const truncatedMessages = messages.slice(0, index);
    setMessages(() => truncatedMessages);
    setEditingMessageId(null);
    setEditValue("");
    if (conversationId) {
      if (index === 0) void clearConversation(conversationId);
      else void truncateMessagesAfter(conversationId, messages[index - 1].id);
    }
    void submitComposer({ promptOverride: newContent, historyOverride: truncatedMessages });
  }, [conversationId, editValue, isBusy, messages, submitComposer]);


  return {
    prompt, setPrompt,
    messages, setMessages,
    theme, setTheme,
    activeModeKey, setActiveModeKey,
    isModePickerOpen, setIsModePickerOpen,
    status, setStatus,
    isBusy, setIsBusy,
    animatingMessageId, setAnimatingMessageId,
    uploadedFiles, setUploadedFiles,
    dropState, setDropState,
    selectedContext, setSelectedContext,
    isCanvasPanelManualOpen, setIsCanvasPanelManualOpen,
    isCompactViewport,
    isGeneratingArtifact, setIsGeneratingArtifact,
    openCanvasState, setOpenCanvasState,
    canvasPanelWidth, setCanvasPanelWidth,
    editingMessageId, setEditingMessageId,
    editValue, setEditValue,
    activeMode,
    isListening, isTranscribing, voiceElapsedSeconds, voiceLevel,
    handleVoiceInput, stopVoiceInput,
    submitComposer, createCanvasFromContent, handleUpload, resetWorkspaceSession, handleRetry, handleSaveEdit,
    textareaRef, messagesRef, chatLayoutRef, bottomRef,
    conversationId, sessionId,
    busyStatus,
  };
}
