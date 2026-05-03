import React from "react";
import { X, FileText } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { ASSISTANT_MODES } from "../../../utils/constants";
import { MODE_ICONS } from "../../../utils/uiConfig";

export function ModePicker({
  isOpen,
  onClose,
  activeMode,
  onModeSelect,
}) {
  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="agents-modal-overlay active"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              onClose();
            }
          }}
        >
          <motion.section
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.98 }}
            className="agents-modal-content active"
            role="dialog"
            aria-modal="true"
            aria-label="Choose assistant mode"
          >
            <div className="agents-modal-header">
              <h3>Select a Mode</h3>
              <button
                type="button"
                className="close-modal"
                onClick={onClose}
                aria-label="Close mode picker"
                title="Close"
              >
                <X size={18} />
              </button>
            </div>

            <div className="agents-grid">
              {ASSISTANT_MODES.map((mode) => {
                const ModeIcon = MODE_ICONS[mode.key] ?? FileText;
                const isActive = mode.key === activeMode.key;

                return (
                  <motion.button
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    type="button"
                    key={mode.key}
                    className={`agent-card${isActive ? " active" : ""}`}
                    onClick={() => onModeSelect(mode.key)}
                    aria-pressed={isActive}
                  >
                    <span className="agent-card-icon" aria-hidden="true">
                      <ModeIcon size={22} />
                    </span>
                    <span className="agent-card-info">
                      <strong>{mode.label}</strong>
                      <span>{mode.description}</span>
                    </span>
                    {isActive && <span className="active-badge">Active</span>}
                  </motion.button>
                );
              })}
            </div>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
