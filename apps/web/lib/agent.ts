import type { EvidenceSpan, Paragraph, Patch } from "./types";

export type AgentContextScope = "selection" | "paragraph" | "section" | "document";

export const AGENT_CONTEXT_OPTIONS: ReadonlyArray<{ value: AgentContextScope; label: string; description: string }> = [
  { value: "selection", label: "所选片段", description: "默认：仅发送所选内容和所在段落。" },
  { value: "paragraph", label: "当前段落", description: "使用当前段落作为写作上下文。" },
  { value: "section", label: "当前章节", description: "使用当前标题下的章节内容。" },
  { value: "document", label: "整篇文稿", description: "范围最大，必须额外确认。" },
];

export const INITIAL_ONE_CLICK_INSTRUCTION = "Rewrite this passage in natural academic English by removing formulaic, repetitive, or generic phrasing. Preserve the author's exact meaning, topic, position, level of certainty, data, citations, quotations, named entities, abbreviations, and technical terms. Do not add or remove any claim or evidence.";

function occurrenceCount(source: string, target: string): number {
  if (!target) return 0;
  let count = 0;
  let cursor = 0;
  while ((cursor = source.indexOf(target, cursor)) !== -1) {
    count += 1;
    cursor += target.length;
  }
  return count;
}

export function selectInitialRewriteTarget(
  paragraphs: Paragraph[],
  spans: EvidenceSpan[],
  selection: { paragraphId: string; text: string },
): { paragraphId: string; text: string } | null {
  const selectedParagraph = paragraphs.find((paragraph) => paragraph.id === selection.paragraphId);
  const selectedText = selection.text.trim();
  if (selectedParagraph && selectedText && occurrenceCount(selectedParagraph.text, selectedText) === 1) {
    return { paragraphId: selectedParagraph.id, text: selectedText };
  }

  const ranked = [...spans].sort((left, right) => {
    const classDifference = Number(right.classification === "ai_generated") - Number(left.classification === "ai_generated");
    return classDifference || right.score - left.score || (right.end - right.start) - (left.end - left.start);
  });
  for (const span of ranked) {
    const paragraph = paragraphs.find((item) => item.id === span.paragraphId);
    if (!paragraph || span.start < 0 || span.end > paragraph.text.length || span.start >= span.end) continue;
    const text = paragraph.text.slice(span.start, span.end).trim();
    if (text && occurrenceCount(paragraph.text, text) === 1) {
      return { paragraphId: paragraph.id, text };
    }
    return { paragraphId: paragraph.id, text: "" };
  }
  return null;
}

export function buildRewriteMessage(input: {
  instruction: string;
  selection: { paragraphId: string; text: string };
  pendingPatch: Patch | null;
  contextScope: AgentContextScope;
  fullDocumentConfirmed: boolean;
}) {
  const { instruction, selection, pendingPatch, contextScope, fullDocumentConfirmed } = input;
  return {
    instruction,
    paragraph_id: pendingPatch?.paragraphId || selection.paragraphId,
    selected_text: pendingPatch ? "" : selection.text,
    previous_patch_id: pendingPatch?.id || null,
    context_scope: contextScope,
    confirm_full_document_context: contextScope === "document" && fullDocumentConfirmed,
  };
}
