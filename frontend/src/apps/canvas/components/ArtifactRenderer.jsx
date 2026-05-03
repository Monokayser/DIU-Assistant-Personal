import React, { useMemo } from "react";
import { ArtifactHeader } from "./ArtifactHeader";
import { TextRenderer } from "./TextRenderer";
import {
  getCurrentCanvasContent,
  selectOpenCanvasVersion,
  updateOpenCanvasContent,
} from "../../../utils/openCanvas";

import { Sparkles } from "lucide-react";

export function ArtifactRenderer({
  canvasState,
  isGenerating,
  onCanvasStateChange,
  onClose,
}) {
  const currentContent = useMemo(() => getCurrentCanvasContent(canvasState), [canvasState]);

  if (isGenerating) {
    return (
      <section className="oc-artifact-shell placeholder loading" aria-label="Generating workspace">
        <div className="oc-placeholder-content">
          <div className="oc-placeholder-loader">
            <Sparkles size={32} className="spinning-spark" />
          </div>
          <h3>Generating Workspace...</h3>
        </div>
      </section>
    );
  }

  if (!canvasState?.artifact || !currentContent) {
    return (
      <section className="oc-artifact-shell placeholder" aria-label="No workspace content">
        <ArtifactHeader
          title="Workspace"
          onClose={onClose}
        />
        <div className="oc-placeholder-content">
          <Sparkles size={32} style={{ opacity: 0.35 }} />
          <h3>No Canvas Yet</h3>
          <p style={{ opacity: 0.55, fontSize: "13px", maxWidth: "280px", textAlign: "center", lineHeight: 1.5 }}>
            Canvas content will appear here when the assistant generates visual artifacts during the conversation.
          </p>
        </div>
      </section>
    );
  }

  function setSelectedArtifact(index) {
    onCanvasStateChange(selectOpenCanvasVersion(canvasState, index));
  }

  function setCurrentContent(updates) {
    onCanvasStateChange(updateOpenCanvasContent(canvasState, currentContent.messageId, updates));
  }

  return (
    <section className="oc-artifact-shell" aria-label="Canvas workspace">
      <ArtifactHeader
        title={currentContent.title}
        currentIndex={canvasState.artifact.currentIndex}
        totalVersions={canvasState.artifact.contents.length}
        onClose={onClose}
        onPrevious={() => setSelectedArtifact(Math.max(1, canvasState.artifact.currentIndex - 1))}
        onNext={() => setSelectedArtifact(Math.min(canvasState.artifact.contents.length, canvasState.artifact.currentIndex + 1))}
      />

      <div className="oc-artifact-body">
        <TextRenderer
          content={currentContent}
          onChange={setCurrentContent}
          sources={currentContent.sources || []}
        />
      </div>
    </section>
  );
}
