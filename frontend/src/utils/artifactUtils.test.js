import test from "node:test";
import assert from "node:assert/strict";

import { normalizeArtifacts, resolveArtifactUrl } from "./artifactUtils.js";

test("resolveArtifactUrl keeps absolute URLs unchanged", () => {
  assert.equal(
    resolveArtifactUrl("https://example.com/file.pdf", "http://127.0.0.1:8765"),
    "https://example.com/file.pdf",
  );
});

test("resolveArtifactUrl prefixes relative URLs with the API base", () => {
  assert.equal(
    resolveArtifactUrl("/api/artifacts/session/report.pdf", "http://127.0.0.1:8765"),
    "http://127.0.0.1:8765/api/artifacts/session/report.pdf",
  );
});

test("normalizeArtifacts drops duplicates and preserves metadata", () => {
  const artifacts = normalizeArtifacts(
    [
      {
        id: "abc",
        label: "PDF brief",
        filename: "report.pdf",
        title: "DIU Planner",
        url: "/api/artifacts/demo/report.pdf",
        mime_type: "application/pdf",
        kind: "document",
        size_bytes: 1280,
      },
      {
        id: "abc",
        label: "PDF brief",
        filename: "report.pdf",
        url: "/api/artifacts/demo/report.pdf",
        mime_type: "application/pdf",
      },
    ],
    "http://127.0.0.1:8765",
  );

  assert.equal(artifacts.length, 1);
  assert.equal(artifacts[0].url, "http://127.0.0.1:8765/api/artifacts/demo/report.pdf");
  assert.equal(artifacts[0].title, "DIU Planner");
  assert.equal(artifacts[0].mimeType, "application/pdf");
  assert.equal(artifacts[0].sizeBytes, 1280);
});
