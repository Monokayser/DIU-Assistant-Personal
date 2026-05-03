import React from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";

export function ArtifactHeader({
  title,
  currentIndex,
  totalVersions,
  onPrevious,
  onNext,
  onClose,
}) {
  return (
    <header className="oc-artifact-header">
      <div className="oc-artifact-title-block">
        <h2>{title}</h2>
      </div>

      <div className="oc-artifact-controls" aria-label="Artifact controls">
        {totalVersions > 1 && (
          <>
            <button
              type="button"
              className="oc-icon-button"
              onClick={onPrevious}
              disabled={currentIndex <= 1}
              aria-label="Previous artifact version"
              title="Previous version"
            >
              <ChevronLeft size={18} />
            </button>
            <span className="oc-history-count">v{currentIndex} / {totalVersions}</span>
            <button
              type="button"
              className="oc-icon-button"
              onClick={onNext}
              disabled={currentIndex >= totalVersions}
              aria-label="Next artifact version"
              title="Next version"
            >
              <ChevronRight size={18} />
            </button>
          </>
        )}

        <button
          type="button"
          className="oc-icon-button canvas-close-button"
          onClick={onClose}
          aria-label="Close canvas"
          title="Close canvas"
        >
          <X size={20} />
        </button>
      </div>
    </header>
  );
}
