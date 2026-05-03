import { safeStorageGet, safeStorageSet } from "./common.js";
import { discoverArtifactFromContent } from "./artifactUtils.js";

const STORAGE_PREFIX = "diu-open-canvas:";

function normalizeText(value) {
  return String(value || "").replace(/\r/g, "").trim();
}

function cleanInline(value) {
  return String(value || "")
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function unwrapModePrompt(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const match = text.match(/(?:^|\n)\s*User question:\s*([\s\S]+)$/i);
  return match?.[1] ? String(match[1]).trim() : text;
}

function stripCanvasUpdatePrefix(value) {
  let text = unwrapModePrompt(value);
  if (!text) return "";

  text = text.replace(/^(update canvas:\s*)+/gi, "");
  text = text.replace(/^update\s+the\s+current\s+canvas\s+artifact\s+in\s+place\.?\s*/i, "");
  text = text.replace(/^artifact title:\s*/i, "");
  text = text.replace(/\s+/g, " ").trim();
  return text;
}

function findNearestUserPrompt(messages, assistantIndex) {
  for (let index = assistantIndex - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message?.role === "user" && String(message.content || "").trim()) {
      return String(message.content).trim();
    }
  }
  return "";
}

function deriveTitle(prompt, content, metadata) {
  const promptTitle = cleanInline(stripCanvasUpdatePrefix(prompt)).replace(/[?!.]+$/, "");
  if (promptTitle) return promptTitle.slice(0, 88);

  const headingMatch = String(content || "").match(/^#{1,6}\s+(.+)$/m);
  if (headingMatch?.[1]) return cleanInline(headingMatch[1]).slice(0, 88);

  const boldHeadingMatch = String(content || "").match(/^\*\*([^*]+)\*\*$/m);
  if (boldHeadingMatch?.[1]) return cleanInline(boldHeadingMatch[1]).slice(0, 88);

  if (content && content.length > 5) {
    const lines = content.split("\n").filter(l => l.trim().length > 3);
    if (lines[0]) return cleanInline(lines[0]).slice(0, 88);
  }

  return "Untitled artifact";
}

function selectWorkspaceArtifact(artifacts) {
  return (Array.isArray(artifacts) ? artifacts : []).find((artifact) => (
    artifact?.mimeType === "text/html" || artifact?.kind === "workspace"
  )) || null;
}

function extractCodeBlock(content) {
  const matches = [...String(content || "").matchAll(/```([\w+-]*)\n([\s\S]*?)```/g)];
  if (!matches.length) return null;

  const largest = matches
    .map((match) => ({
      language: String(match[1] || "").trim().toLowerCase() || "text",
      code: String(match[2] || "").replace(/\s+$/, ""),
      fullMatch: match[0],
    }))
    .sort((left, right) => right.code.length - left.code.length)[0];

  if (!largest?.code) return null;
  return largest;
}

function toCanvasEntry(messages, message, messageIndex) {
  const markdown = normalizeText(message.content);
  if (!markdown) return null;

  const prompt = findNearestUserPrompt(messages, messageIndex);
  const workspaceArtifact = selectWorkspaceArtifact(message.artifacts) || discoverArtifactFromContent(markdown);
  const codeBlock = extractCodeBlock(markdown);
  if (!workspaceArtifact && !codeBlock) return null;
  const key = String(message.id || `artifact-${messageIndex + 1}`);
  const sources = Array.isArray(message.sources) ? message.sources : [];

  return {
    key,
    messageId: key,
    index: 0,
    kind: workspaceArtifact ? "workspace" : codeBlock ? "code" : "document",
    title: cleanInline(workspaceArtifact?.title) || deriveTitle(prompt, markdown, message.metadata),
    fullMarkdown: markdown,
    code: codeBlock?.code || "",
    language: codeBlock?.language || "",
    workspaceUrl: workspaceArtifact?.url || "",
    workspaceHtml: workspaceArtifact?.workspaceHtml || "",
    prompt,
    createdAt: String(message.created_at || new Date().toISOString()),
    assistantLabel: null,
    sourceCount: sources.length,
    sources,
    metadata: message.metadata || null,
    savedAt: String(message.created_at || ""),
    isDirty: false,
    hasLocalChanges: false,
    hasWorkspaceSnapshot: false,
  };
}

function getVersionId(content) {
  return String(content?.messageId || content?.key || "");
}

function preserveLocalEdits(previous, incoming) {
  if (!previous) return incoming;

  return {
    ...incoming,
    fullMarkdown: previous.hasLocalChanges ? previous.fullMarkdown : incoming.fullMarkdown,
    code: previous.hasLocalChanges ? previous.code : incoming.code,
    workspaceHtml: previous.hasWorkspaceSnapshot ? previous.workspaceHtml : incoming.workspaceHtml || previous.workspaceHtml || "",
    savedAt: previous.savedAt || incoming.savedAt,
    isDirty: Boolean(previous.isDirty),
    hasLocalChanges: Boolean(previous.hasLocalChanges),
    hasWorkspaceSnapshot: Boolean(previous.hasWorkspaceSnapshot || incoming.workspaceHtml),
  };
}

function reindexContents(contents) {
  return contents.map((content, index) => ({
    ...content,
    index: index + 1,
  }));
}

function toCanvasContents(messages) {
  const filtered = [];

  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index];
    if (message?.role !== "assistant") continue;
    if (String(message?.mode || "").trim() === "assistant") continue;

    const entry = toCanvasEntry(messages, message, index);
    if (entry) filtered.push(entry);
  }

  return filtered;
}

