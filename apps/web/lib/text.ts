import type { EvidenceSpan, Paragraph } from "./types";

export type HighlightChunk = { text: string; evidence?: "consensus" | "single" };

export function splitHighlights(text: string, spans: EvidenceSpan[]): HighlightChunk[] {
  const normalized = spans
    .filter((span) => span.start >= 0 && span.end > span.start && span.end <= text.length)
    .toSorted((left, right) => left.start - right.start || left.end - right.end);
  const chunks: HighlightChunk[] = [];
  let cursor = 0;
  for (const span of normalized) {
    if (span.start < cursor) continue;
    if (span.start > cursor) chunks.push({ text: text.slice(cursor, span.start) });
    chunks.push({ text: text.slice(span.start, span.end), evidence: span.evidence });
    cursor = span.end;
  }
  if (cursor < text.length) chunks.push({ text: text.slice(cursor) });
  return chunks.length ? chunks : [{ text }];
}

export function countWords(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

export function documentText(paragraphs: Paragraph[]): string {
  return paragraphs.map((paragraph) => paragraph.text.trim()).filter(Boolean).join("\n\n");
}

export function makeDemoPaper(): string {
  const sections = [
    ["Introduction", "The reuse of data has become central to modern research across disciplines. It accelerates discovery, improves reproducibility, and reduces redundant collection efforts. It is important to note that these benefits do not remove the ethical obligations attached to consent, privacy, and fair governance."],
    ["Understanding data reuse", "Data reuse refers to the use of information collected for one purpose in a later project with a different analytical question. Moreover, researchers may combine records from several sources, which can create insights that were not possible when each source was examined alone."],
    ["Consent and autonomy", "Meaningful consent requires people to understand how their information may be used now and in the future. Studies have shown that broad consent can be interpreted differently by participants and institutions. Researchers should therefore explain realistic secondary uses and provide proportionate choices when circumstances change."],
    ["Privacy and anonymity", "Removing direct identifiers reduces risk but does not guarantee anonymity. A large number of attributes can still identify a person when datasets are linked. Technical controls, governance, and limited access all have a direct role in reducing the possibility of re-identification."],
    ["Justice and fairness", "Data that appear representative may reproduce earlier exclusions. Furthermore, automated analysis can distribute benefits and harms unevenly when a dataset underrepresents particular communities. Ethical review should examine who contributes data, who receives value, and who carries residual risk."],
    ["Governance", "Institutions need documented purposes, access controls, retention limits, and procedures for responding to participant concerns. These safeguards should be reviewed throughout a project rather than treated as a one-time administrative exercise."],
    ["Conclusion", "In conclusion, data reuse is neither inherently ethical nor inherently harmful. Its legitimacy depends on purpose, proportionality, transparency, and continuing accountability. A defensible project makes these judgments visible and allows affected people to question them."],
  ];
  const body = sections.map(([heading, paragraph]) => `${heading}\n\n${paragraph}`).join("\n\n");
  const expansion = Array.from({ length: 7 }, (_, index) =>
    `Case reflection ${index + 1}\n\nA practical review should connect general principles to the specific dataset, institutional setting, and people who may be affected. Researchers can document the original collection context, identify new analytical purposes, test whether less intrusive information would answer the question, and record the reasons for retaining each field. This process makes ethical reasoning open to challenge and reduces reliance on vague assurances. It also helps reviewers distinguish a justified secondary use from a convenient but poorly governed one.`,
  ).join("\n\n");
  return `${body}\n\n${expansion}`;
}
