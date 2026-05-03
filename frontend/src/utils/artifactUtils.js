function cleanText(value) {
  return String(value || "").trim();
}

function removeMarkdownTableSeparatorRows(html) {
  return String(html || "").replace(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi, (row) => {
    const cells = Array.from(row.matchAll(/<t[dh][^>]*>\s*([^<]*)\s*<\/t[dh]>/gi)).map((match) => (
      String(match[1] || "").replace(/\s+/g, "")
    ));
    if (cells.length && cells.every((cell) => /^:?\s*-{2,}\s*:?$/.test(cell))) {
      return "";
    }
    return row;
  });
}

function looksLikeHtmlArtifact(value) {
  const text = cleanText(value);
  if (!text || text.length < 15) return false;

  if (/<(?:!doctype\s+html|html|body|main|section|article|header|nav|aside|form|table|canvas|svg)\b/i.test(text)) {
    return true;
  }

  const tags = Array.from(text.matchAll(/<\/?([a-z][a-z0-9:-]*)\b[^>]*>/gi)).map((match) => match[1].toLowerCase());
  const meaningfulTags = new Set([
    "main",
    "div",
    "section",
    "article",
    "header",
    "nav",
    "aside",
    "form",
    "label",
    "input",
    "select",
    "option",
    "button",
    "canvas",
    "svg",
    "style",
    "script",
    "p",
    "h1",
    "h2",
    "h3",
  ]);
  const matchedMeaningfulTags = tags.filter((tag) => meaningfulTags.has(tag));
  return matchedMeaningfulTags.length >= 4 && new Set(matchedMeaningfulTags).size >= 2;
}

function extractRawHtmlDocument(content) {
  const text = String(content || "");
  const docMatch = text.match(/(<!doctype\s+html[\s\S]*?(?:<\/html>|$))/i);
  if (docMatch) return docMatch[1].trim();

  const htmlMatch = text.match(/(<html[\s\S]*?(?:<\/html>|$))/i);
  if (htmlMatch) return htmlMatch[1].trim();

  return "";
}

function extractRawHtmlFragment(content) {
  const lines = String(content || "").split("\n");
  const startIndex = lines.findIndex((line) => /^\s*<(?:main|div|section|article|header|nav|aside|form|label|input|select|option|button|canvas|svg|style|script|p)\b/i.test(line));
  if (startIndex === -1) return "";

  const fragment = lines.slice(startIndex).join("\n").trim();
  if (looksLikeHtmlArtifact(fragment)) return fragment;

  // Final fallback: check for any valid block starting with <
  const anyTagMatch = fragment.match(/<([a-z][a-z0-9:-]*)\b[^>]*>[\s\S]*<\/\1>/i);
  return anyTagMatch?.[0] || "";
}

export function resolveArtifactUrl(url, apiBase = "") {
  const value = cleanText(url);
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  if (!apiBase) return value;
  return new URL(value, `${apiBase}/`).toString();
}

export function normalizeArtifacts(artifacts, apiBase = "") {
  const unique = new Map();

  for (const artifact of Array.isArray(artifacts) ? artifacts : []) {
    const filename = cleanText(artifact?.filename);
    const label = cleanText(artifact?.label) || filename || "Artifact";
    const url = resolveArtifactUrl(artifact?.url, apiBase);
    if (!url) continue;

    const key = cleanText(artifact?.id) || `${label}:${url}`;
    if (unique.has(key)) continue;

    unique.set(key, {
      id: cleanText(artifact?.id) || key,
      label,
      filename: filename || "artifact",
      title: cleanText(artifact?.title) || cleanText(artifact?.filename?.replace(/\.[^.]+$/, "")),
      url,
      mimeType: cleanText(artifact?.mime_type),
      kind: cleanText(artifact?.kind) || "document",
      sizeBytes: Number.isFinite(artifact?.size_bytes) ? artifact.size_bytes : null,
    });
  }

  return Array.from(unique.values());
}

export function extractHtmlFromContent(content) {
  const text = String(content || "");
  const fencedMatch = text.match(/```(?:html|HTML|xml)?\s*\n?([\s\S]*?)```/);
  if (fencedMatch?.[1] && looksLikeHtmlArtifact(fencedMatch[1])) {
    return removeMarkdownTableSeparatorRows(fencedMatch[1].trim());
  }

  const rawDocument = extractRawHtmlDocument(text);
  if (rawDocument) return removeMarkdownTableSeparatorRows(rawDocument);

  const rawFragment = extractRawHtmlFragment(text);
  if (rawFragment) return removeMarkdownTableSeparatorRows(rawFragment);

  return "";
}

export function extractTitleFromContent(content) {
  const html = extractHtmlFromContent(content);
  const header = String(content || "").match(/^#+\s+(.+)$/m)
    || html.match(/<title[^>]*>(.*?)<\/title>/i)
    || html.match(/<h[1-3][^>]*>(.*?)<\/h[1-3]>/i);
  if (header) {
    let text = header[1].replace(/<[^>]+>/g, "").trim();
    text = text.replace(/^\d+[\s.)-]+\s*/, "");
    if (text.length > 2) return text;
  }
  return "";
}

export function cleanArtifactMessageContent(content) {
  const text = String(content || "");
  const html = extractHtmlFromContent(text);
  let cleaned = text.replace(/```[\s\S]*?```/g, "\n\n");
  if (html && cleaned.includes(html)) {
    cleaned = cleaned.replace(html, "\n\n");
  }
  cleaned = cleaned.replace(/<!doctype\s+html[\s\S]*?(?:<\/html>|$)/gi, " ");
  cleaned = cleaned.replace(/<html[\s\S]*?(?:<\/html>|$)/gi, " ");
  cleaned = cleaned.replace(/\[canvas force unlock\]/gi, " ");
  cleaned = cleaned.replace(/Here is your workspace\. Open the canvas to explore it\.?/gi, " ");
  cleaned = cleaned.replace(/Based on the following content, generate a visual HTML version now\.?/gi, " ");
  return cleaned.replace(/\s+/g, " ").trim();
}

export function discoverArtifactFromContent(content) {
  const html = extractHtmlFromContent(content);
  if (!html) return null;
  return {
    workspaceHtml: html,
    title: extractTitleFromContent(content) || "Interactive Tool",
    kind: "workspace",
  };
}

export function buildMobileCanvasHref(content) {
  if (!content) return "";
  if (content.url) return content.url;
  if (content.workspaceHtml) {
    return `data:text/html;charset=utf-8,${encodeURIComponent(content.workspaceHtml)}`;
  }
  return "";
}
