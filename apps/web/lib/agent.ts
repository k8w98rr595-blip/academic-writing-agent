import type { Patch } from "./types";

export type AgentContextScope = "selection" | "paragraph" | "section" | "document";

export const AGENT_CONTEXT_OPTIONS: ReadonlyArray<{ value: AgentContextScope; label: string; description: string }> = [
  { value: "selection", label: "所选片段", description: "默认：仅发送所选内容和所在段落。" },
  { value: "paragraph", label: "当前段落", description: "使用当前段落作为写作上下文。" },
  { value: "section", label: "当前章节", description: "使用当前标题下的章节内容。" },
  { value: "document", label: "整篇文稿", description: "范围最大，必须额外确认。" },
];

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
