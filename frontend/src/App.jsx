import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useAssistant } from "./apps/chat/hooks/useAssistant";
import { AppShell } from "./apps/layout/components/AppShell";
import { TopBar } from "./apps/layout/components/TopBar";
import { MessageList } from "./apps/chat/components/MessageList";
import { Composer } from "./apps/chat/components/Composer";
import { ModePicker } from "./apps/chat/components/ModePicker";
import { CanvasGuidePopup } from "./apps/canvas/components/CanvasGuidePopup";
import { ArtifactRenderer } from "./apps/canvas/components/ArtifactRenderer";
import {
  triggerHaptic,
  eventHasFiles,
} from "./utils/common.js";
import { persistOpenCanvasState } from "./utils/openCanvas";
import {
  cleanArtifactMessageContent,
  buildMobileCanvasHref,
} from "./utils/artifactUtils";
import { buildWelcomeContent } from "./utils/uiConfig";
import { ASSISTANT_MODE } from "./utils/constants";

function getRenderableAssistantContent(message) {
  if (message?.role !== "assistant") return String(message?.content || "");
  const hasWorkspaceArtifact = Array.isArray(message.artifacts) && message.artifacts.some((artifact) => (
    artifact?.kind === "workspace" || artifact?.mimeType === "text/html"
  ));
  if (!hasWorkspaceArtifact) return String(message?.content || "");
  const cleaned = cleanArtifactMessageContent(message.content);
  return cleaned || "Here is your workspace. Open the canvas to explore it.";
}

