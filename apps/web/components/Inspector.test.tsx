import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Inspector } from "./Inspector";
import type { PaperDocument, Patch } from "@/lib/types";

const noop = () => {};
const document: PaperDocument = {
  id: "doc_test", title: "Synthetic test", patches: [], analysis: null, versions: [],
  createdAt: "2026-09-06T00:00:00", updatedAt: "2026-09-06T00:00:00", expiresAt: "2026-09-13T00:00:00",
  currentVersion: { id: "version_test", number: 1, paragraphs: [], wordCount: 800, source: "text", createdAt: "2026-09-06T00:00:00" },
};
const patch: Patch = { id: "patch_test", baseVersionId: "version_test", paragraphId: "p_test",
  originalText: "Original test evidence.", revisedText: "Revised test evidence.", reason: "Clarity.",
  protectedStatus: "preserved", status: "pending", batch: true, rewriteSessionId: "rewrite_test", isMock: true };
function render(overrides: Partial<React.ComponentProps<typeof Inspector>> = {}) {
  return renderToStaticMarkup(<Inspector tab="agent" collapsed={false} document={document} selectedText="" pendingPatch={null}
    batchPatches={[]} onBatchDecision={noop} instruction="Improve clarity" contextScope="selection" fullDocumentConfirmed={false}
    initialOneClickAvailable={false} initialOneClickTargetText="" busy={false} onToggleCollapsed={noop} onTab={noop}
    onInstruction={noop} onContextScope={noop} onFullDocumentConfirmed={noop} onAnalyze={noop} onInitialOneClick={noop}
    onPropose={noop} onAccept={noop} onReject={noop} onRestore={noop} {...overrides} />);
}

describe("author-controlled batch preview", () => {
  it("labels Mock preview, originals and explicit acceptance", () => {
    const html = render({ batchPatches: [patch] });
    for (const text of ["批量修改预览", "演示结果 · Mock 建议", "正文尚未改变", patch.originalText, patch.revisedText, "接受所选 1 项并保存", "整批保留原文"]) expect(html).toContain(text);
  });
  it("does not mislabel real-provider fixtures as Mock", () => {
    const html = render({ batchPatches: [{ ...patch, isMock: false, provider: "DeepSeek" }] });
    expect(html).toContain("写作建议 · 请人工审阅");
    expect(html).not.toContain("演示结果 · Mock 建议");
  });
  it("shows a keyboard-operable checkbox per paragraph", () => {
    expect(render({ batchPatches: [patch, { ...patch, id: "patch_second" }] }).match(/type="checkbox"/g)).toHaveLength(2);
  });
  it("disables batch decisions while a request is running", () => {
    expect(render({ batchPatches: [patch], busy: true }).match(/disabled=""/g)?.length).toBeGreaterThanOrEqual(3);
  });
  it("offers preview without a direct-application promise", () => {
    const html = render({ initialOneClickAvailable: true });
    expect(html).toContain("预览风险段落修改");
    expect(html).toContain("真实和 Mock 模式都先生成可审阅预览");
    expect(html).not.toContain("点击即接受");
    expect(html).not.toContain("一键降低");
  });
  it("escapes provider text in the preview", () => {
    const html = render({ batchPatches: [{ ...patch, revisedText: '<img src=x onerror="alert(1)">' }] });
    expect(html).toContain("&lt;img");
    expect(html).not.toContain("<img");
  });
});
