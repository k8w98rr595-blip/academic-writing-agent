import { describe, expect, it } from "vitest";
import { countWords, splitHighlights } from "./text";

describe("text helpers", () => {
  it("splits non-overlapping evidence ranges", () => {
    expect(
      splitHighlights("Alpha beta gamma", [
        { paragraphId: "p1", start: 0, end: 5, score: 0.9, evidence: "consensus", providers: ["a", "b"] },
        { paragraphId: "p1", start: 11, end: 16, score: 0.7, evidence: "single", providers: ["a"] },
      ]),
    ).toEqual([
      { text: "Alpha", evidence: "consensus" },
      { text: " beta " },
      { text: "gamma", evidence: "single" },
    ]);
  });

  it("counts coursework words", () => {
    expect(countWords("One two\nthree")).toBe(3);
  });
});
