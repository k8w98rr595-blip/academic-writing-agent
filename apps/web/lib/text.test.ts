import { describe, expect, it } from "vitest";
import { countWords, splitHighlights } from "./text";

describe("text helpers", () => {
  it("splits non-overlapping evidence ranges", () => {
    expect(
      splitHighlights("Alpha beta gamma", [
        { paragraphId: "p1", start: 0, end: 5, score: 0.9, confidence: 0.9, classification: "ai_generated" },
        { paragraphId: "p1", start: 11, end: 16, score: 0.7, confidence: 0.7, classification: "ai_assisted" },
      ]),
    ).toEqual([
      { text: "Alpha", classification: "ai_generated" },
      { text: " beta " },
      { text: "gamma", classification: "ai_assisted" },
    ]);
  });

  it("counts coursework words", () => {
    expect(countWords("One two\nthree")).toBe(3);
  });
});
