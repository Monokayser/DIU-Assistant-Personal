import test from "node:test";
import assert from "node:assert/strict";

import { buildSelectionAwarePrompt, buildSessionAwarePrompt } from "./common.js";

test("buildSessionAwarePrompt keeps normal prompts unchanged", () => {
  assert.equal(
    buildSessionAwarePrompt("Tell me about DIU admission information", [
      { role: "user", content: "Hello" },
    ]),
    "Tell me about DIU admission information",
  );
});

test("buildSessionAwarePrompt expands vague detail followups with session topic", () => {
  const prompt = buildSessionAwarePrompt("more detailed?", [
    { role: "user", content: "Tell me about DIU admission information" },
    { role: "assistant", content: "DIU admission depends on the program and current requirements." },
  ]);

  assert.match(prompt, /Session topic: Tell me about DIU admission information/);
  assert.match(prompt, /Relevant recent context:/);
});

test("buildSessionAwarePrompt expands chart followups with earlier comparison topic", () => {
  const prompt = buildSessionAwarePrompt("chart?", [
    { role: "user", content: "Compare CSE vs software engineering" },
    { role: "assistant", content: "CSE is broader while software engineering focuses more on software lifecycle work." },
  ]);

  assert.match(prompt, /Session topic: Compare CSE vs software engineering/);
  assert.match(prompt, /software lifecycle work/);
});

test("buildSessionAwarePrompt uses the latest substantive user topic instead of the first one", () => {
  const prompt = buildSessionAwarePrompt("more detailed?", [
    { role: "user", content: "Tell me about DIU admission information" },
    { role: "assistant", content: "DIU admission depends on the program." },
    { role: "user", content: "Tell me about DIU scholarship opportunities" },
    { role: "assistant", content: "DIU offers scholarships and waivers." },
  ]);

  assert.match(prompt, /Session topic: Tell me about DIU scholarship opportunities/);
  assert.doesNotMatch(prompt, /Session topic: Tell me about DIU admission information/);
});

test("buildSessionAwarePrompt does not rewrite standalone explicit compare questions", () => {
  assert.equal(
    buildSessionAwarePrompt("compare CSE and SWE", [
      { role: "user", content: "Tell me about DIU admission information" },
      { role: "assistant", content: "DIU admission depends on the program." },
    ]),
    "compare CSE and SWE",
  );
});

test("buildSelectionAwarePrompt rewrites short meaning followups to target selected text", () => {
  const prompt = buildSelectionAwarePrompt("means?", "Accommodation");

  assert.match(prompt, /What does "Accommodation" mean in this DIU context/);
  assert.match(prompt, /not about the word 'mean' or 'means'/);
});

test("buildSelectionAwarePrompt keeps selected text primary for normal selected followups", () => {
  const prompt = buildSelectionAwarePrompt("explain this in more detail", "25 AC buses");

  assert.match(prompt, /"""25 AC buses"""/);
  assert.match(prompt, /Prioritize the selected text/);
});