function App() {
  const assistant = useAssistant();
  const {
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
  } = assistant;

  const hasConversationStarted = messages.length > 0;
  const showCanvasPanel = activeMode.key !== ASSISTANT_MODE && isCanvasPanelManualOpen && hasConversationStarted;
  const welcomeContentByMode = useMemo(() => ({
    assistant: buildWelcomeContent("assistant"),
    admission: buildWelcomeContent("admission"),
    course: buildWelcomeContent("course"),
    scholarship: buildWelcomeContent("scholarship"),
  }), []);
  const welcomeContent = welcomeContentByMode[activeMode.key] ?? welcomeContentByMode.assistant;
  const mobileCanvasHref = useMemo(() => {
    if (!openCanvasState?.artifact?.contents?.length) return null;
    return buildMobileCanvasHref(openCanvasState.artifact.contents[openCanvasState.artifact.currentIndex - 1]);
  }, [openCanvasState]);

  const scrollToBottomState = useCallback((smooth = true) => {
    bottomRef.current?.scrollIntoView(smooth ? { behavior: "smooth", block: "end" } : { block: "end" });
  }, [bottomRef]);

  // Global Drag & Drop handlers
  useEffect(() => {
    const onDragEnter = (e) => { if (eventHasFiles(e)) { e.preventDefault(); setDropState("dragging"); } };
    const onDragOver = (e) => { if (eventHasFiles(e)) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; } };
    const onDragLeave = (e) => { if (eventHasFiles(e)) { e.preventDefault(); setDropState("idle"); } };
    const onDrop = (e) => { if (eventHasFiles(e)) { e.preventDefault(); handleUpload(e.dataTransfer.files, "drop"); } };
    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("drop", onDrop);
    };
  }, [handleUpload, setDropState]);

  // Global Context Selection
  useEffect(() => {
    const captureSelection = () => {
      const selection = window.getSelection?.();
      const selectedText = selection?.toString().replace(/\s+/g, " ").trim();
      if (!selectedText || selectedText.length < 2 || !messagesRef.current?.contains(selection.anchorNode)) return;
      setSelectedContext({ text: selectedText });
    };
    const clearSelection = (e) => { if (!e.target.closest?.(".composer")) { if (!window.getSelection?.()?.toString().trim()) setSelectedContext(null); } };
    document.addEventListener("mouseup", captureSelection);
    document.addEventListener("keyup", captureSelection);
    document.addEventListener("mousedown", clearSelection);
    return () => {
      document.removeEventListener("mouseup", captureSelection);
      document.removeEventListener("keyup", captureSelection);
      document.removeEventListener("mousedown", clearSelection);
    };
  }, [messagesRef, setSelectedContext]);

  const handleCanvasAction = useCallback(() => {
    triggerHaptic(10);
    setIsCanvasPanelManualOpen(v => !v);
    if (isCanvasPanelManualOpen) {
      setIsAnimatingCanvas(true);
    }
  }, [setIsCanvasPanelManualOpen, isCanvasPanelManualOpen]);

  const [isAnimatingCanvas, setIsAnimatingCanvas] = useState(false);
  const effectiveSplit = showCanvasPanel || isAnimatingCanvas;

  return (
    <>
      <CanvasGuidePopup activeModeKey={activeModeKey} messagesCount={messages.length} />

      <AppShell
        dropState={dropState}
        showCanvasPanel={effectiveSplit}
        isCompactViewport={isCompactViewport}
        canvasPanelWidth={canvasPanelWidth}
      >
        <TopBar
          activeMode={activeMode}
          theme={theme}
          toggleTheme={() => setTheme(t => t === "light" ? "dark" : "light")}
          isModePickerOpen={isModePickerOpen}
          setIsModePickerOpen={setIsModePickerOpen}
          isCanvasPanelManualOpen={isCanvasPanelManualOpen}
          handleCanvasAction={handleCanvasAction}
          handleNewChat={() => { triggerHaptic(15); resetWorkspaceSession(); }}
          handleBrandRefresh={(e) => { e?.preventDefault(); triggerHaptic(15); resetWorkspaceSession(); }}
          hasConversationStarted={hasConversationStarted}
          isCompactViewport={isCompactViewport}
          mobileCanvasHref={mobileCanvasHref}
          triggerHaptic={triggerHaptic}
        />

        <section className="chat-panel" aria-live="polite">
          <div
            ref={chatLayoutRef}
            className={`chat-layout${effectiveSplit ? " split" : ""}${isCompactViewport ? " compact-canvas" : ""}`}
          >
            <MessageList
              messages={messages}
              isBusy={isBusy}
              busyStatus={busyStatus}
              welcomeContent={welcomeContent}
              handleWelcomeSuggestion={(s) => { triggerHaptic(15); setPrompt(s.prompt); requestAnimationFrame(() => textareaRef.current?.focus()); }}
              messagesRef={messagesRef}
              bottomRef={bottomRef}
              animatingMessageId={animatingMessageId}
              getRenderableAssistantContent={getRenderableAssistantContent}
              editingMessageId={editingMessageId}
              editValue={editValue}
              setEditValue={setEditValue}
              handleSaveEdit={handleSaveEdit}
              handleCancelEdit={() => { setEditingMessageId(null); setEditValue(""); }}
              handleEditMessage={(m) => { setEditingMessageId(m.id); setEditValue(m.content); }}
              handleRetry={handleRetry}
              handleCopyMessage={(c) => { navigator.clipboard.writeText(c); triggerHaptic(5); setStatus("Copied"); setTimeout(() => setStatus(""), 2000); }}
              handleCreateCanvas={createCanvasFromContent}
              scrollToBottomState={scrollToBottomState}
              setAnimatingMessageId={setAnimatingMessageId}
              isCompactViewport={isCompactViewport}
              isGeneratingArtifact={isGeneratingArtifact}
              activeMode={activeMode}
              triggerHaptic={triggerHaptic}
            />

            <AnimatePresence 
              onExitComplete={() => setIsAnimatingCanvas(false)}
            >
              {showCanvasPanel && (
                <>
                  <div
                    className="canvas-resize-handle"
                    onMouseDown={(e) => {
                      const bounds = chatLayoutRef.current.getBoundingClientRect();
                      const onMove = (me) => setCanvasPanelWidth(Math.min(72, Math.max(42, ((bounds.width - (me.clientX - bounds.left)) / bounds.width) * 100)));
                      const onUp = () => { window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
                      e.preventDefault();
                      window.addEventListener("mousemove", onMove);
                      window.addEventListener("mouseup", onUp);
                    }}
                  />
                  <motion.aside
                    onAnimationStart={() => setIsAnimatingCanvas(true)}
                    initial={isCompactViewport ? { y: "100%" } : { x: "100%" }}
                    animate={isCompactViewport ? { y: 0 } : { x: 0 }}
                    exit={isCompactViewport ? { y: "100%" } : { x: "100%" }}
                    transition={{ type: "tween", duration: 0.15, ease: "easeOut" }}
                    className="canvas-panel-shell"
                    aria-label="Canvas workspace"
                  >
                    <ArtifactRenderer
                      canvasState={openCanvasState}
                      isGenerating={isGeneratingArtifact}
                      onCanvasStateChange={(s) => { setOpenCanvasState(s); if (conversationId) persistOpenCanvasState(conversationId, s); }}
                      onClose={handleCanvasAction}
                    />
                  </motion.aside>
                </>
              )}
            </AnimatePresence>
          </div>
        </section>

        <Composer
          prompt={prompt}
          setPrompt={setPrompt}
          handleSubmit={(e) => { e.preventDefault(); submitComposer(); }}
          handleUpload={(e) => { handleUpload(e.target.files, "picker"); e.target.value = ""; }}
          handleComposerKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.repeat) { e.preventDefault(); submitComposer(); } }}
          handleComposerPaste={(e) => { const files = e.clipboardData?.files; if (files?.length) { e.preventDefault(); handleUpload(files, "clipboard"); } }}
          handleInputFocus={() => { if (isCompactViewport) setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }), 300); }}
          handleVoiceInput={handleVoiceInput}
          isListening={isListening}
          isBusy={isBusy}
          isTranscribing={isTranscribing}
          voiceElapsedSeconds={voiceElapsedSeconds}
          voiceLevel={voiceLevel}
          status={status}
          uploadedFiles={uploadedFiles}
          removeUploadedFile={(id) => setUploadedFiles(current => current.filter(f => f.id !== id))}
          selectedContext={selectedContext}
          setSelectedContext={setSelectedContext}
          textareaRef={textareaRef}
          activeMode={activeMode}
          isCompactViewport={isCompactViewport}
          hasReadyUploads={uploadedFiles.length > 0}
          triggerHaptic={triggerHaptic}
        />
      </AppShell>

      <ModePicker
        isOpen={isModePickerOpen}
        onClose={() => setIsModePickerOpen(false)}
        activeMode={activeMode}
        onModeSelect={(k) => { triggerHaptic(10); resetWorkspaceSession(); setActiveModeKey(k); setIsModePickerOpen(false); }}
      />
    </>
  );
}

export default App;
