"use client";

import { Check, ChevronLeft, ChevronRight, Clock3, FileCheck2, RotateCcw, ShieldCheck, Sparkles, X } from "lucide-react";
import type { LegacyDetectionResult, PangramDetectionResult, PaperDocument, Patch, VersionSummary } from "@/lib/types";

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
    ? `演示结果：使用本地固定规则生成，不代表真实 Pangram 结论。${disclaimer}`
    : disclaimer;
}

function LegacyDetectionPanel({ result, stale, onAnalyze }: { result: LegacyDetectionResult; stale: boolean; onAnalyze: () => void }) {
  return <div className="detection-panel legacy-result">
    <div className="metric-heading"><div><span>旧版检测结果</span><small>历史记录只读，不再用于当前版本高亮</small></div><strong>旧版</strong></div>
    <p className="legacy-explanation">此记录来自已停用的旧检测架构。Paperlight 保留历史事实，但不会把旧字符范围映射到新文稿，也不会将其解释为当前 Pangram 风险。</p>
    {typeof result.estimate === "number" ? <div className="legacy-score"><span>历史内部风险信号</span><strong>{result.estimate}%</strong></div> : null}
    {stale ? <div className="stale-notice"><Clock3 size={18} /><div><strong>检测结果已过期</strong><span>当前文稿版本与这条历史记录不同。</span></div></div> : null}
    <button className="button primary wide" onClick={onAnalyze}>使用当前检测器重新检测</button>
    <p className="inspector-disclaimer">{result.disclaimer || "旧版概率性风险记录不能证明作者身份或学术不端。"}</p>
  </div>;
}

function percentage(value: number | null): string {
  return typeof value === "number" ? `${value}%` : "—";
}

