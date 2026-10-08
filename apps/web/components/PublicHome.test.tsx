import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PublicHome } from "./PublicHome";
import { PublicExperience } from "./PublicExperience";

describe("honest public launch boundaries", () => {
  it("keeps unverified cloud registration and real AI closed", () => {
    const html = renderToStaticMarkup(<PublicHome onExperience={() => {}} onLogin={() => {}} />);
    for (const phrase of ["免费本地体验", "学生云端注册暂未开放", "真实模型检测与改写尚未开放", "概率性信号"]) expect(html).toContain(phrase);
    for (const forbidden of ["Turnitin", "100%精准", "保证降低", "Copyleaks"]) expect(html).not.toContain(forbidden);
  });
  it("labels local rules as non-AI and provides explicit export and review controls", () => {
    const html = renderToStaticMarkup(<PublicExperience onBack={() => {}} />);
    for (const phrase of ["没有调用 AI 模型", "不上传", "运行写作自检", "导出当前文本", "生成规则修改示例"]) expect(html).toContain(phrase);
    expect(html).not.toContain("AI 生成风险百分比");
  });
});
