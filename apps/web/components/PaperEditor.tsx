"use client";

import { useLayoutEffect, useRef } from "react";
import type { EvidenceSpan, Paragraph } from "@/lib/types";
import { editableChunks } from "@/lib/text";

type Selection = { paragraphId: string; text: string };
type Props = {
  paragraphs: Paragraph[];
  spans: EvidenceSpan[];
  stale: boolean;
  disabled: boolean;
  onParagraphChange: (paragraphId: string, value: string) => void;
  onSelection: (selection: Selection) => void;
  onRiskSpan: (selection: Selection) => void;
};

function EditableParagraph({ paragraph, index, ...props }: Omit<Props, "paragraphs"> & { paragraph: Paragraph; index: number }) {
  const ref = useRef<HTMLParagraphElement>(null);
  // The browser owns the editable subtree. React must not reconcile evidence
  // children with nodes that typing, paste or native undo already removed.
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element || window.document.activeElement === element) return;
    const nodes = editableChunks(paragraph.text, props.spans.filter(span => span.paragraphId === paragraph.id), false).map(chunk => {
      if (!chunk.classification || props.stale) return window.document.createTextNode(chunk.text);
      const mark = window.document.createElement("mark");
      mark.textContent = chunk.text;
      mark.className = `evidence ${chunk.classification}`;
      mark.tabIndex = 0;
      mark.setAttribute("role", "button");
      mark.title = "发送到写作助手审阅";
      return mark;
    });
    element.replaceChildren(...nodes);
  }, [paragraph.text, paragraph.id, props.spans, props.stale]);

  function input() {
    const element = ref.current!;
    element.querySelectorAll("mark").forEach(mark => mark.replaceWith(...Array.from(mark.childNodes)));
    props.onParagraphChange(paragraph.id, element.innerText);
  }
  function captureSelection() {
    props.onSelection({ paragraphId: paragraph.id, text: window.getSelection()?.toString().trim() || "" });
  }
  const isHeading = paragraph.text.length < 80 && !/[.!?]$/.test(paragraph.text);
  return <p ref={ref} data-paragraph-id={paragraph.id} className={isHeading ? "paper-heading" : "paper-paragraph"}
    contentEditable={!props.disabled} suppressContentEditableWarning spellCheck role="textbox" aria-multiline="true"
    aria-readonly={props.disabled} aria-label={isHeading ? `Heading ${index + 1}` : `Paragraph ${index + 1}`}
    onInput={input} onMouseUp={captureSelection} onKeyUp={event => { if (!(event.target as HTMLElement).closest("mark.evidence")) captureSelection(); }}
    onPaste={event => {
      event.preventDefault();
      window.document.execCommand("insertText", false, event.clipboardData.getData("text/plain"));
      input();
    }}
    onPointerDown={event => {
      const mark = (event.target as HTMLElement).closest("mark.evidence");
      if (mark && !props.disabled) {
        event.preventDefault();
        props.onRiskSpan({ paragraphId: paragraph.id, text: mark.textContent || "" });
      }
    }}
    onKeyDown={event => {
      const mark = (event.target as HTMLElement).closest("mark.evidence");
      if (mark && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        props.onRiskSpan({ paragraphId: paragraph.id, text: mark.textContent || "" });
      }
      if ((event.ctrlKey || event.metaKey) && ["b", "i", "u"].includes(event.key.toLowerCase())) event.preventDefault();
    }} />;
}

export function PaperEditor({ paragraphs, ...props }: Props) {
  return <article className={`paper-page ${props.stale ? "analysis-stale" : ""}`} aria-label="Editable paper">
    {paragraphs.map((paragraph, index) => <EditableParagraph key={paragraph.id} paragraph={paragraph} index={index} {...props} />)}
  </article>;
}
