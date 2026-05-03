import test from "node:test";
import assert from "node:assert/strict";

import { normalizeSources, sourceDisplayLabel } from "./sourceUtils.js";

test("normalizeSources collapses duplicate visible source domains", () => {
  const sources = normalizeSources([
    {
      title: "daffodilvarsity.edu.bd",
      url: "https://daffodilvarsity.edu.bd/admission",
    },
    {
      title: "daffodilvarsity.edu.bd",
      url: "https://daffodilvarsity.edu.bd/programs",
    },
    {
      title: "www.daffodilvarsity.edu.bd",
      url: "https://www.daffodilvarsity.edu.bd/scholarship",
    },
  ]);

  assert.equal(sources.length, 1);
  assert.equal(sourceDisplayLabel(sources[0]), "daffodilvarsity.edu.bd");
});

test("normalizeSources keeps distinct human-readable source labels", () => {
  const sources = normalizeSources([
    {
      title: "Admission",
      url: "https://daffodilvarsity.edu.bd/admission",
    },
    {
      title: "Programs",
      url: "https://daffodilvarsity.edu.bd/programs",
    },
  ]);

  assert.equal(sources.length, 2);
  assert.deepEqual(sources.map(sourceDisplayLabel), ["Admission", "Programs"]);
});

test("sourceDisplayLabel prefers real source title over Google grounding redirect host", () => {
  const source = {
    title: "daffodilvarsity.edu.bd",
    url: "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc123",
  };

  assert.equal(sourceDisplayLabel(source), "daffodilvarsity.edu.bd");
});
