import React, { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileSearch,
  Sparkles
} from "lucide-react";

const FAST_TYPE_MIN_DURATION_MS = 140;
const FAST_TYPE_MAX_DURATION_MS = 900;
const FAST_TYPE_MS_PER_CHAR = 4;

export function ThinkingStatus({ status }) {
  const message = status?.status === "analyzing_file" 
    ? `Analyzing ${status.filename}...`
    : status?.status === "generating_artifact"
    ? "Building DIU tool..."
    : "Thinking...";

  return (
    <div className="thinking-status">
      <span className="thinking-spark" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}

export function AnswerStatus({ metadata, sources, triggerHaptic }) {
  const [isOpen, setIsOpen] = useState(false);
  if (!sources || sources.length === 0) return null;

  return (
    <div className="answer-status" data-open={isOpen}>
      <button
        type="button"
        className="answer-status-toggle"
        onClick={() => {
          setIsOpen(!isOpen);
          triggerHaptic(5);
        }}
      >
        <CheckCircle2 size={14} className="verified-icon" />
        <span>Verified by DIU Context</span>
        {isOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>

      {isOpen && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="answer-status-details"
        >
          <div className="status-detail-wide">
            <dt>Grounding Sources</dt>
            <dd>
              {sources.map((s, i) => (
                <div key={i} className="source-item">
                  <Search size={10} />
                  <span>{s.title || "Untitled Document"}</span>
                </div>
              ))}
            </dd>
          </div>
        </motion.div>
      )}
    </div>
  );
}

function stripArtifacts(text) {
  if (!text) return "";

  // Only strip the internal <artifact> blocks which are handled by the Canvas UI
  let clean = text.replace(/<artifact[\s\S]*?<\/artifact>/gi, "");
  clean = clean.replace(/<artifact[\s\S]*$/gi, "");

  // Strip internal system signals
  clean = clean.replace(/\[canvas force unlock\]/gi, "");

  return clean;
}

export function MarkdownMessage({ content }) {
  const cleanContent = stripArtifacts(content);
  const lines = cleanContent.split("\n");
  const blocks = [];
  let listItems = [];
  let orderedItems = [];
  let orderedStart = 1;
  let inTable = false;
  let tableRows = [];
  let inCodeBlock = false;
  let codeLines = [];
  let codeLanguage = "";
  let inThoughtBlock = false;
  let thoughtLines = [];
  let inCommentBlock = false;

  function flushLists() {
    if (listItems.length) {
      blocks.push(<ul key={`ul-${blocks.length}`}>{listItems.map((item, i) => <li key={i}>{renderInline(item)}</li>)}</ul>);
      listItems = [];
    }
    if (orderedItems.length) {
      blocks.push(<ol start={orderedStart} key={`ol-${blocks.length}`}>{orderedItems.map((item, i) => <li key={i}>{renderInline(item)}</li>)}</ol>);
      orderedItems = [];
    }
  }

  function flushTable() {
    if (inTable && tableRows.length) {
      const parsedRows = tableRows
        .map(parseTableRow)
        .filter((row) => row.length > 0);
      const header = parsedRows[0] || [];
      const bodyRows = parsedRows
        .slice(1)
        .flatMap((row) => normalizeTableRow(row, header.length));

      if (header.length > 0) {
        blocks.push(
          <div className="table-container" key={`table-${blocks.length}`}>
            <table>
              <thead>
                <tr>{header.map((cell, i) => <th key={i}>{renderInline(cell)}</th>)}</tr>
              </thead>
              <tbody>
                {bodyRows.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, cellIndex) => <td key={cellIndex}>{renderInline(cell)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      tableRows = [];
      inTable = false;
    }
  }

  function flushCodeBlock() {
    if (inCodeBlock) {
      blocks.push(
        <div className="code-block-container" key={`code-${blocks.length}`}>
          {codeLanguage && <div className="code-block-header">{codeLanguage}</div>}
          <pre><code>{codeLines.join("\n")}</code></pre>
        </div>
      );
      codeLines = [];
      inCodeBlock = false;
      codeLanguage = "";
    }
  }

  function flushThoughtBlock() {
    if (inThoughtBlock) {
      blocks.push(<ThoughtSection key={`thought-${blocks.length}`} content={thoughtLines.join("\n")} />);
      thoughtLines = [];
      inThoughtBlock = false;
    }
  }

  function flushAll() {
    flushLists();
    flushTable();
    flushCodeBlock();
    flushThoughtBlock();
  }

  lines.forEach((line, index) => {
    const trimmed = line.trim();

    if (trimmed.startsWith("<!--")) {
      flushAll();
      if (!trimmed.endsWith("-->")) {
        inCommentBlock = true;
      }
      return;
    }

    if (trimmed.endsWith("-->") && inCommentBlock) {
      inCommentBlock = false;
      return;
    }

    if (inCommentBlock) {
      return;
    }

    if (trimmed.startsWith("<thought>")) {
      flushAll();
      inThoughtBlock = true;
      const initialContent = trimmed.replace("<thought>", "");
      if (initialContent) thoughtLines.push(initialContent);
      return;
    }

    if (trimmed.endsWith("</thought>") && inThoughtBlock) {
      const finalContent = trimmed.replace("</thought>", "");
      if (finalContent) thoughtLines.push(finalContent);
      flushThoughtBlock();
      return;
    }

    if (inThoughtBlock) {
      thoughtLines.push(line);
      return;
    }

    if (trimmed.startsWith("```")) {
      if (inCodeBlock) flushCodeBlock();
      else {
        flushAll();
        inCodeBlock = true;
        codeLanguage = trimmed.slice(3).trim();
      }
      return;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      return;
    }

    if (!trimmed) {
      flushAll();
      return;
    }

    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      flushLists();
      inTable = true;
      tableRows.push(trimmed);
      return;
    }

    flushTable();

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      if (orderedItems.length) flushLists();
      listItems.push(unordered[1]);
      return;
    }

    const ordered = trimmed.match(/^(\d+)\.\s+(.+)$/);
    if (ordered) {
      if (listItems.length) flushLists();
      if (!orderedItems.length) orderedStart = Number.parseInt(ordered[1], 10) || 1;
      orderedItems.push(ordered[2]);
      return;
    }

    flushAll();

    const quote = trimmed.match(/^>\s?(.+)$/);
    if (quote) {
      blocks.push(<blockquote key={`quote-${index}`}>{renderInline(quote[1])}</blockquote>);
      return;
    }

    const headerMatch = trimmed.match(/^(#{1,6})\s*(.+)$/);
    if (headerMatch) {
      const Tag = `h${headerMatch[1].length}`;
      blocks.push(<Tag key={`h-${index}`}>{renderInline(headerMatch[2])}</Tag>);
      return;
    }

    const heading = trimmed.match(/^\*\*(.+)\*\*$/);
    if (heading) {
      blocks.push(<h3 key={`hx-${index}`}>{renderInline(heading[1])}</h3>);
      return;
    }

    if (/^-{3,}$/.test(trimmed)) {
      flushAll();
      blocks.push(<hr key={`hr-${index}`} />);
      return;
    }

    blocks.push(<p key={`p-${index}`}>{renderInline(trimmed)}</p>);
  });

  flushAll();
  return <>{blocks}</>;
}

function parseTableRow(row) {
  const cells = row.split("|");
  return cells.slice(1, cells.length - 1).map((cell) => cell.trim());
}

function isTableSeparatorCell(cell) {
  return /^:?-{2,}:?$/.test(cell.trim());
}

function normalizeTableRow(row, columnCount) {
  if (!columnCount || row.every(isTableSeparatorCell)) return [];

  const cells = row.filter((cell) => !isTableSeparatorCell(cell));
  if (!cells.length) return [];

  const rows = [];
  for (let index = 0; index < cells.length; index += columnCount) {
    const chunk = cells.slice(index, index + columnCount);
    if (chunk.some((cell) => cell.trim())) {
      rows.push([...chunk, ...Array(Math.max(columnCount - chunk.length, 0)).fill("")]);
    }
  }

  return rows;
}

function ThoughtSection({ content }) {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div className="thought-section">
      <button
        type="button"
        className="thought-toggle"
        onClick={() => setIsOpen(!isOpen)}
      >
        {isOpen ? "Hide thinking" : "Show thinking"}
        <span className={`chevron ${isOpen ? "up" : "down"}`}>▼</span>
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: "easeInOut" }}
            className="thought-content"
          >
            <MarkdownMessage content={content} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function TypewriterMarkdown({ content, messageId, scrollToBottom, onComplete }) {
  const [displayed, setDisplayed] = useState("");

  useEffect(() => {
    setDisplayed("");

    if (!content) {
      onComplete?.();
      return undefined;
    }

    const duration = Math.min(
      FAST_TYPE_MAX_DURATION_MS,
      Math.max(FAST_TYPE_MIN_DURATION_MS, content.length * FAST_TYPE_MS_PER_CHAR),
    );

    let frameId = 0;
    let startTime = 0;

    function step(timestamp) {
      if (!startTime) startTime = timestamp;
      const elapsed = timestamp - startTime;
      const progress = Math.min(1, elapsed / duration);
      const nextLength = Math.max(
        1,
        Math.floor(content.length * (1 - ((1 - progress) ** 3))),
      );

      setDisplayed(content.slice(0, nextLength));
      scrollToBottom();

      if (progress >= 1 || nextLength >= content.length) {
        setDisplayed(content);
        onComplete?.();
        return;
      }

      frameId = window.requestAnimationFrame(step);
    }

    frameId = window.requestAnimationFrame(step);

    return () => window.cancelAnimationFrame(frameId);
  }, [content, messageId, onComplete, scrollToBottom]);

  return displayed === content
    ? <MarkdownMessage content={displayed} />
    : <div className="live-answer-text">{stripArtifacts(displayed)}</div>;
}

function renderInline(text) {
  const withBreaks = text.split(/<br\s*\/?>/gi).map((part, index, items) => (
    <span key={`brpart-${index}`}>
      {parseStyling(part)}
      {index < items.length - 1 && <br />}
    </span>
  ));

  return <>{withBreaks}</>;
}

function parseStyling(text) {
  const parts = text.split(/(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);

  return parts.map((part, index) => {
    const link = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) {
      return (
        <a key={`${part}-${index}`} href={link[2]} target="_blank" rel="noreferrer">
          {link[1]}
        </a>
      );
    }

    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }

    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code className="inline-code" key={`${part}-${index}`}>
          {part.slice(1, -1)}
        </code>
      );
    }

    return <span key={`${part}-${index}`}>{part}</span>;
  });
}
