import React from "react";
import { Copy, Pencil, RotateCcw, Sparkles } from "lucide-react";
import { motion } from "framer-motion";
import { 
  AnswerStatus, 
  MarkdownMessage, 
  TypewriterMarkdown 
} from "./MessageContent";
import { SourceChips } from "./SourceChips";
import { ASSISTANT_MODE } from "../../../utils/constants";
import { 
  extractHtmlFromContent, 
  extractTitleFromContent 
} from "../../../utils/artifactUtils";

export function MessageItem({
  message,
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
  idx = 0,
}) {
  const isAnimatingAssistant = message.role === "assistant" && message.id === animatingMessageId;
  const renderedContent = getRenderableAssistantContent(message);

  return (
    <article className={`message ${message.role}`}>
      {message.role === "assistant" && (
        <AnswerStatus
          metadata={message.metadata}
          sources={message.sources}
          triggerHaptic={triggerHaptic}
        />
      )}
      <div className="bubble">
        {editingMessageId === message.id ? (
          <div className="edit-message-container">
            <textarea
              className="edit-message-textarea"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSaveEdit(message.id);
                } else if (e.key === "Escape") {
                  handleCancelEdit();
                }
              }}
            />
            <div className="edit-message-actions">
              <button type="button" className="edit-save-btn" onClick={() => handleSaveEdit(message.id)}>
                Save & Submit
              </button>
              <button type="button" className="edit-cancel-btn" onClick={handleCancelEdit}>
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <MarkdownMessage 
            content={renderedContent} 
            isStreaming={isAnimatingAssistant}
          />
        )}
      </div>

      {!isAnimatingAssistant && editingMessageId !== message.id && (
        <div className="message-actions">
          {message.role === "user" ? (
            <button
              type="button"
              className="message-action-btn"
              onClick={() => handleEditMessage(message)}
              title="Edit message"
            >
              <Pencil size={14} />
            </button>
          ) : (
            <button
              type="button"
              className="message-action-btn"
              onClick={() => handleRetry(message.id)}
              title="Regenerate response"
            >
              <RotateCcw size={14} />
            </button>
          )}
          <button
            type="button"
            className="message-action-btn"
            onClick={() => handleCopyMessage(renderedContent)}
            title="Copy to clipboard"
          >
            <Copy size={14} />
          </button>
          {message.role === "assistant" && activeMode.key !== ASSISTANT_MODE && (
            <button
              type="button"
              className="message-action-btn"
              onClick={() => handleCreateCanvas(renderedContent)}
              title="Create Canvas"
            >
              <Sparkles size={14} />
            </button>
          )}
        </div>
      )}
      {message.role === "assistant" && <SourceChips sources={message.sources} />}
      
    </article>
  );
}
