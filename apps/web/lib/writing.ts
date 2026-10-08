import { textMetrics } from "./text";

export const CHINESE_SAMPLE = `大学生如何负责任地使用写作工具

值得注意的是，写作工具可以帮助作者检查表达，但不能替代作者对事实和论证的判断。本文讨论课程论文中的使用边界，并提出一种保留修改过程的工作方式。

首先，作者应先提出研究问题，再选择与问题有关的材料。工具可以提示句子过长或段落衔接不足，但证据是否支持结论，仍需回到原始材料核验。

其次，修改应保留数据、引用和原有的确定程度。以2026年的合成案例为例，若样本只有30份，就不能将结果描述为适用于全部大学生。这个案例仅供功能演示，不是真实研究发现。

综上所述，清晰的表达、可靠的证据和可追溯的修改过程应共同构成写作质量。作者需要审阅每项建议，并遵守课程要求。`;

export function writingReview(text: string) {
  const paragraphs = text.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean);
  const sentences = text.split(/[。！？.!?]+/).map(s => s.trim()).filter(Boolean);
  const long = sentences.filter(s => textMetrics(s).count > (/[\u3400-\u9fff]/.test(s) ? 90 : 45)).length;
  const duplicate = paragraphs.length - new Set(paragraphs).size;
  const notes: string[] = [];
  if (long) notes.push(`发现 ${long} 个较长句子，可检查能否拆分论点和解释。`);
  if (duplicate) notes.push(`发现 ${duplicate} 段完全重复的文本，请检查是否粘贴重复。`);
  if (/(研究表明|调查显示|studies show|research shows)/i.test(text) && !/(\[\d+\]|\(.*\d{4}.*\)|（.*\d{4}.*）)/.test(text)) notes.push("文稿提到研究或调查，请人工核对来源与引用。此提示不能判断引用是否真实。");
  if (paragraphs.length < 3) notes.push("可以检查问题、证据与结论是否分段表达。短文本也可能无需更多段落。");
  if (!notes.length) notes.push("未发现这些基础规则能提示的问题，请继续人工检查事实、引用和论证。");
  return { metrics: textMetrics(text), paragraphs: paragraphs.length, sentences: sentences.length, notes };
}

export function localProposal(text: string): { source: string; index: number; original: string; revised: string } | null {
  const parts = text.split(/\n\s*\n/);
  for (let index = 0; index < parts.length; index++) {
    const original = parts[index];
    const revised = original.replace(/^值得注意的是[，,]?/, "需要注意，").replace(/^综上所述[，,]?/, "综合以上分析，");
    if (original !== revised) return { source: text, index, original, revised };
  }
  return null;
}

export function acceptLocalProposal(text: string, proposal: NonNullable<ReturnType<typeof localProposal>>): string {
  if (text !== proposal.source) throw new Error("文稿已修改，请重新生成建议");
  const parts = text.split(/\n\s*\n/);
  if (parts[proposal.index] !== proposal.original) throw new Error("原文已变化");
  parts[proposal.index] = proposal.revised;
  return parts.join("\n\n");
}
