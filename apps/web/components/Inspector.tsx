"use client";

import { Check, Clock3, FileCheck2, RefreshCw, RotateCcw, ShieldCheck, Sparkles, X } from "lucide-react";
import type { PaperDocument, Patch, VersionSummary } from "@/lib/types";

export type InspectorTab = "agent" | "detection" | "versions";

type Props = {
  tab: InspectorTab;
  document: PaperDocument;
  selectedText: string;
  pendingPatch: Patch | null;
  instruction: string;
  busy: boolean;
  onTab: (tab: InspectorTab) => void;
  onInstruction: (value: string) => void;
  onAnalyze: () => void;
  onPropose: () => void;
  onAccept: (patch: Patch) => void;
  onReject: (patch: Patch) => void;
  onRestore: (version: VersionSummary) => void;
};

function DetectionPanel({ document, busy, onAnalyze, onTab }: Pick<Props, "document" | "busy" | "onAnalyze" | "onTab">) {
  const analysis = document.analysis;
  const result = analysis?.result;
  if (!result) {
    return <div className="empty-inspector"><ShieldCheck size={28} /><h2>No analysis for this version</h2><p>Run the labeled demo detectors to preview sentence-level evidence. Results are not proof of authorship.</p><button className="button primary wide" disabled={busy} onClick={onAnalyze}>{busy ? "Analyzing…" : "Run demo analysis"}</button></div>;
  }
  const qualityChecks = result.qualityChecks || { duplicateGroups: [], inlineCitationCount: 0, referenceHeadingPresent: false, referenceEntryParagraphs: 0, warnings: ["Run a new analysis to populate document checks."] };
  return (
    <div className="detection-panel">
      <div className="metric-heading"><span>{result.label}</span><small>{result.isMock ? "Demo providers" : "Configured providers"}</small></div>
      <div className="score-row"><strong>{result.estimate < 20 ? "<20" : result.estimate}<em>%</em></strong><div><span>Uncertainty range</span><b>{result.uncertainty.low}–{result.uncertainty.high}%</b></div></div>
      <div className="score-scale" aria-label={`Estimated AI-like text ${result.estimate}%`}><span style={{ width: `${Math.max(3, result.estimate)}%` }} /></div>
      <div className="qualifying-row"><span>{result.qualifyingWords.toLocaleString()} qualifying words</span><span>{result.spans.filter((span) => span.evidence === "consensus").length} consensus passages</span></div>
      <section className="provider-list"><h3>Provider agreement</h3>{result.providers.map((provider) => <div className="provider-row" key={provider.name}><div><strong>{provider.name}</strong><small>{provider.modelVersion}</small></div><span>{provider.estimate}%</span></div>)}</section>
      <section className="quality-checks"><h3>Document checks</h3><div><span>Repeated passage groups</span><strong>{qualityChecks.duplicateGroups.length}</strong></div><div><span>Inline citations detected</span><strong>{qualityChecks.inlineCitationCount}</strong></div><div><span>Reference section</span><strong>{qualityChecks.referenceHeadingPresent ? `${qualityChecks.referenceEntryParagraphs} paragraphs` : "Not found"}</strong></div>{qualityChecks.warnings.length ? <ul>{qualityChecks.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p>No citation-structure warnings.</p>}</section>
      {analysis?.isStale ? <div className="stale-notice"><Clock3 size={18} /><div><strong>Results may be stale.</strong><span>The document changed after this analysis.</span><button onClick={onAnalyze}>Re-analyze current version</button></div></div> : null}
      <button className="button primary wide" onClick={() => onTab("agent")}>Review flagged passages</button>
      <p className="inspector-disclaimer">{result.disclaimer}</p>
    </div>
  );
}

function AgentPanel(props: Pick<Props, "selectedText" | "pendingPatch" | "instruction" | "busy" | "onInstruction" | "onPropose" | "onAccept" | "onReject">) {
  const { selectedText, pendingPatch, instruction, busy, onInstruction, onPropose, onAccept, onReject } = props;
  if (pendingPatch) {
    return <div className="patch-panel"><div className="patch-title"><span className="patch-number">1</span><div><h2>Rewrite suggestion</h2><p>{pendingPatch.isMock ? "Mock Agent · review before accepting" : "Writing Agent · review before accepting"}</p></div></div><label>Original<blockquote>{pendingPatch.originalText}</blockquote></label><label>Suggested<blockquote className="suggested">{pendingPatch.revisedText}</blockquote></label><div className="patch-reason"><strong>Why this change?</strong><p>{pendingPatch.reason}</p></div><div className="protected-row"><ShieldCheck size={18} /><span>{pendingPatch.protectedStatus}</span></div><div className="patch-actions"><button className="button danger-outline" disabled={busy} onClick={() => onReject(pendingPatch)}><X size={17} />Reject</button><button className="button primary" disabled={busy || pendingPatch.originalText === pendingPatch.revisedText} onClick={() => onAccept(pendingPatch)}><Check size={17} />Accept change</button></div></div>;
  }
  return <div className="agent-compose"><div className="compose-intro"><Sparkles size={24} /><h2>Revise with author control</h2><p>Select a passage in the paper, then describe the improvement. The Agent proposes a reversible patch and may not add facts or references.</p></div><div className="selection-preview"><strong>Current selection</strong><p>{selectedText || "No text selected — the active paragraph will be reviewed."}</p></div><label>Instruction<textarea value={instruction} onChange={(event) => onInstruction(event.target.value)} placeholder="Make this passage more specific and less formulaic without changing the claim." /></label><button className="button primary wide" disabled={busy || instruction.trim().length < 2} onClick={onPropose}>{busy ? "Preparing patch…" : "Propose a reviewable patch"}</button></div>;
}

function VersionsPanel({ document, busy, onRestore }: Pick<Props, "document" | "busy" | "onRestore">) {
  return <div className="versions-panel"><div className="versions-intro"><FileCheck2 size={24} /><h2>Immutable versions</h2><p>Manual saves, accepted patches, and restores create a new version. Earlier text is never overwritten.</p></div><div className="version-list">{document.versions.map((version) => <article key={version.id} className={version.id === document.currentVersion.id ? "current" : ""}><div className="version-badge">v{version.number}</div><div><strong>{version.source.replace("-", " ")}</strong><span>{version.wordCount.toLocaleString()} words · {new Date(version.createdAt).toLocaleString()}</span></div>{version.id === document.currentVersion.id ? <small>Current</small> : <button disabled={busy} onClick={() => onRestore(version)} title={`Restore version ${version.number}`}><RotateCcw size={16} /></button>}</article>)}</div></div>;
}

export function Inspector(props: Props) {
  return <aside className={`inspector inspector-${props.tab}`}><nav className="inspector-tabs" aria-label="Document inspector">{(["agent", "detection", "versions"] as InspectorTab[]).map((tab) => <button key={tab} className={props.tab === tab ? "active" : ""} onClick={() => props.onTab(tab)}>{tab === "agent" ? "Writing Agent" : tab === "detection" ? "AI Detection" : "Version History"}</button>)}</nav><div className="inspector-body">{props.tab === "detection" ? <DetectionPanel {...props} /> : props.tab === "agent" ? <AgentPanel {...props} /> : <VersionsPanel {...props} />}</div></aside>;
}
