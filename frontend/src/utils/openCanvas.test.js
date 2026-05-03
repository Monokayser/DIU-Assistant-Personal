import test from "node:test";
import assert from "node:assert/strict";

import {
  buildOpenCanvasPreview,
  buildOpenCanvasState,
  getArtifactContent,
  selectOpenCanvasVersion,
  updateOpenCanvasContent,
} from "./openCanvas.js";

test("buildOpenCanvasState builds workspace versions from assistant replies", () => {
  const state = buildOpenCanvasState(null, [
    { role: "user", content: "Compare CSE and SWE" },
    {
      id: "a1",
      role: "assistant",
      content: "First answer",
      sources: [{ title: "Programs" }],
      artifacts: [{ id: "w1", mimeType: "text/html", kind: "workspace", url: "/api/artifacts/demo/w1" }],
    },
    { role: "user", content: "Now make it shorter" },
    {
      id: "a2",
      role: "assistant",
      content: "Second answer",
      sources: [],
    },
  ], "conversation-1");

  assert.equal(state.artifact.currentIndex, 1);
  assert.equal(state.artifact.contents.length, 1);
  assert.equal(state.artifact.contents[0].kind, "workspace");
  assert.equal(state.artifact.contents[0].workspaceUrl, "/api/artifacts/demo/w1");
  const selected = selectOpenCanvasVersion(state, 1);
  assert.equal(getArtifactContent(selected.artifact).title, "Compare CSE and SWE");
});

test("buildOpenCanvasState prefers artifact titles over placeholder user prompts", () => {
  const state = buildOpenCanvasState(null, [
    { role: "user", content: "Generating visual companion..." },
    {
      id: "a-title",
      role: "assistant",
      content: "Here is your workspace. Open the canvas to explore it.",
      artifacts: [
        {
          id: "w-title",
          mimeType: "text/html",
          kind: "workspace",
          url: "/api/artifacts/demo/workspace.html",
          title: "DIU Academic Planning Dashboard",
        },
      ],
    },
  ], "conversation-title");

  assert.equal(state.artifact.contents[0].title, "DIU Academic Planning Dashboard");
});

test("buildOpenCanvasState preserves local edits for existing versions", () => {
  const initial = buildOpenCanvasState(null, [
    { role: "user", content: "Make a checklist" },
    {
      id: "a1",
      role: "assistant",
      content: "Original answer",
      artifacts: [{ id: "w1", mimeType: "text/html", kind: "workspace", url: "/api/artifacts/demo/w1" }],
    },
  ], "conversation-2");

  const edited = updateOpenCanvasContent(initial, "a1", {
    fullMarkdown: "Locally edited answer",
  });

  const merged = buildOpenCanvasState(edited, [
    { role: "user", content: "Make a checklist" },
    {
      id: "a1",
      role: "assistant",
      content: "Original answer",
      artifacts: [{ id: "w1", mimeType: "text/html", kind: "workspace", url: "/api/artifacts/demo/w1" }],
    },
  ], "conversation-2");

  assert.equal(getArtifactContent(merged.artifact).fullMarkdown, "Locally edited answer");
  assert.equal(getArtifactContent(merged.artifact).hasLocalChanges, true);
});

test("buildOpenCanvasState auto-selects the newest incoming version", () => {
  const initial = buildOpenCanvasState(null, [
    { role: "user", content: "How can I apply?" },
    {
      id: "a1",
      role: "assistant",
      content: "First answer",
      artifacts: [{ id: "w1", mimeType: "text/html", kind: "workspace", url: "/api/artifacts/demo/w1" }],
    },
  ], "conversation-4");

  const olderSelected = selectOpenCanvasVersion(initial, 1);
  const merged = buildOpenCanvasState(olderSelected, [
    { role: "user", content: "How can I apply?" },
    {
      id: "a1",
      role: "assistant",
      content: "First answer",
      artifacts: [{ id: "w1", mimeType: "text/html", kind: "workspace", url: "/api/artifacts/demo/w1" }],
    },
    { role: "user", content: "Rewrite it more simply" },
    {
      id: "a2",
      role: "assistant",
      content: "Second answer",
      artifacts: [{ id: "w2", mimeType: "text/html", kind: "workspace", url: "/api/artifacts/demo/w2" }],
    },
  ], "conversation-4");

  assert.equal(merged.currentVersionId, "a2");
  assert.equal(merged.artifact.currentIndex, 2);
});

test("buildOpenCanvasState ignores assistant replies without canvas artifacts", () => {
  const state = buildOpenCanvasState(null, [
    { role: "user", content: "Question" },
    {
      role: "assistant",
      content: "First answer",
    },
    {
      role: "assistant",
      content: "Second answer",
    },
  ], "conversation-3");

  assert.equal(state, null);
});

test("buildOpenCanvasState ignores plain DIU assistant-mode replies", () => {
  const state = buildOpenCanvasState(null, [
    { role: "user", content: "What scholarship opportunities are available?" },
    {
      id: "a1",
      role: "assistant",
      mode: "assistant",
      content: "Plain assistant answer",
      artifacts: [
        { id: "html-1", mimeType: "text/html", kind: "workspace", url: "/api/artifacts/demo/scholarships.html" },
      ],
    },
  ], "conversation-6");

  assert.equal(state, null);
});

test("buildOpenCanvasState ignores legacy PDF artifacts and keeps the workspace", () => {
  const state = buildOpenCanvasState(null, [
    { role: "user", content: "Write an admission checklist" },
    {
      id: "a1",
      role: "assistant",
      content: "## Admission checklist",
      artifacts: [
        { id: "html-1", mimeType: "text/html", kind: "workspace", url: "/api/artifacts/demo/checklist.html" },
        { id: "pdf-1", mimeType: "application/pdf", kind: "document", url: "/api/artifacts/demo/checklist.pdf", filename: "checklist.pdf" },
      ],
    },
  ], "conversation-5");

  const content = getArtifactContent(state.artifact);
  assert.equal(content.workspaceUrl, "/api/artifacts/demo/checklist.html");
  assert.equal("pdfUrl" in content, false);
});

test("buildOpenCanvasPreview creates a short canvas-oriented lead-in", () => {
  const preview = buildOpenCanvasPreview(`
**Working result**

DIU offers multiple scholarship paths.

- Merit waivers
- Need-based waivers
  `);

  assert.match(preview, /DIU offers multiple scholarship paths/i);
  assert.match(preview, /Merit waivers/i);
});
