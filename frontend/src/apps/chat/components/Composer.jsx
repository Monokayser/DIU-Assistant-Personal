import React from "react";
import { CornerUpLeft, FileText, Image as ImageIcon, Music, Video, Mic, Send, Upload, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  SUPPORTED_UPLOAD_ACCEPT, 
  VOICE_BAR_HEIGHTS, 
  VOICE_DRAFT_READY_STATUS, 
  VOICE_TRANSCRIBING_STATUS 
} from "../../../utils/constants";
import { isImageFile, isAudioFile, isVideoFile, formatVoiceTime } from "../../../utils/common";

export function Composer({
  prompt,
  setPrompt,
  handleSubmit,
  handleUpload,
  handleComposerKeyDown,
  handleComposerPaste,
  handleInputFocus,
  handleVoiceInput,
  isListening,
  isBusy,
  isTranscribing,
  voiceElapsedSeconds,
  voiceLevel,
  status,
  uploadedFiles,
  removeUploadedFile,
  selectedContext,
  setSelectedContext,
  textareaRef,
  activeMode,
  isCompactViewport,
  hasReadyUploads,
  triggerHaptic,
}) {
  return (
    <section className="prompt-dock stagger-3">
      <form 
        className={`composer${status === "transcription-success" ? " transcription-success" : ""}`} 
        onSubmit={handleSubmit}
      >
        <label className="upload-button" title="Upload or paste files">
          <Upload size={18} />
          <input
            type="file"
            accept={SUPPORTED_UPLOAD_ACCEPT}
            multiple
            onChange={handleUpload}
          />
        </label>

        <div className="composer-input-area">
          {selectedContext && (
            <div className="selected-context-row">
              <CornerUpLeft className="selected-context-icon" size={17} aria-hidden="true" />
              <span className="selected-context-quotes">"</span>
              <span className="selected-context-text">{selectedContext.text}</span>
              <span className="selected-context-quotes">"</span>
              <button
                type="button"
                className="selected-context-clear"
                onClick={() => {
                  setSelectedContext(null);
                  window.getSelection?.()?.removeAllRanges();
                }}
                aria-label="Remove selected text context"
                title="Remove selected text"
              >
                <X size={17} />
              </button>
            </div>
          )}

          <AnimatePresence>
            {uploadedFiles.length > 0 && (
              <div className="uploaded-files-inline" aria-label="Uploaded files">
                {uploadedFiles.map((file) => (
                  <motion.span
                    initial={{ opacity: 0, scale: 0.8, x: -10 }}
                    animate={{ opacity: 1, scale: 1, x: 0 }}
                    exit={{ opacity: 0, scale: 0.8, x: -5 }}
                    transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                    className="uploaded-file-chip state-ready"
                    key={file.id}
                    title={file.name}
                  >
                    {file.previewUrl ? (
                      <img className="uploaded-file-preview" src={file.previewUrl} alt="" aria-hidden="true" />
                    ) : isImageFile(file) ? (
                      <ImageIcon size={13} />
                    ) : isAudioFile(file) ? (
                      <Music size={13} />
                    ) : isVideoFile(file) ? (
                      <Video size={13} />
                    ) : (
                      <FileText size={13} />
                    )}
                    <span>{file.name}</span>
                    <button
                      type="button"
                      className="remove-uploaded-file"
                      onClick={() => {
                        triggerHaptic(5);
                        removeUploadedFile(file.id);
                      }}
                      aria-label={`Remove ${file.name}`}
                    >
                      <X size={12} />
                    </button>
                  </motion.span>
                ))}
              </div>
            )}
          </AnimatePresence>

          <textarea
            ref={textareaRef}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            onPaste={handleComposerPaste}
            onFocus={handleInputFocus}
            placeholder={
              isCompactViewport
                ? "Message..."
                : activeMode.placeholder
            }
            rows={1}
          />
        </div>

        <button
          className={isListening ? "mic-button listening" : "mic-button"}
          type="button"
          onClick={handleVoiceInput}
          disabled={isBusy || isTranscribing}
          aria-label={isListening ? "Stop voice input" : "Start voice input"}
          aria-pressed={isListening}
          title={isListening ? "Stop voice input" : isTranscribing ? "Transcribing voice" : "Start voice input"}
        >
          <Mic size={18} />
        </button>

        <button
          className="send-button"
          type="submit"
          disabled={(!prompt.trim() && !hasReadyUploads) || isBusy || isTranscribing}
          aria-label="Send"
        >
          <Send size={18} />
        </button>
      </form>

      {isListening && (
        <div className="voice-monitor" aria-label="Voice recording level">
          <span className="voice-timer">{formatVoiceTime(voiceElapsedSeconds)}</span>
          <div className="voice-bars" style={{ "--voice-level": voiceLevel }} aria-hidden="true">
            {VOICE_BAR_HEIGHTS.map((height, index) => (
              <span
                key={`${height}-${index}`}
                style={{ "--bar-height": `${height}px` }}
              />
            ))}
          </div>
          <span className="voice-hint">tap the mic again to finish</span>
        </div>
      )}

      {status && (
        <p
          className={
            status === VOICE_TRANSCRIBING_STATUS
              ? "composer-status transcribing"
              : status === VOICE_DRAFT_READY_STATUS
                ? "composer-status ready"
                : "composer-status"
          }
          aria-live="polite"
        >
          {status}
        </p>
      )}
    </section>
  );
}
