import React, { useState, useEffect } from 'react';
import { Sparkles, X } from 'lucide-react';
import { safeStorageGet, safeStorageSet, triggerHaptic } from '../../../utils/common';

export function CanvasGuidePopup({ activeModeKey, messagesCount }) {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const isAgentMode = activeModeKey && activeModeKey !== 'assistant';
    const hasConversationStarted = messagesCount > 0;
    const hasSeenGuide = safeStorageGet(`diu_canvas_hint_v4_${activeModeKey}`);
    
    if (isAgentMode && hasConversationStarted && !hasSeenGuide) {
      const timer = setTimeout(() => setIsOpen(true), 1200);
      return () => clearTimeout(timer);
    } else {
      setIsOpen(false);
    }
  }, [activeModeKey, messagesCount]);

  const dismiss = () => {
    triggerHaptic(10);
    setIsOpen(false);
    safeStorageSet(`diu_canvas_hint_v4_${activeModeKey}`, 'true');
  };

  if (!isOpen) return null;

  return (
    <div className="canvas-hint-anchor">
      <div className="canvas-hint-box animate-float-in">
        <div className="hint-arrow"></div>
        <div className="hint-content">
          <Sparkles size={16} className="hint-spark" />
          <span className="hint-text">Workspace may take time to answer.</span>
          <button onClick={dismiss} className="hint-close" aria-label="Close">
            <X size={14} />
          </button>
        </div>
      </div>

      <style>{`
        .canvas-hint-anchor {
          position: fixed;
          top: 78px;
          right: 176px;
          z-index: 99999;
          pointer-events: none;
        }
        @media (max-width: 768px) {
          .canvas-hint-anchor {
            right: 16px;
            top: 70px;
          }
        }
        .canvas-hint-box {
          position: relative;
          pointer-events: auto;
          filter: none;
        }
        .animate-float-in {
          animation: floatIn 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
        }
        @keyframes floatIn {
          from { opacity: 0; transform: translateY(12px) scale(0.95); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        .hint-content {
          background: color-mix(in srgb, var(--accent) 92%, black 8%);
          color: var(--accent-contrast);
          padding: 14px 20px;
          border-radius: 18px;
          display: flex;
          align-items: center;
          gap: 12px;
          min-width: 340px;
          max-width: 100vw;
          border: 1px solid rgba(var(--accent-rgb), 0.22);
          box-shadow: none;
        }
        @media (max-width: 768px) {
          .hint-content {
            min-width: unset;
            width: max-content;
            max-width: calc(100vw - 32px);
          }
          .hint-arrow {
            right: 16px !important;
          }
        }
        .hint-arrow {
          position: absolute;
          top: -6px;
          right: 26px;
          width: 14px;
          height: 14px;
          background: color-mix(in srgb, var(--accent) 92%, black 8%);
          transform: rotate(45deg);
          border-left: 1px solid rgba(var(--accent-rgb), 0.22);
          border-top: 1px solid rgba(var(--accent-rgb), 0.22);
        }
        .hint-spark {
          color: color-mix(in srgb, var(--accent-contrast) 78%, var(--accent) 22%);
          animation: spark-pulse 2s infinite ease-in-out;
        }
        @keyframes spark-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.6; transform: scale(0.85); }
        }
        .hint-text {
          font-size: 14px;
          line-height: 1.4;
          font-weight: 600;
          font-family: 'Outfit', 'Inter', sans-serif;
        }
        .hint-close {
          color: var(--accent-contrast-muted);
          padding: 6px;
          margin-left: 8px;
          transition: all 0.25s;
          border-radius: 10px;
          flex-shrink: 0;
        }
        .hint-close:hover {
          color: var(--accent-contrast);
          background: var(--accent-contrast-soft);
          transform: rotate(90deg);
        }
      `}</style>
    </div>
  );
}
