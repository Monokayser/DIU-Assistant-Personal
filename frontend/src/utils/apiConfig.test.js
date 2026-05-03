import test from "node:test";
import assert from "node:assert/strict";

import { resolveApiBase } from "./apiConfig.js";

test("resolveApiBase keeps same-origin requests relative", () => {
  assert.equal(
    resolveApiBase("https://example.com", "https://example.com", "example.com"),
    "",
  );
});

test("resolveApiBase blocks dev-only API hosts on public pages", () => {
  assert.equal(
    resolveApiBase("http://127.0.0.1:8765", "https://example.com", "example.com"),
    "",
  );
});

test("resolveApiBase keeps explicit production API origins", () => {
  assert.equal(
    resolveApiBase("https://api.example.com", "https://example.com", "example.com"),
    "https://api.example.com",
  );
});

test("resolveApiBase preserves local development API origins", () => {
  assert.equal(
    resolveApiBase("http://127.0.0.1:8765", "http://localhost:5173", "localhost"),
    "http://127.0.0.1:8765",
  );
});

test("resolveApiBase falls back to the local backend when no explicit API URL is set", () => {
  assert.equal(
    resolveApiBase("", "http://localhost:5173", "localhost"),
    "http://localhost:8765",
  );
});
