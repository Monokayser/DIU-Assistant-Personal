import React from "react";
import { Check, Upload } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

export function AppShell({
  children,
  dropState,
  showCanvasPanel,
  isCompactViewport,
  canvasPanelWidth,
}) {
  return (
    <main className={`app-shell state-${dropState}`}>
      <AnimatePresence>
        {dropState !== "idle" && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className={`drop-overlay state-${dropState}`} 
            aria-hidden="true"
          >
            <div className="drop-content">
              <div className="drop-icon">
                {dropState === "dragging" ? (
                  <Upload size={52} strokeWidth={1.5} />
                ) : (
                  <Check size={52} strokeWidth={1.5} />
                )}
              </div>
              <span className="drop-text">
                {dropState === "dragging" ? "Drop files to upload" : "Ready"}
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <section
        className={`workspace${showCanvasPanel && !isCompactViewport ? " has-split-layout" : ""}`}
        style={showCanvasPanel && !isCompactViewport ? {
          "--chat-panel-width": `${100 - canvasPanelWidth}%`,
          "--canvas-panel-width": `${canvasPanelWidth}%`,
        } : undefined}
      >
        {children}
      </section>
    </main>
  );
}
