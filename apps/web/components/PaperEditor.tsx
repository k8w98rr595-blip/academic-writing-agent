"use client";

import { ClipboardEvent, FocusEvent, KeyboardEvent, MouseEvent } from "react";
import type { EvidenceSpan, Paragraph } from "@/lib/types";
import { splitHighlights } from "@/lib/text";

type Selection = { paragraphId: string; text: string };

type Props = {
  paragraphs: Paragraph[];
  spans: EvidenceSpan[];
  stale: boolean;
  onDirty: () => void;
  onParagraphBlur: (paragraphId: string, value: string) => void;
  onSelection: (selection: Selection) => void;
};

export function PaperEditor({ paragraphs, spans, stale, onDirty, onParagraphBlur, onSelection }: Props) {
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
        const chunks = splitHighlights(paragraph.text, paragraphSpans);
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
            onInput={onDirty}
            onBlur={(event: FocusEvent<HTMLElement>) => onParagraphBlur(paragraph.id, event.currentTarget.innerText.trim())}
            onMouseUp={captureSelection}
            onKeyUp={captureSelection}
            onPaste={pastePlain}
          >
            {chunks.map((chunk, chunkIndex) => chunk.evidence ? <mark key={`${paragraph.id}-${chunkIndex}`} className={`evidence ${chunk.evidence}`}>{chunk.text}</mark> : chunk.text)}
          </p>
        );
      })}
    </article>
  );
}
