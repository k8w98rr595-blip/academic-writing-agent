import { describe, expect, it } from "vitest";
import { buildRewriteMessage, selectInitialRewriteParagraphs } from "./agent";
import type { Patch } from "./types";

const pendingPatch: Patch = {
  id: "patch_1",
  baseVersionId: "version_1",
  paragraphId: "paragraph_2",
  originalText: "Original passage.",
  revisedText: "Current candidate.",
  reason: "Improved clarity.",
  protectedStatus: "preserved",
  status: "pending",
  rewriteSessionId: "rewrite_1",
  revisionNumber: 1,
};

describe("buildRewriteMessage", () => {
  it("sends a first-turn selection with the requested context", () => {
    expect(buildRewriteMessage({
      instruction: "Make the reasoning more specific.",
      selection: { paragraphId: "paragraph_1", text: "Selected passage." },
      pendingPatch: null,
      contextScope: "section",
      fullDocumentConfirmed: false,
    })).toEqual({
      instruction: "Make the reasoning more specific.",
      paragraph_id: "paragraph_1",
      selected_text: "Selected passage.",
      previous_patch_id: null,
      context_scope: "section",
      confirm_full_document_context: false,
    });
  });

  it("refines the pending patch without trusting a changed browser selection", () => {
    expect(buildRewriteMessage({
      instruction: "Make the current suggestion shorter.",
      selection: { paragraphId: "attacker_paragraph", text: "Unrelated browser selection." },
      pendingPatch,
      contextScope: "document",
      fullDocumentConfirmed: true,
    })).toMatchObject({
      paragraph_id: "paragraph_2",
      selected_text: "",
      previous_patch_id: "patch_1",
      context_scope: "document",
      confirm_full_document_context: true,
    });
  });
});

describe("selectInitialRewriteParagraphs", () => {
  const paragraphs = [
    { id: "paragraph_1", text: "A repeated claim appears. A repeated claim appears." },
    { id: "paragraph_2", text: "It is important to note that the evidence supports the claim." },
  ];

  it("returns every marked paragraph once in document order", () => {
    expect(selectInitialRewriteParagraphs(paragraphs, [
      { paragraphId: "paragraph_1", start: 0, end: 24, classification: "ai_assisted", score: 0.9, confidence: 0.9 },
      { paragraphId: "paragraph_2", start: 0, end: 35, classification: "ai_generated", score: 0.7, confidence: 0.7 },
      { paragraphId: "paragraph_2", start: 36, end: 45, classification: "ai_assisted", score: 0.6, confidence: 0.6 },
    ])).toEqual(paragraphs);
  });

  it("ignores invalid and unknown ranges", () => {
    expect(selectInitialRewriteParagraphs(paragraphs, [
      { paragraphId: "paragraph_1", start: 4, end: 4, classification: "ai_generated", score: 0.9, confidence: 0.9 },
      { paragraphId: "missing", start: 0, end: 5, classification: "ai_generated", score: 0.9, confidence: 0.9 },
    ])).toEqual([]);
  });
});
