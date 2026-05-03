import React, { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import Lenis from "lenis";
import { ThinkingStatus } from "./MessageContent";
import { MessageItem } from "./MessageItem";

export function MessageList({
  messages,
  isBusy,
  busyStatus,
  welcomeContent,
  handleWelcomeSuggestion,
  messagesRef,
  bottomRef,
  animatingMessageId,
  getRenderableAssistantContent,
  editingMessageId,
  editValue,
  setEditValue,
  handleSaveEdit,
  handleCancelEdit,
  handleEditMessage,
  handleRetry,
  handleCopyMessage,
  handleCreateCanvas,
  scrollToBottomState,
  setAnimatingMessageId,
  isCompactViewport,
  isGeneratingArtifact,
  activeMode,
  triggerHaptic,
}) {
  const isRenderableAssistantMessage = (message) => {
    if (message?.role !== "assistant") return true;
    if (!message?._pending) return true;
    if (String(message?.content || "").trim()) return true;
    if (Array.isArray(message?.artifacts) && message.artifacts.length > 0) return true;
    return false;
  };

  const lenisRef = useRef(null);
  const lastMessagesLength = useRef(messages.length);
  const autoFollowRef = useRef(true);

  useEffect(() => {
    if (!messagesRef.current) return undefined;

    const wrapper = messagesRef.current;

    const lenis = new Lenis({
      wrapper,
      content: wrapper.firstElementChild,
      duration: 1.2,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      wheelMultiplier: 1.1,
      lerp: 0.08,
      autoResize: true,
    });
    lenisRef.current = lenis;

    const isNearBottom = () => {
      const { scrollHeight, scrollTop, clientHeight } = wrapper;
      return scrollHeight - scrollTop - clientHeight < 150;
    };

    const updateAutoFollow = () => {
      autoFollowRef.current = isNearBottom();
    };

    updateAutoFollow();
    wrapper.addEventListener("scroll", updateAutoFollow, { passive: true });

    const resizeObserver = new ResizeObserver(() => {
      lenis.resize();
    });
    if (messagesRef.current) resizeObserver.observe(messagesRef.current);

    let rafId;
    function raf(time) {
      lenis.raf(time);
      rafId = requestAnimationFrame(raf);
    }
    rafId = requestAnimationFrame(raf);

    return () => {
      wrapper.removeEventListener("scroll", updateAutoFollow);
      resizeObserver.disconnect();
      cancelAnimationFrame(rafId);
      lenis.destroy();
      lenisRef.current = null;
    };
  }, [messagesRef]);

  // Auto-scroll logic during streaming
  useEffect(() => {
    if (!lenisRef.current || !messagesRef.current) return;

    const isStreaming = messages.some(m => m.id === animatingMessageId);
    const messageCountIncreased = messages.length > lastMessagesLength.current;

    if ((isStreaming || messageCountIncreased) && autoFollowRef.current) {
      lenisRef.current.resize();
      lenisRef.current.scrollTo(bottomRef.current || "bottom", { duration: 0.12, lerp: 0.18 });
    }

    lastMessagesLength.current = messages.length;
  }, [messages, animatingMessageId, bottomRef]);

  return (
    <div className="messages" ref={messagesRef}>
      <div className="messages-content-wrapper">
        {!messages.length && !isBusy && (
          <section className="welcome-page" aria-label="Welcome">
            <div className="welcome-copy">
              <h2>{welcomeContent.title}</h2>
              <p>{welcomeContent.subtitle}</p>
            </div>

            <div className="welcome-suggestions" aria-label="Follow-up suggestions">
              {welcomeContent.suggestions.map((suggestion, idx) => (
                <button
                  type="button"
                  className="welcome-suggestion"
                  key={suggestion.label}
                  onClick={() => handleWelcomeSuggestion(suggestion)}
                >
                  {suggestion.label}
                </button>
              ))}
            </div>
          </section>
        )}

        {messages.filter((m) => !m._hidden).filter(isRenderableAssistantMessage).map((message, idx) => (
          <MessageItem
            key={message.id}
            message={message}
            idx={idx}
            animatingMessageId={animatingMessageId}
            getRenderableAssistantContent={getRenderableAssistantContent}
            editingMessageId={editingMessageId}
            editValue={editValue}
            setEditValue={setEditValue}
            handleSaveEdit={handleSaveEdit}
            handleCancelEdit={handleCancelEdit}
            handleEditMessage={handleEditMessage}
            handleRetry={handleRetry}
            handleCopyMessage={handleCopyMessage}
            handleCreateCanvas={handleCreateCanvas}
            scrollToBottomState={scrollToBottomState}
            setAnimatingMessageId={setAnimatingMessageId}
            isCompactViewport={isCompactViewport}
            isGeneratingArtifact={isGeneratingArtifact}
            activeMode={activeMode}
            triggerHaptic={triggerHaptic}
          />
        ))}

        {isBusy && (
          <article className="message assistant typing-message">
            <ThinkingStatus status={busyStatus} />
          </article>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
