import React from "react";
import { LayoutGrid, Moon, PanelRight, Plus, Sun } from "lucide-react";
import { motion } from "framer-motion";
import { ASSISTANT_MODE } from "../../../utils/constants";

export function TopBar({
  activeMode,
  theme,
  toggleTheme,
  isModePickerOpen,
  setIsModePickerOpen,
  isCanvasPanelManualOpen,
  handleCanvasAction,
  handleNewChat,
  handleBrandRefresh,
  hasConversationStarted,
  isCompactViewport,
  mobileCanvasHref,
  triggerHaptic,
}) {
  return (
    <header className="topbar">
      <a
        href="/"
        className="topbar-content brand-refresh-button"
        onClick={handleBrandRefresh}
        aria-label="Refresh site"
        title="Refresh site"
      >
        <div className="app-logo">
          <img
            src="/favicon.svg"
            alt="DIU monogram"
            className="app-logo-image"
          />
        </div>

        <div className="topbar-text">
          <h1>{activeMode.label}</h1>
        </div>
      </a>

      <div className="topbar-actions">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="mode-toggle"
          onClick={() => {
            triggerHaptic(8);
            setIsModePickerOpen(true);
          }}
          aria-label="Change assistant mode"
          title="Change assistant mode"
          type="button"
        >
          <LayoutGrid size={18} />
          <span className="sr-only">{activeMode.shortLabel}</span>
        </motion.button>
        
        <motion.button 
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="theme-toggle" 
          onClick={toggleTheme} 
          aria-label="Toggle theme" 
          title="Toggle theme"
        >
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </motion.button>

        {activeMode.key !== ASSISTANT_MODE && hasConversationStarted && (
          <motion.button 
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            initial={false}
            animate={{ 
              backgroundColor: isCanvasPanelManualOpen ? "var(--accent)" : "var(--control-bg)",
              color: isCanvasPanelManualOpen ? "var(--accent-contrast)" : "var(--control-text)",
              rotate: isCanvasPanelManualOpen ? 180 : 0
            }}
            className={`canvas-panel-toggle${isCanvasPanelManualOpen ? " active" : ""}`}
            onClick={handleCanvasAction}
            aria-label={
              isCompactViewport
                ? (mobileCanvasHref ? "Open Canvas Workspace" : "Generate Canvas Workspace")
                : (isCanvasPanelManualOpen ? "Hide Canvas Panel" : "Show Canvas Panel")
            }
            title={
              isCompactViewport
                ? (mobileCanvasHref ? "Open Canvas Workspace" : "Generate Canvas Workspace")
                : (isCanvasPanelManualOpen ? "Hide Canvas Panel" : "Show Canvas Panel")
            }
          >
            <PanelRight size={18} />
          </motion.button>
        )}

        <motion.button 
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="new-chat-pill" 
          onClick={handleNewChat} 
          aria-label="New chat" 
          title="New chat"
        >
          <Plus size={16} />
          <span>New Chat</span>
        </motion.button>
      </div>
    </header>
  );
}
