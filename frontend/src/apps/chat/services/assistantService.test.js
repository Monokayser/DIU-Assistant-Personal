import test from "node:test";
import assert from "node:assert/strict";

import { answerWithBackendStreaming, buildSessionHistory, createCanvasWebsite } from "./assistantService.js";

function buildStreamResponse(lines) {
  const encoder = new TextEncoder();
  return {
    ok: true,
    body: new ReadableStream({
      start(controller) {
        lines.forEach((line) => controller.enqueue(encoder.encode(`${line}\n`)));
        controller.close();
      },
    }),
  };
}

test("buildSessionHistory keeps the first user task when trimming long conversations", () => {
  const messages = [{ role: "user", content: "First task" }];
  for (let index = 1; index <= 105; index += 1) {
    messages.push(
      { role: "assistant", content: `Reply ${index}` },
      { role: "user", content: `Task ${index + 1}` },
    );
  }

  const history = buildSessionHistory(messages);

  assert.equal(history[0].content, "First task");
  assert.equal(history.length, 101);
  assert.equal(history.at(-1).content, "Task 106");
});

test("buildSessionHistory skips malformed or empty messages", () => {
  const history = buildSessionHistory([
    null,
    { role: "system", content: "Ignore me" },
    { role: "user", content: "" },
    { role: "user", content: "Valid user turn" },
    { role: "assistant", content: "Valid assistant turn" },
  ]);

  assert.deepEqual(history, [
    { role: "user", mode: "", content: "Valid user turn" },
    { role: "assistant", mode: "", content: "Valid assistant turn" },
  ]);
});

test("answerWithBackendStreaming omits session history for plain assistant mode", async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];

  globalThis.fetch = async (_url, options = {}) => {
    requests.push(JSON.parse(String(options.body || "{}")));
    return buildStreamResponse([
      JSON.stringify({
        done: true,
        answer: "Plain answer",
        sources: [],
        artifacts: [],
      }),
    ]);
  };

  try {
    const result = await answerWithBackendStreaming({
      prompt: "What is DIU?",
      mode: "assistant",
      sessionId: "demo-session",
      history: [
        { role: "user", content: "Old question" },
        { role: "assistant", content: "Old answer" },
      ],
      directFiles: [],
      onChunk: () => {},
    });

    assert.equal(result.content, "Plain answer");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requests.length, 1);
  assert.deepEqual(requests[0].history, []);
});

test("answerWithBackendStreaming collects streamed chunks and normalizes canvas artifacts", async () => {
  const originalFetch = globalThis.fetch;
  const streamedChunks = [];

  globalThis.fetch = async () => buildStreamResponse([
    JSON.stringify({ chunk: "Hello " }),
    JSON.stringify({ chunk: "world" }),
    JSON.stringify({
      done: true,
      answer: "Hello world",
      sources: [],
      artifacts: [
        {
          id: "canvas-1",
          label: "Canvas",
          filename: "planner.html",
          title: "DIU Planner",
          url: "/api/artifacts/demo/planner.html",
          mime_type: "text/html",
          kind: "workspace",
          size_bytes: 2048,
        },
      ],
    }),
  ]);

  try {
    const result = await answerWithBackendStreaming({
      prompt: "Generate workspace",
      mode: "course",
      sessionId: "canvas-session",
      history: [],
      directFiles: [],
      onChunk: (chunk) => streamedChunks.push(chunk),
    });

    assert.equal(result.content, "Hello world");
    assert.deepEqual(streamedChunks, ["Hello ", "world"]);
    assert.equal(result.artifacts.length, 1);
    assert.equal(result.artifacts[0].title, "DIU Planner");
    assert.match(result.artifacts[0].url, /\/api\/artifacts\/demo\/planner\.html$/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("createCanvasWebsite posts typed canvas request and normalizes artifact", async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];

  globalThis.fetch = async (_url, options = {}) => {
    requests.push(JSON.parse(String(options.body || "{}")));
    return {
      ok: true,
      json: async () => ({
        answer: "Here is your website canvas. Open the canvas to explore it.",
        sources: [],
        artifacts: [
          {
            id: "canvas-site",
            label: "Canvas",
            filename: "site.html",
            title: "DIU Website",
            url: "/api/artifacts/session/site.html",
            mime_type: "text/html",
            kind: "workspace",
            size_bytes: 4096,
          },
        ],
        used_model: true,
        found_match: true,
      }),
    };
  };

  try {
    const result = await createCanvasWebsite({
      sourceContent: "CSE scholarship content",
      mode: "course",
      sessionId: "canvas-session",
    });

    assert.equal(result.artifacts.length, 1);
    assert.equal(result.artifacts[0].title, "DIU Website");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requests.length, 1);
  assert.equal(requests[0].artifact_type, "website");
  assert.equal(requests[0].source_content, "CSE scholarship content");
  assert.equal(requests[0].mode, "course");
  assert.equal(requests[0].session_id, "canvas-session");
});

test("answerWithBackendStreaming retries JSON when the streamed final answer looks truncated", async () => {
  const originalFetch = globalThis.fetch;
  const streamedChunks = [];
  const requests = [];

  globalThis.fetch = async (_url, options = {}) => {
    const body = JSON.parse(String(options.body || "{}"));
    requests.push(body);
    if (body.stream) {
      return buildStreamResponse([
        JSON.stringify({ chunk: "DIU offers several scholarship categories. " }),
        JSON.stringify({
          done: true,
          answer: "DIU offers several scholarship categories. One of the most common benefits is",
          sources: [],
          artifacts: [],
        }),
      ]);
    }
    return {
      ok: true,
      json: async () => ({
        answer: "DIU offers several scholarship categories. One of the most common benefits is a 20% tuition fee waiver for eligible cases.",
        sources: [],
        artifacts: [],
      }),
    };
  };

  try {
    const result = await answerWithBackendStreaming({
      prompt: "What scholarships are available?",
      mode: "assistant",
      sessionId: "retry-session",
      history: [],
      directFiles: [],
      onChunk: (chunk) => streamedChunks.push(chunk),
    });

    assert.equal(result.content, "DIU offers several scholarship categories. One of the most common benefits is a 20% tuition fee waiver for eligible cases.");
    assert.equal(requests.length, 2);
    assert.equal(requests[0].stream, true);
    assert.equal(requests[1].stream, false);
    assert.deepEqual(streamedChunks, ["DIU offers several scholarship categories. "]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