function CurrentDetectionPanel({ result, stale, busy, onAnalyze, onTab }: { result: PangramDetectionResult; stale: boolean; busy: boolean; onAnalyze: () => void; onTab: (tab: InspectorTab) => void }) {
  const warnings = result.warnings || [];
  const failed = result.status === "failed";
  const comparison = result.riskComparison;
  return <div className="detection-panel">
    <div className="metric-heading"><div><span>AI 写作风险检测</span><small>{result.isMock ? "演示结果，不代表真实服务" : "Pangram 内部风险信号"}</small></div><strong>{result.isMock ? "演示结果" : "真实 Pangram"}</strong></div>
    {failed ? <div className="detection-alert unavailable"><strong>检测服务不可用</strong><span>{result.error?.message || "本次检测未完成。未保存百分比或高亮。"}</span></div> : null}
    <div className="risk-metrics" aria-label="AI 写作风险分类比例">
      <div><span>AI 生成风险</span><strong>{percentage(result.aiGeneratedPercent)}</strong></div>
      <div><span>AI 辅助风险</span><strong>{percentage(result.aiAssistedPercent)}</strong></div>
      <div><span>人工写作比例</span><strong>{percentage(result.humanPercent)}</strong></div>
      <div className="combined"><span>风险合计</span><strong>{percentage(result.combinedRiskPercent)}</strong><small>生成风险与辅助风险之和</small></div>
    </div>
    {typeof result.combinedRiskPercent === "number" ? <div className="score-scale" aria-label={`AI 生成与 AI 辅助风险合计 ${result.combinedRiskPercent}%`}><span style={{ width: `${Math.max(3, result.combinedRiskPercent)}%` }} /></div> : <div className="score-scale unavailable" aria-label="本次没有可用风险比例" />}
    <div className="evidence-legend"><span><i className="deep" />AI-generated（深蓝）</span><span><i />AI-assisted（浅蓝）</span></div>
    <div className="qualifying-row"><span>{result.qualifyingWords.toLocaleString()} 个有效单词</span><span>{result.spans.length} 个被标记片段</span></div>
    <section className="provider-summary"><div><span>检测器</span><strong>{result.provider}</strong></div><div><span>模型 / 接口版本</span><strong>{result.providerModelVersion || "未返回"}</strong></div><div><span>判断</span><strong>{result.prediction || "未形成"}</strong></div></section>
    {comparison ? <div className={`risk-comparison ${comparison.changePercentagePoints > 0 ? "increased" : ""}`}><span>修改前后风险变化</span><strong>{comparison.beforePercent}% → {comparison.afterPercent}%</strong><small>{comparison.changePercentagePoints > 0 ? "+" : ""}{comparison.changePercentagePoints} 个百分点；如实显示，不代表修改必然降低风险。</small></div> : null}
    {warnings.length ? <section className="detection-warnings"><h3>检测说明</h3><ul>{warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></section> : null}
    {stale ? <div className="stale-notice"><Clock3 size={18} /><div><strong>检测结果已过期</strong><span>文稿在本次检测后发生了修改，旧范围不会继续高亮当前版本。</span><button onClick={onAnalyze}>重新检测当前版本</button></div></div> : null}
    {!failed && !stale && result.spans.length ? <button className="button primary wide" onClick={() => onTab("agent")}>选择蓝色片段进入写作助手</button> : <button className="button primary wide" disabled={busy} onClick={onAnalyze}>{busy ? "正在分析..." : "重新运行 AI 写作风险检测"}</button>}
    <p className="inspector-disclaimer">{mockDisclaimer(result.isMock, result.disclaimer)}</p>
  </div>;
}

function DetectionPanel({ document, busy, onAnalyze, onTab }: Pick<Props, "document" | "busy" | "onAnalyze" | "onTab">) {
  const analysis = document.analysis;
  const result = analysis?.result;
  if (!result) {
    return <div className="empty-inspector"><ShieldCheck size={26} /><span className="eyebrow">AI EVIDENCE</span><h2>当前版本尚未检测</h2><p>运行 AI 写作风险检测，查看 AI 生成风险、AI 辅助风险和可审阅片段。结果不能证明文本作者身份或学术不端。</p><button className="button primary wide" disabled={busy} onClick={onAnalyze}>{busy ? "正在分析..." : "运行 AI 写作风险检测"}</button></div>;
  }
  if (!("aiGeneratedPercent" in result)) {
    return <LegacyDetectionPanel result={result} stale={Boolean(analysis?.isStale)} onAnalyze={onAnalyze} />;
  }
  return <CurrentDetectionPanel result={result} stale={Boolean(analysis?.isStale)} busy={busy} onAnalyze={onAnalyze} onTab={onTab} />;
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
  return <div className="agent-compose"><div className="compose-intro"><Sparkles size={25} /><span className="eyebrow">DEEPSEEK WRITING AGENT</span><h2>由作者控制每一次修改</h2><p>点击蓝色风险片段或在论文中选择文字，再说明你想改进的方向。Agent 只发送所选内容和必要段落上下文，目标是提高具体性、论证质量、作者表达和证据结合度；它只会提出可撤销补丁。</p></div><div className="selection-preview"><strong>当前选中内容</strong><p>{selectedText || "尚未选择文本，将审阅当前活动段落。"}</p></div><label>修改要求<textarea value={instruction} onChange={(event) => onInstruction(event.target.value)} placeholder="例如：让论证更具体，并说明证据如何支持主张，但不要改变原意。" /></label><button className="button primary wide" disabled={busy || instruction.trim().length < 2} onClick={onPropose}>{busy ? "正在准备补丁..." : "生成可审阅补丁"}</button></div>;
}

function VersionsPanel({ document, busy, onRestore }: Pick<Props, "document" | "busy" | "onRestore">) {
  return <div className="versions-panel"><div className="versions-intro"><FileCheck2 size={24} /><span className="eyebrow">VERSION HISTORY</span><h2>不可变版本记录</h2><p>手动保存、接受补丁和恢复操作都会创建新版本，较早文本不会被覆盖。</p></div><div className="version-list">{document.versions.map((version) => <article key={version.id} className={version.id === document.currentVersion.id ? "current" : ""}><div className="version-badge">v{version.number}</div><div><strong>{version.source.replace("-", " ")}</strong><span>{version.wordCount.toLocaleString()} 词 · {new Date(version.createdAt).toLocaleString()}</span></div>{version.id === document.currentVersion.id ? <small>当前</small> : <button disabled={busy} onClick={() => onRestore(version)} title={`恢复版本 ${version.number}`}><RotateCcw size={16} /></button>}</article>)}</div></div>;
}

export function Inspector(props: Props) {
  if (props.collapsed) {
    return <aside className="inspector collapsed"><button className="inspector-expand" onClick={props.onToggleCollapsed} title="展开侧栏"><ChevronLeft size={20} /><span>展开助手</span></button></aside>;
  }
  return <aside className={`inspector inspector-${props.tab}`}><header className="inspector-header"><div><Sparkles size={19} /><strong>{props.tab === "agent" ? "写作助手" : props.tab === "detection" ? "AI 写作风险检测" : "版本记录"}</strong>{props.tab === "agent" ? <span>DeepSeek</span> : null}</div><button onClick={props.onToggleCollapsed} title="收起侧栏"><ChevronRight size={19} /></button></header><nav className="inspector-tabs" aria-label="文稿检查器">{(["agent", "detection", "versions"] as InspectorTab[]).map((tab) => <button key={tab} className={props.tab === tab ? "active" : ""} onClick={() => props.onTab(tab)}>{tab === "agent" ? "写作助手" : tab === "detection" ? "AI 风险" : "版本"}</button>)}</nav><div className="inspector-body">{props.tab === "detection" ? <DetectionPanel {...props} /> : props.tab === "agent" ? <AgentPanel {...props} /> : <VersionsPanel {...props} />}</div></aside>;
}
