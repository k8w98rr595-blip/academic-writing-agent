"use client";

import { ClipboardEvent, FocusEvent, KeyboardEvent, MouseEvent, useState } from "react";
import type { EvidenceSpan, Paragraph } from "@/lib/types";
import { editableChunks } from "@/lib/text";

type Selection = { paragraphId: string; text: string };

type Props = {
  paragraphs: Paragraph[];
  spans: EvidenceSpan[];
  stale: boolean;
  onDirty: () => void;
  onParagraphBlur: (paragraphId: string, value: string) => void;
  onSelection: (selection: Selection) => void;
  onRiskSpan: (selection: Selection) => void;
};

export function PaperEditor({ paragraphs, spans, stale, onDirty, onParagraphBlur, onSelection, onRiskSpan }: Props) {
  const [editingParagraphId, setEditingParagraphId] = useState<string | null>(null);

  function captureSelection(event: MouseEvent<HTMLElement> | KeyboardEvent<HTMLElement>) {
    const selection = window.getSelection();
    const target = event.currentTarget;
    onSelection({ paragraphId: target.dataset.paragraphId || "", text: selection?.toString().trim() || "" });
  }

  function pastePlain(event: ClipboardEvent<HTMLElement>) {
    event.preventDefault();
    document.execCommand("insertText", false, event.clipboardData.getData("text/plain"));
  }

  return (
    <article className={`paper-page ${stale ? "analysis-stale" : ""}`} aria-label="Editable paper">
      {paragraphs.map((paragraph, index) => {
        const paragraphSpans = spans.filter((span) => span.paragraphId === paragraph.id);
        const isHeading = paragraph.text.length < 80 && !/[.!?]$/.test(paragraph.text);
        // Evidence marks are React-managed children. Browsers mutate a contentEditable
        // subtree directly while the author types, so keep the active paragraph as one
        // plain text node until blur; otherwise React can reconcile against nodes that
        // the browser has already removed and crash the workspace.
        const chunks = editableChunks(paragraph.text, paragraphSpans, editingParagraphId === paragraph.id);
        return (
          <p
            key={paragraph.id}
            className={isHeading ? "paper-heading" : "paper-paragraph"}
            data-paragraph-id={paragraph.id}
            contentEditable
            suppressContentEditableWarning
            spellCheck
            role="textbox"
            aria-multiline="true"
            aria-label={isHeading ? `Heading ${index + 1}` : `Paragraph ${index + 1}`}
            onFocus={(event: FocusEvent<HTMLElement>) => {
              if (event.target === event.currentTarget) setEditingParagraphId(paragraph.id);
            }}
            onInput={onDirty}
            onBlur={(event: FocusEvent<HTMLElement>) => {
              if (event.target !== event.currentTarget) return;
              const value = event.currentTarget.innerText.trim();
              setEditingParagraphId(null);
              onParagraphBlur(paragraph.id, value);
            }}
            onPointerDownCapture={(event) => {
              const evidence = (event.target as HTMLElement).closest("mark.evidence");
              if (!evidence || !event.currentTarget.contains(evidence)) return;
              event.preventDefault();
              event.stopPropagation();
              onRiskSpan({ paragraphId: paragraph.id, text: evidence.textContent?.trim() || "" });
            }}
            onClickCapture={(event) => {
              const evidence = (event.target as HTMLElement).closest("mark.evidence");
              if (!evidence || !event.currentTarget.contains(evidence)) return;
              event.preventDefault();
              event.stopPropagation();
              onRiskSpan({ paragraphId: paragraph.id, text: evidence.textContent?.trim() || "" });
            }}
            onMouseUp={captureSelection}
            onKeyUp={captureSelection}
            onPaste={pastePlain}
          >
            {chunks.map((chunk, chunkIndex) => chunk.classification ? <mark
              key={`${paragraph.id}-${chunkIndex}`}
              className={`evidence ${chunk.classification}`}
              role="button"
              tabIndex={0}
              title="发送到写作助手审阅"
              onClick={(event) => event.stopPropagation()}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  event.stopPropagation();
                  onRiskSpan({ paragraphId: paragraph.id, text: chunk.text });
                }
              }}
              onKeyUp={(event) => event.stopPropagation()}
            >{chunk.text}</mark> : chunk.text)}
          </p>
        );
      })}
    </article>
  );
}
