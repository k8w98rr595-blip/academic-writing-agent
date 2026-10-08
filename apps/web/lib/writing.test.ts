import { describe, expect, it } from "vitest";
import { textMetrics } from "./text";
import { acceptLocalProposal, CHINESE_SAMPLE, localProposal, writingReview } from "./writing";

describe("local writing experience", () => {
  it("matches server Chinese counting boundaries", () => {
    expect(textMetrics("中".repeat(500) + "AI 2026 don't")).toMatchObject({ language: "zh", count: 503, unit: "字/词", valid: true });
    expect(textMetrics("中".repeat(499)).valid).toBe(false);
    expect(textMetrics("中".repeat(12001)).valid).toBe(false);
    expect(textMetrics("短文2026年")).toMatchObject({ language: "zh", count: 4 });
  });
  it("reviews duplicate text and unsupported research assertions without inventing AI scores", () => {
    const result = writingReview("研究表明，工具是有帮助的。\n\n研究表明，工具是有帮助的。");
    expect(result.notes.join(" ")).toContain("重复");
    expect(result.notes.join(" ")).toContain("核对来源");
    expect(result).not.toHaveProperty("aiGeneratedPercent");
  });
  it("preserves numbers, citations and URLs in rule-based edits", () => {
    const text = "值得注意的是，2026年有30份样本[1]，来源https://example.com。";
    const proposal = localProposal(text)!;
    expect(acceptLocalProposal(text, proposal)).toBe("需要注意，2026年有30份样本[1]，来源https://example.com。");
    expect(text).toContain("值得注意的是");
  });
  it("rejects an outdated proposal", () => {
    const proposal = localProposal(CHINESE_SAMPLE)!;
    expect(() => acceptLocalProposal(CHINESE_SAMPLE + "新内容", proposal)).toThrow("文稿已修改");
  });
  it("does not rewrite quoted prefixes or fabricate unmatched proposals", () => {
    expect(localProposal("“值得注意的是，原引文不能修改。”")).toBeNull();
    expect(localProposal("没有规则命中的合成正文。")).toBeNull();
  });
});
