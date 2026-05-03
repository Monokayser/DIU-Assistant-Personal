import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  FileText,
  FileSearch,
} from "lucide-react";
import { MarkdownMessage } from "../../chat/components/MessageContent";

function getAvailableViews(content, sources = []) {
  const views = [];
  const hasPdfSource = sources.some(s => s.url?.toLowerCase().endsWith(".pdf"));
  if (hasPdfSource) views.push("source");

  const hasWorkspaceContent = Boolean(content?.workspaceHtml || content?.workspaceUrl);
  if (hasWorkspaceContent) {
    views.push("document");
  } else {
    // If it's a code block or document kind, still allow document view for markdown rendering
    views.push("document");
  }

  return views;
}

function getDefaultView(views) {
  if (views.includes("document")) {
    return "document";
  }
  return views[0] || "document";
}



function stripHtml(html) {
  return String(html || "")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isDocumentStyleWorkspace(content) {
  if (!(content.kind === "workspace" || content.workspaceHtml || content.code)) {
    return false;
  }

  const html = String(content.workspaceHtml || content.code || "");
  const lowerHtml = html.toLowerCase();
  const explicitDocumentSignals = [
    "data-canvas-format=\"document\"",
    "data-canvas-format='document'",
    "class=\"paper",
    "class='paper",
    "contenteditable",
    "document-style",
    "report",
    "brief",
    "letter",
    "article",
  ];
  if (explicitDocumentSignals.some((signal) => lowerHtml.includes(signal))) {
    return true;
  }

  const interactiveSignals = /<(input|select|textarea|canvas|svg)\b|onclick=|addeventlistener|function\s+\w+\s*\(|zen-btn|data-prompt|data-canvas-format=["']interactive["']/i;
  const headingCount = (html.match(/<h[1-3]\b/gi) || []).length;
  const paragraphCount = (html.match(/<(p|li|table|section|article)\b/gi) || []).length;
  return (stripHtml(html).length > 600 || paragraphCount >= 4) && !interactiveSignals.test(lowerHtml);
}

function applyCanvasBrandTheme(html) {
  let themed = String(html || "");

  // 1. Core Layout & Reset (Non-intrusive)
  const coreStyles = `
  <style id="diu-canvas-core-layout">
    html, body {
      max-width: 100%;
      overflow-x: hidden;
      background: transparent;
      scroll-behavior: smooth;
      margin: 0;
      padding: 0;
    }
    img, svg, canvas, video {
      max-width: 100%;
      height: auto;
    }
  </style>`;

  // 2. DIU Design Tokens (CSS Variables only)
  const brandTokens = `
  <style id="diu-canvas-tokens">
    :root {
      --diu-950: #122017;
      --diu-900: #183b2d;
      --diu-800: #245f35;
      --diu-700: #2f7a45;
      --diu-600: #3d8b53;
      --diu-500: #5fb171;
      --diu-100: #d9ead7;
      --diu-50: #f5f8f2;
    }
    body {
      font-family: 'Outfit', 'Inter', system-ui, sans-serif;
      color: var(--diu-950);
    }
    .zen-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 10px 24px;
      border-radius: 12px;
      background: var(--diu-900);
      color: #fff !important;
      font-weight: 600;
      transition: all 0.2s ease;
      cursor: pointer;
      border: none;
      text-decoration: none !important;
    }
    .zen-btn:hover {
      background: var(--diu-800);
      transform: translateY(-1px);
    }
  </style>`;

  // 3. Dependency Injection (Only if missing)
  const dependencies = [];
  if (!themed.includes("fonts.googleapis.com")) {
    dependencies.push('<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@400;500;600;700&display=swap" rel="stylesheet">');
  }
  if (!themed.includes("cdn.tailwindcss.com")) {
    dependencies.push('<script src="https://cdn.tailwindcss.com"></script>');
  }
  if (!themed.includes("chart.js")) {
    dependencies.push('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>');
  }

  const bootstrap = `
  ${dependencies.join('\n')}
  <script id="diu-canvas-bootstrap">
    if (window.tailwind) {
      tailwind.config = {
        theme: {
          extend: {
            colors: {
              diu: {
                950: '#122017', 900: '#183b2d', 800: '#245f35', 700: '#2f7a45',
                600: '#3d8b53', 500: '#5fb171', 100: '#d9ead7', 50: '#f5f8f2',
              }
            }
          }
        }
      }
    }
  </script>`;

  if (themed.includes('id="diu-canvas-core-layout"')) {
    return themed;
  }

  const injection = `\n${coreStyles}\n${brandTokens}\n${bootstrap}\n`;

  // Avoid injecting into document format artifacts that already have a structured shell
  if (themed.includes('data-canvas-format="document"')) {
    return themed;
  }

  if (/<\/head>/i.test(themed)) {
    return themed.replace(/<\/head>/i, `${injection}</head>`);
  }
  return injection + themed;
}

export function TextRenderer({
  content,
  onChange,
  sources = [],
}) {
  const availableViews = useMemo(() => getAvailableViews(content, sources), [content, sources]);
  const [activeView, setActiveView] = useState(() => getDefaultView(availableViews));
  const selectionRootRef = useRef(null);
  const iframeRef = useRef(null);

  useEffect(() => {
    if (!availableViews.includes(activeView)) {
      setActiveView(getDefaultView(availableViews));
    }
  }, [activeView, availableViews, content]);

  useEffect(() => {
    setActiveView(getDefaultView(availableViews));
  }, [content?.messageId, availableViews, content]);

  useEffect(() => {
    if (content?.workspaceHtml || !content?.workspaceUrl) {
      return undefined;
    }

    const controller = new AbortController();

    fetch(content.workspaceUrl, { signal: controller.signal })
      .then((response) => response.ok ? response.text() : "")
      .then((workspaceHtml) => {
        if (!workspaceHtml) return;
        onChange({ workspaceHtml, code: content?.code || workspaceHtml, language: content?.language || "html" });
      })
      .catch(() => {
        // Best-effort enhancement only.
      });

    return () => controller.abort();
  }, [content?.code, content?.language, content?.workspaceHtml, content?.workspaceUrl, onChange]);


  useEffect(() => {
    if (!(content?.kind === "workspace" || content?.workspaceHtml || content?.workspaceUrl)) return;
    const currentHtml = content?.workspaceHtml || content?.code || "";
    if (!currentHtml) return;
    
    // Only apply branding to interactive artifacts, let document artifacts use their own style
    if (isDocumentStyleWorkspace(content)) return;

    const brandedHtml = applyCanvasBrandTheme(currentHtml);
    if (brandedHtml !== currentHtml) {
      onChange({ workspaceHtml: brandedHtml, code: brandedHtml, language: "html" });
    }
  }, [content?.code, content?.kind, content?.workspaceHtml, content?.workspaceUrl, onChange, content]);




  const isWorkspace = content?.kind === "workspace";
  const documentHtml = content?.workspaceHtml || (isWorkspace ? content?.code : "");
  const isPlaceholderContent = typeof content?.fullMarkdown === "string" && 
    (content.fullMarkdown.includes("Open the canvas to explore it") || content.fullMarkdown.includes("Here is your workspace"));

  // 1. Initializing state
  if (isWorkspace && !documentHtml && !content?.workspaceUrl) {
    return (
      <div className="oc-placeholder-content" style={{ padding: "80px 40px", textAlign: "center" }}>
        <div className="oc-placeholder-loader" style={{ marginBottom: "20px" }}>
          <div className="spinning-spark" style={{ width: "38px", height: "38px", margin: "0 auto", opacity: 0.6 }} />
        </div>
        <h3 style={{ fontSize: "18px", marginBottom: "8px", color: "var(--text-strong)" }}>Preparing Workspace...</h3>
        <p style={{ opacity: 0.5, fontSize: "14px" }}>Optimizing environment for your artifact</p>
      </div>
    );
  }

  // 2. Suppress redundant placeholder text
  if (isPlaceholderContent && isWorkspace && !documentHtml) {
    return null;
  }

  return (
    <section className="oc-text-renderer">
      {availableViews.length > 1 && (
        <div className="oc-renderer-toolbar">
          <div className="oc-renderer-toggle" role="tablist" aria-label="Artifact view mode">
            {availableViews.map((view) => (
              <button
                key={view}
                type="button"
                className={`oc-toggle-button${activeView === view ? " active" : ""}`}
                aria-pressed={activeView === view}
                onClick={() => setActiveView(view)}
              >
                {view === "document" ? <FileText size={14} /> : null}
                {view === "source" ? <FileSearch size={14} /> : null}
              </button>
            ))}
          </div>
        </div>
      )}

      {activeView === "source" ? (
        <div className="oc-stage-shell">
          <div className="oc-stage-surface oc-stage-source">
            <iframe
              className="oc-source-frame"
              title="Source document"
              src={sources.find(s => s.url?.toLowerCase().endsWith(".pdf"))?.url}
            />
          </div>
        </div>
      ) : null}

      {activeView === "document" ? (
        documentHtml ? (
          <div className="oc-stage-shell">
            <div className="oc-stage-surface oc-stage-document">
              <iframe
                ref={iframeRef}
                className="oc-document-frame"
                title={content.title || "Document preview"}
                sandbox="allow-forms allow-modals allow-popups allow-scripts"
                srcDoc={documentHtml}
              />
            </div>
          </div>
        ) : (
          <div className="oc-stage-shell">
            <article
              ref={selectionRootRef}
              className="oc-rendered-document"
            >
              <div className="oc-stage-surface oc-rendered-document-inner artifact-content">
                <MarkdownMessage content={content.fullMarkdown || ""} />
              </div>
            </article>
          </div>
        )
      ) : null}
    </section>
  );
}
