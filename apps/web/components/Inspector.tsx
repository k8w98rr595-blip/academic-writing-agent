"use client";

import { Check, ChevronLeft, ChevronRight, Clock3, FileCheck2, RotateCcw, ShieldCheck, Sparkles, X } from "lucide-react";
import type { PaperDocument, Patch, VersionSummary } from "@/lib/types";

export type InspectorTab = "agent" | "detection" | "versions";

type Props = {
  tab: InspectorTab;
  collapsed: boolean;
  document: PaperDocument;
  selectedText: string;
  pendingPatch: Patch | null;
  instruction: string;
  busy: boolean;
  onToggleCollapsed: () => void;
  onTab: (tab: InspectorTab) => void;
  onInstruction: (value: string) => void;
  onAnalyze: () => void;
  onPropose: () => void;
  onAccept: (patch: Patch) => void;
  onReject: (patch: Patch) => void;
  onRestore: (version: VersionSummary) => void;
};

function mockDisclaimer(isMock: boolean, disclaimer: string): string {
  return isMock
    ? "这是写作模式的概率估算，不是对作者身份或学术不端的证明。"
    : disclaimer;
}

function DetectionPanel({ document, busy, onAnalyze, onTab }: Pick<Props, "document" | "busy" | "onAnalyze" | "onTab">) {
  const analysis = document.analysis;
  const result = analysis?.result;
  if (!result) {
    return <div className="empty-inspector"><ShieldCheck size={26} /><span className="eyebrow">AI EVIDENCE</span><h2>当前版本尚未检测</h2><p>运行带有明确演示标识的检测器，查看句子级证据。结果不能证明文本作者身份。</p><button className="button primary wide" disabled={busy} onClick={onAnalyze}>{busy ? "正在分析..." : "运行演示检测"}</button></div>;
  }
  const qualityChecks = result.qualityChecks || { duplicateGroups: [], inlineCitationCount: 0, referenceHeadingPresent: false, referenceEntryParagraphs: 0, warnings: ["重新检测后可生成文稿结构检查。"] };
  const consensusCount = result.spans.filter((span) => span.evidence === "consensus").length;
  return (
    <div className="detection-panel">
      <div className="metric-heading"><div><span>AI 痕迹检测</span><small>{result.isMock ? "演示检测，不代表真实服务" : "已配置检测提供方"}</small></div><strong>{result.isMock ? "演示" : result.label}</strong></div>
      <div className="score-row"><div><span>估算比例</span><strong>{result.estimate < 20 ? "<20" : result.estimate}<em>%</em></strong></div><div><span>不确定性范围</span><b>{result.uncertainty.low}% 至 {result.uncertainty.high}%</b></div></div>
      <div className="score-scale" aria-label={`估算 AI 痕迹比例 ${result.estimate}%`}><span style={{ width: `${Math.max(3, result.estimate)}%` }} /></div>
      <div className="evidence-legend"><span><i className="deep" />高一致性证据</span><span><i />单提供方证据</span></div>
      <div className="qualifying-row"><span>{result.qualifyingWords.toLocaleString()} 个有效单词</span><span>{consensusCount} 处一致命中</span></div>
      <section className="provider-list"><h3>提供方一致性</h3>{result.providers.map((provider) => <div className="provider-row" key={provider.name}><div><strong>{provider.name}</strong><small>{provider.modelVersion}</small></div><span>{provider.estimate}%</span></div>)}</section>
      <section className="quality-checks"><h3>文稿结构检查</h3><div><span>重复段落组</span><strong>{qualityChecks.duplicateGroups.length}</strong></div><div><span>文内引用</span><strong>{qualityChecks.inlineCitationCount}</strong></div><div><span>参考文献章节</span><strong>{qualityChecks.referenceHeadingPresent ? `${qualityChecks.referenceEntryParagraphs} 个段落` : "未找到"}</strong></div>{qualityChecks.warnings.length ? <ul>{qualityChecks.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul> : <p>未发现引用结构提醒。</p>}</section>
      {analysis?.isStale ? <div className="stale-notice"><Clock3 size={18} /><div><strong>检测结果已过期</strong><span>文稿在本次检测后发生了修改。</span><button onClick={onAnalyze}>重新检测当前版本</button></div></div> : null}
      <button className="button primary wide" onClick={() => onTab("agent")}>审阅被标记的段落</button>
      <p className="inspector-disclaimer">{mockDisclaimer(result.isMock, result.disclaimer)}</p>
    </div>
  );
}

function AgentPanel(props: Pick<Props, "selectedText" | "pendingPatch" | "instruction" | "busy" | "onInstruction" | "onPropose" | "onAccept" | "onReject">) {
  const { selectedText, pendingPatch, instruction, busy, onInstruction, onPropose, onAccept, onReject } = props;
  if (pendingPatch) {
    const providerLabel = pendingPatch.isMock
      ? "Mock Agent，接受前请人工审阅"
      : `${pendingPatch.provider || "Writing Agent"} ${pendingPatch.modelVersion || ""}`.trim();
    const validatorLabel = pendingPatch.validatorModelVersion
      ? `${pendingPatch.validatorModelVersion} 已完成语义安全校验`
      : pendingPatch.protectedStatus;
    return <div className="patch-panel"><div className="patch-title"><div><span className="eyebrow">REVIEWABLE PATCH</span><h2>建议修改</h2><p>{providerLabel}</p></div></div><section className="patch-comparison"><label>原文<blockquote>{pendingPatch.originalText}</blockquote></label><span className="patch-arrow">→</span><label>建议稿<blockquote className="suggested">{pendingPatch.revisedText}</blockquote></label></section><details className="patch-reason"><summary>修改说明</summary><p>{pendingPatch.reason}</p></details><div className="protected-row"><ShieldCheck size={18} /><span>{validatorLabel}</span></div><div className="patch-actions"><button className="button secondary" disabled={busy} onClick={() => onReject(pendingPatch)}><X size={17} />保留原文</button><button className="button primary" disabled={busy || pendingPatch.originalText === pendingPatch.revisedText} onClick={() => onAccept(pendingPatch)}><Check size={17} />接受此修改</button></div></div>;
  }
  return <div className="agent-compose"><div className="compose-intro"><Sparkles size={25} /><span className="eyebrow">DEEPSEEK WRITING AGENT</span><h2>由作者控制每一次修改</h2><p>在论文中选择一段文字，再说明你想改进的方向。Agent 只会提出可撤销补丁，不会擅自添加事实或参考文献。</p></div><div className="selection-preview"><strong>当前选中内容</strong><p>{selectedText || "尚未选择文本，将审阅当前活动段落。"}</p></div><label>修改要求<textarea value={instruction} onChange={(event) => onInstruction(event.target.value)} placeholder="例如：让这段表达更具体，减少模板化语气，但不要改变原意。" /></label><button className="button primary wide" disabled={busy || instruction.trim().length < 2} onClick={onPropose}>{busy ? "正在准备补丁..." : "生成可审阅补丁"}</button></div>;
}

function VersionsPanel({ document, busy, onRestore }: Pick<Props, "document" | "busy" | "onRestore">) {
  return <div className="versions-panel"><div className="versions-intro"><FileCheck2 size={24} /><span className="eyebrow">VERSION HISTORY</span><h2>不可变版本记录</h2><p>手动保存、接受补丁和恢复操作都会创建新版本，较早文本不会被覆盖。</p></div><div className="version-list">{document.versions.map((version) => <article key={version.id} className={version.id === document.currentVersion.id ? "current" : ""}><div className="version-badge">v{version.number}</div><div><strong>{version.source.replace("-", " ")}</strong><span>{version.wordCount.toLocaleString()} 词 · {new Date(version.createdAt).toLocaleString()}</span></div>{version.id === document.currentVersion.id ? <small>当前</small> : <button disabled={busy} onClick={() => onRestore(version)} title={`恢复版本 ${version.number}`}><RotateCcw size={16} /></button>}</article>)}</div></div>;
}

export function Inspector(props: Props) {
  if (props.collapsed) {
    return <aside className="inspector collapsed"><button className="inspector-expand" onClick={props.onToggleCollapsed} title="展开侧栏"><ChevronLeft size={20} /><span>展开助手</span></button></aside>;
  }
  return <aside className={`inspector inspector-${props.tab}`}><header className="inspector-header"><div><Sparkles size={19} /><strong>{props.tab === "agent" ? "写作助手" : props.tab === "detection" ? "AI 检测" : "版本记录"}</strong>{props.tab === "agent" ? <span>DeepSeek</span> : null}</div><button onClick={props.onToggleCollapsed} title="收起侧栏"><ChevronRight size={19} /></button></header><nav className="inspector-tabs" aria-label="文稿检查器">{(["agent", "detection", "versions"] as InspectorTab[]).map((tab) => <button key={tab} className={props.tab === tab ? "active" : ""} onClick={() => props.onTab(tab)}>{tab === "agent" ? "写作助手" : tab === "detection" ? "AI 检测" : "版本"}</button>)}</nav><div className="inspector-body">{props.tab === "detection" ? <DetectionPanel {...props} /> : props.tab === "agent" ? <AgentPanel {...props} /> : <VersionsPanel {...props} />}</div></aside>;
}