export function getCanvasStorageKey(conversationId) {
  if (!conversationId) return "";
  return `${STORAGE_PREFIX}${conversationId}`;
}

export function loadOpenCanvasState(conversationId) {
  const key = getCanvasStorageKey(conversationId);
  if (!key) return null;

  const raw = safeStorageGet(key);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    
    if (Array.isArray(parsed?.artifact?.contents)) {
      parsed.artifact.contents = parsed.artifact.contents.filter((c) => c.kind === "workspace" || c.kind === "code");
      if (parsed.artifact.contents.length === 0) return null;
    }
    
    return parsed;
  } catch {
    return null;
  }
}

export function persistOpenCanvasState(conversationId, state) {
  const key = getCanvasStorageKey(conversationId);
  if (!key) return;
  safeStorageSet(key, state ? JSON.stringify(state) : "");
}

export function buildOpenCanvasState(previousState, messages, conversationId = null) {
  const incomingContents = toCanvasContents(Array.isArray(messages) ? messages : []);
  if (!incomingContents.length) return null;

  const previousContents = Array.isArray(previousState?.artifact?.contents)
    ? previousState.artifact.contents.filter((c) => c.kind === "workspace" || c.kind === "code")
    : [];
  const previousByVersion = new Map(previousContents.map((content) => [getVersionId(content), content]));
  const mergedContents = reindexContents(incomingContents.map((content) => (
    preserveLocalEdits(previousByVersion.get(getVersionId(content)), content)
  )));

  const previousCurrentId = String(previousState?.currentVersionId || "");
  const previousCurrent = mergedContents.find((content) => getVersionId(content) === previousCurrentId);
  const latestContent = mergedContents[mergedContents.length - 1];
  const previousLatestId = getVersionId(previousContents[previousContents.length - 1]);
  const latestId = getVersionId(latestContent);
  const hasNewIncomingVersion = Boolean(latestId && latestId !== previousLatestId);
  const currentContent = hasNewIncomingVersion ? latestContent : (previousCurrent || latestContent);

  return {
    conversationId,
    currentVersionId: getVersionId(currentContent),
    updatedAt: new Date().toISOString(),
    artifact: {
      currentIndex: currentContent.index,
      contents: mergedContents,
    },
  };
}

export function getArtifactContent(artifact) {
  if (!artifact?.contents?.length) return null;
  return artifact.contents.find((entry) => entry.index === artifact.currentIndex)
    || artifact.contents[artifact.contents.length - 1]
    || null;
}

export function getCurrentCanvasContent(canvasState) {
  return getArtifactContent(canvasState?.artifact);
}

export function selectOpenCanvasVersion(canvasState, nextIndex) {
  if (!canvasState?.artifact?.contents?.length) return canvasState;
  const selected = canvasState.artifact.contents.find((entry) => entry.index === nextIndex);
  if (!selected) return canvasState;

  return {
    ...canvasState,
    currentVersionId: getVersionId(selected),
    artifact: {
      ...canvasState.artifact,
      currentIndex: selected.index,
    },
  };
}

export function updateOpenCanvasContent(canvasState, versionId, updates = {}) {
  if (!canvasState?.artifact?.contents?.length || !versionId) return canvasState;

  const nextContents = canvasState.artifact.contents.map((content) => {
    if (getVersionId(content) !== versionId) return content;

    return {
      ...content,
      ...updates,
      savedAt: new Date().toISOString(),
      isDirty: false,
      hasLocalChanges: Boolean(
        updates.fullMarkdown !== undefined
        || updates.code !== undefined
        || content.hasLocalChanges
      ),
      hasWorkspaceSnapshot: Boolean(
        updates.workspaceHtml
        || content.workspaceHtml
        || content.hasWorkspaceSnapshot
      ),
    };
  });

  return {
    ...canvasState,
    updatedAt: new Date().toISOString(),
    artifact: {
      ...canvasState.artifact,
      contents: nextContents,
    },
  };
}


export function buildOpenCanvasPreview(content) {
  const text = normalizeText(content);
  if (!text) return "";

  const sections = text
    .split(/\n\s*\n/)
    .map((section) => cleanInline(section))
    .filter(Boolean)
    .filter((section) => !/^(task|what i did|working result|still need|next action)$/i.test(section));
  const previewParts = [];

  if (sections[0]) {
    previewParts.push(sections[0]);
  }

  const bulletLines = text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => /^[-*]\s+/.test(line))
    .slice(0, 2)
    .map((line) => `- ${cleanInline(line.replace(/^[-*]\s+/, ""))}`);

  if (bulletLines.length) {
    previewParts.push(bulletLines.join("\n"));
  }

  return previewParts.filter(Boolean).join("\n\n").trim();
}
