"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, CreditCard, Download, FileClock, FileText, History, ListTree, LogOut, Plus, Redo2, Save, ShieldCheck, Sparkles, Trash2, Undo2 } from "lucide-react";
import { api, downloadExport, isQuotaError, withIdempotency } from "@/lib/api";
import { buildRewriteMessage, selectInitialRewriteParagraphs, type AgentContextScope } from "@/lib/agent";
import type { DocumentListItem, EvidenceSpan, PaperDocument, Paragraph, Patch, VersionSummary } from "@/lib/types";
import { Inspector, type InspectorTab } from "./Inspector";
import { PaperEditor } from "./PaperEditor";
import { ActionDialog } from "./ActionDialog";

type Props = {
  document: PaperDocument;
  documents: DocumentListItem[];
  onDocumentChange: (document: PaperDocument) => void;
  onRefresh: () => void;
  onOpen: (id: string) => void;
  onNew: () => void;
  onDeleted: () => void;
  onBilling: () => void;
  onLogout: () => void;
};

type Navigation = { kind: "open"; id: string } | { kind: "new" } | { kind: "logout" } | { kind: "billing" } | { kind: "restore"; version: VersionSummary };

type Confirmation =
  | { kind: "unsaved"; action: Navigation }
  | { kind: "delete" }
  | { kind: "restore"; version: VersionSummary };

export function Workspace(props: Props) {
  const { document, documents, onDocumentChange, onOpen, onNew, onDeleted, onBilling, onLogout } = props;
  const [paragraphs, setParagraphs] = useState<Paragraph[]>(document.currentVersion.paragraphs);
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState<InspectorTab>(document.analysis ? "detection" : "agent");
  const [selection, setSelection] = useState({ paragraphId: paragraphs[0]?.id || "", text: "" });
  const [instruction, setInstruction] = useState("Make this passage more specific, strengthen its reasoning, and connect evidence to the claim without changing its meaning.");
  const [rewriteSessionId, setRewriteSessionId] = useState(() => document.patches.find((patch) => patch.status === "pending")?.rewriteSessionId || "");
  const [pendingPatch, setPendingPatch] = useState<Patch | null>(() => document.patches.find((patch) => patch.status === "pending" && !patch.batch && patch.baseVersionId === document.currentVersion.id) || null);
  const [contextScope, setContextScope] = useState<AgentContextScope>("selection");
  const [fullDocumentConfirmed, setFullDocumentConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const requestKeys = useRef(new Map<string, string>());
  const draft = useRef(paragraphs);
  const dirtyRef = useRef(false);
  const working = useRef(false);
  const mobileMenu = useRef<HTMLDetailsElement>(null);
  const batchPatches = document.patches.filter(patch => patch.batch && patch.status === "pending" && patch.baseVersionId === document.currentVersion.id);
  const batchSessionId = batchPatches[0]?.rewriteSessionId;
  const activeBatch = batchPatches.filter(patch => patch.rewriteSessionId === batchSessionId)
    .sort((left, right) => paragraphs.findIndex(p => p.id === left.paragraphId) - paragraphs.findIndex(p => p.id === right.paragraphId));

  function requestKey(operation: string): string {
    const existing = requestKeys.current.get(operation);
    if (existing) return existing;
    const created = globalThis.crypto.randomUUID();
    requestKeys.current.set(operation, created);
    return created;
  }

  function completeRequest(operation: string): void {
    requestKeys.current.delete(operation);
  }
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const stale = dirty || Boolean(document.analysis?.isStale);
  const detectionResult = document.analysis?.result;
  const spans: EvidenceSpan[] = !stale && detectionResult && "aiGeneratedPercent" in detectionResult
    ? detectionResult.spans
    : [];
  const initialOneClickParagraphs = useMemo(
    () => selectInitialRewriteParagraphs(paragraphs, spans),
    [paragraphs, spans],
  );
  const initialOneClickAvailable = Boolean(
    initialOneClickParagraphs.length
    && !dirty
    && !pendingPatch
    && !activeBatch.length
    && document.analysis
    && !document.analysis.isStale
    && detectionResult
    && "aiGeneratedPercent" in detectionResult
    && detectionResult.status === "success",
  );
  const initialOneClickTargetText = initialOneClickParagraphs.length
    ? `将一次处理本轮检测标记的 ${initialOneClickParagraphs.length} 个风险段落。`
    : "";

  useEffect(() => {
    draft.current = document.currentVersion.paragraphs;
    dirtyRef.current = false;
    setParagraphs(document.currentVersion.paragraphs);
    setDirty(false);
    setSelection({ paragraphId: document.currentVersion.paragraphs[0]?.id || "", text: "" });
    const currentPendingPatch = document.patches.find((patch) => patch.status === "pending" && !patch.batch && patch.baseVersionId === document.currentVersion.id) || null;
    setRewriteSessionId(currentPendingPatch?.rewriteSessionId || "");
    setPendingPatch(currentPendingPatch);
    setContextScope("selection");
    setFullDocumentConfirmed(false);
  }, [document.id, document.currentVersion.id]);

  useEffect(() => {
    setMessage("");
    setTab(document.analysis ? "detection" : "agent");
  }, [document.id]);

  const outline = useMemo(() => paragraphs.filter((paragraph) => paragraph.text.length < 80 && !/[.!?]$/.test(paragraph.text)).slice(0, 12), [paragraphs]);

  function updateParagraph(paragraphId: string, value: string) {
    draft.current = draft.current.map(paragraph => paragraph.id === paragraphId ? { ...paragraph, text: value } : paragraph);
    dirtyRef.current = true;
    setDirty(true);
    setParagraphs(draft.current);
  }

  // Keep reload/close protection in one place; paper text is not stored in localStorage.
  useEffect(() => {
    if (!dirty && !busy) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, busy]);

  async function run(action: () => void | Promise<unknown>) {
    if (working.current) return;
    working.current = true;
    setBusy(true);
    setMessage("");
    try { await action(); }
    catch (cause) { setMessage(cause instanceof Error ? cause.message : "操作未完成，修改仍保留在当前页面。"); }
    finally { working.current = false; setBusy(false); }
  }

  function navigate(action: Navigation) {
    if (working.current) return;
    mobileMenu.current?.removeAttribute("open");
    setMessage("");
    if (dirtyRef.current) setConfirmation({ kind: "unsaved", action });
    else void run(() => performNavigation(action));
  }

  async function performNavigation(action: Navigation) {
    if (action.kind === "open") await onOpen(action.id);
    else if (action.kind === "new") onNew();
    else if (action.kind === "logout") await onLogout();
    else if (action.kind === "billing") onBilling();
    else setConfirmation({ kind: "restore", version: action.version });
  }

  async function leaveDraft(action: Navigation, save: boolean) {
    if (save) await saveDraft();
    else {
      draft.current = document.currentVersion.paragraphs;
      dirtyRef.current = false;
      setParagraphs(draft.current);
      setDirty(false);
    }
    // On failed save no navigation is attempted and the editable draft survives.
    setConfirmation(null);
    await performNavigation(action);
  }

  async function exportDraft() {
    mobileMenu.current?.removeAttribute("open");
    const saved = await saveDraft();
    await downloadExport(saved);
    setMessage(`已导出版本 ${saved.currentVersion.number} 的纯文本 DOCX；请保留排版原稿。`);
  }

  async function decideBatch(acceptedIds: string[]) {
    if (dirtyRef.current || !batchSessionId) throw new Error("请先保存或撤销手动修改；旧批量建议不能应用到新正文。");
    const response = await api<{ document: PaperDocument; acceptedCount: number }>(`/api/v1/rewrite-sessions/${batchSessionId}/batch-decision`, {
      method: "POST", body: JSON.stringify({ expected_base_version_id: document.currentVersion.id, accepted_patch_ids: acceptedIds }),
    });
    onDocumentChange(response.document);
    setMessage(response.acceptedCount ? `已接受 ${response.acceptedCount} 项修改并保存为新版本；可在版本记录整体恢复，检测需要主动复检。` : "整批保留原文，没有创建新版本或再次调用模型。");
  }

  function openInspector(nextTab: InspectorTab) {
    setTab(nextTab);
    setInspectorCollapsed(false);
  }

  function reviewRiskSpan(nextSelection: { paragraphId: string; text: string }) {
    setSelection(nextSelection);
    setTab("agent");
    setInspectorCollapsed(false);
  }

  function changeContextScope(nextScope: AgentContextScope) {
    setContextScope(nextScope);
    if (nextScope !== "document") setFullDocumentConfirmed(false);
  }

  async function saveDraft(): Promise<PaperDocument> {
    if (!dirtyRef.current) return document;
    const payload = await api<{ document: PaperDocument }>(`/api/v1/documents/${document.id}`, {
      method: "PATCH",
      body: JSON.stringify({ base_version_id: document.currentVersion.id, paragraphs: draft.current }),
    });
    dirtyRef.current = false;
    draft.current = payload.document.currentVersion.paragraphs;
    setDirty(false);
    setRewriteSessionId("");
    setPendingPatch(null);
    onDocumentChange(payload.document);
    setParagraphs(draft.current);
    setMessage("版本已保存");
    return payload.document;
  }

  async function analyze() {
    setBusy(true);
    setMessage("");
    try {
      const current = await saveDraft();
      const operation = `analysis:${current.id}:${current.currentVersion.id}`;
      await api(`/api/v1/documents/${current.id}/analyses`, withIdempotency({ method: "POST" }, requestKey(operation)));
      completeRequest(operation);
      const refreshed = await api<{ document: PaperDocument }>(`/api/v1/documents/${current.id}`);
      onDocumentChange(refreshed.document);
      setParagraphs(refreshed.document.currentVersion.paragraphs);
      setTab("detection");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Analysis failed");
      if (isQuotaError(cause)) onBilling();
    } finally {
      setBusy(false);
    }
  }

  async function propose() {
    setBusy(true);
    setMessage("");
    try {
      const wasDirty = dirtyRef.current;
      const current = await saveDraft();
      const previousPatch = wasDirty ? null : pendingPatch;
      let sessionId = wasDirty ? "" : (previousPatch?.rewriteSessionId || rewriteSessionId);
      if (!sessionId) {
        const created = await api<{ rewriteSession: { id: string } }>(`/api/v1/documents/${current.id}/rewrite-sessions`, { method: "POST", body: JSON.stringify({ version_id: current.currentVersion.id }) });
        sessionId = created.rewriteSession.id;
        setRewriteSessionId(sessionId);
      }
      const safeSelection = {
        paragraphId: selection.paragraphId || current.currentVersion.paragraphs[0].id,
        text: selection.text,
      };
      const body = buildRewriteMessage({ instruction, selection: safeSelection, pendingPatch: previousPatch, contextScope, fullDocumentConfirmed });
      const operation = `rewrite:${sessionId}:${safeSelection.paragraphId}:${pendingPatch?.id || "first"}:${instruction}:${contextScope}`;
      const response = await api<{ patch: Patch }>(`/api/v1/rewrite-sessions/${sessionId}/messages`, withIdempotency({ method: "POST", body: JSON.stringify(body) }, requestKey(operation)));
      completeRequest(operation);
      setPendingPatch(response.patch);
      setRewriteSessionId(response.patch.rewriteSessionId || sessionId);
      setMessage(`Agent 建议版本 ${response.patch.revisionNumber || 1} 已生成，等待你审阅。`);
      setTab("agent");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Unable to prepare patch");
      if (isQuotaError(cause)) onBilling();
    } finally {
      setBusy(false);
    }
  }

  async function initialOneClickRewrite() {
    if (!initialOneClickAvailable) return;
    setBusy(true);
    setMessage("");
    setTab("agent");
    try {
      const current = await saveDraft();
      const operation = `first-pass:${current.id}:${current.currentVersion.id}`;
      const response = await api<{ applied: false; document: PaperDocument; revisedParagraphCount: number }>(`/api/v1/documents/${current.id}/first-pass-rewrite`, withIdempotency({
        method: "POST", body: JSON.stringify({ version_id: current.currentVersion.id }),
      }, requestKey(operation)));
      completeRequest(operation);
      onDocumentChange(response.document);
      setPendingPatch(null);
      setRewriteSessionId("");
      setMessage(`已生成 ${response.revisedParagraphCount} 项批量建议，正文尚未改变；请逐段审阅后接受。`);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "首次修改未完成");
      if (isQuotaError(cause)) onBilling();
    } finally {
      setBusy(false);
    }
  }

  async function accept(patch: Patch) {
    if (dirtyRef.current) throw new Error("正文有未保存修改，请先保存或撤销；不能应用旧补丁。");
    setBusy(true);
    try {
      const response = await api<{ document: PaperDocument }>(`/api/v1/patches/${patch.id}/accept`, { method: "POST", body: JSON.stringify({ expected_base_version_id: patch.baseVersionId }) });
      onDocumentChange(response.document);
      setParagraphs(response.document.currentVersion.paragraphs);
      setPendingPatch(null);
      setRewriteSessionId("");
      setContextScope("selection");
      setFullDocumentConfirmed(false);
      setMessage("Patch accepted as a new version; detection is now stale.");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Unable to accept patch");
    } finally { setBusy(false); }
  }

  async function reject(patch: Patch) {
    setBusy(true);
    try {
      await api(`/api/v1/patches/${patch.id}/reject`, { method: "POST", body: JSON.stringify({ expected_base_version_id: patch.baseVersionId }) });
      setPendingPatch(null);
      setContextScope("selection");
      setFullDocumentConfirmed(false);
      setMessage("Patch rejected; the document was not changed.");
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : "Unable to reject patch"); }
    finally { setBusy(false); }
  }

  function restore(version: VersionSummary) {
    navigate({ kind: "restore", version });
  }

  async function confirmRestore(version: VersionSummary) {
    setBusy(true);
    try {
      const response = await api<{ document: PaperDocument }>(`/api/v1/documents/${document.id}/versions/${version.id}/restore`, { method: "POST", body: JSON.stringify({ expected_current_version_id: document.currentVersion.id }) });
      onDocumentChange(response.document);
      setParagraphs(response.document.currentVersion.paragraphs);
      setDirty(false);
      setPendingPatch(null);
      setConfirmation(null);
      setMessage(`Version ${version.number} restored as a new immutable version.`);
    } finally { setBusy(false); }
  }

  function remove() {
    mobileMenu.current?.removeAttribute("open");
    setConfirmation({ kind: "delete" });
  }

  async function confirmRemove() {
    setBusy(true);
    try { await api(`/api/v1/documents/${document.id}`, { method: "DELETE" }); onDeleted(); }
    finally { setBusy(false); }
  }

  return (
    <main className="workspace-shell">
      {confirmation ? <ActionDialog busy={busy} onCancel={() => setConfirmation(null)}
        title={confirmation.kind === "unsaved" ? "有未保存的修改" : confirmation.kind === "delete" ? "立即删除这篇文稿？" : `恢复版本 ${confirmation.version.number}？`}>
        <p>{confirmation.kind === "unsaved" ? "保存成功后才能继续；也可以明确放弃当前草稿，或取消并继续编辑。" : confirmation.kind === "delete" ? "将删除本服务中的文稿、版本、检测与补丁；不会删除你已下载的文件或供应商副本。此操作无法撤销。" : "将所选内容恢复为新版本，原有历史仍保留。"}</p>
        {message ? <p role="status">{message}</p> : null}
        <div><button autoFocus className="button secondary" disabled={busy} onClick={() => setConfirmation(null)}>取消</button>
          {confirmation.kind === "unsaved" ? <>
            <button className="button secondary" disabled={busy} onClick={() => void run(() => leaveDraft(confirmation.action, false))}>放弃修改并继续</button>
            <button className="button primary" disabled={busy} onClick={() => void run(() => leaveDraft(confirmation.action, true))}>保存并继续</button>
          </> : <button className={confirmation.kind === "delete" ? "button danger-confirm" : "button primary"} disabled={busy}
            onClick={() => void run(() => confirmation.kind === "delete" ? confirmRemove() : confirmRestore(confirmation.version))}>{confirmation.kind === "delete" ? "确认删除" : "确认恢复"}</button>}
        </div>
      </ActionDialog> : null}

      <aside className="studio-nav" aria-label="主要导航">
        <div className="studio-brand"><span className="brand-mark inverse">P</span><strong>Paperlight</strong></div>
        <nav>
          <button className={inspectorCollapsed ? "active" : ""} onClick={() => setInspectorCollapsed(true)} title="文稿"><FileText size={22} /><span>文稿</span></button>
          <button onClick={() => setInspectorCollapsed(true)} title="结构"><ListTree size={22} /><span>结构</span></button>
          <button className={!inspectorCollapsed && tab === "agent" ? "active" : ""} onClick={() => openInspector("agent")} title="写作助手"><Sparkles size={22} /><span>写作助手</span></button>
          <button className={!inspectorCollapsed && tab === "detection" ? "active" : ""} onClick={() => openInspector("detection")} title="AI 写作风险检测"><ShieldCheck size={22} /><span>AI 风险</span></button>
          <button className={!inspectorCollapsed && tab === "versions" ? "active" : ""} onClick={() => openInspector("versions")} title="版本"><History size={22} /><span>版本</span></button>
          <button disabled={busy} onClick={() => navigate({ kind: "billing" })} title="套餐与用量"><CreditCard size={22} /><span>套餐</span></button>
        </nav>
        <button className="studio-logout" title="退出登录" disabled={busy} onClick={() => navigate({ kind: "logout" })}><LogOut size={20} /><span>退出</span></button>
      </aside>

      <section className="workspace-stage">
        <header className="workspace-header">
          <div className="document-title-block"><h1>{document.title}</h1><div><span className="saved-state"><Save size={14} />{dirty ? "有未保存修改" : `版本 ${document.currentVersion.number} 已保存`}</span><span>{document.currentVersion.wordCount.toLocaleString()} 词</span></div></div>
          <div className="header-actions"><button className="button secondary compact" onClick={() => openInspector("versions")}><FileClock size={17} />版本</button><button className="button secondary compact" disabled={busy} onClick={() => void run(exportDraft)}><Download size={17} />导出 DOCX</button><button className="button secondary compact desktop-only" onClick={remove} disabled={busy}><Trash2 size={17} />删除</button><button className="button primary compact" disabled={busy} onClick={() => navigate({ kind: "new" })}><Plus size={18} />新建文稿</button><details ref={mobileMenu} className="mobile-workspace-menu"><summary>更多</summary><div>
            <label>切换文稿<select aria-label="切换文稿" value={document.id} disabled={busy} onChange={event => navigate({ kind: "open", id: event.target.value })}>{documents.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
            <button className="mobile-menu-action" disabled={busy} onClick={() => void run(exportDraft)}>导出 DOCX</button>
            <button className="mobile-menu-action" disabled={busy} onClick={() => { mobileMenu.current?.removeAttribute("open"); openInspector("versions"); }}>查看版本</button>
            <button className="mobile-menu-action" disabled={busy} onClick={remove}>删除文稿</button>
            <button className="mobile-menu-action" disabled={busy} onClick={() => navigate({ kind: "logout" })}>退出登录</button>
          </div></details></div>
        </header>

        <div className={`workspace-grid ${inspectorCollapsed ? "inspector-collapsed" : ""}`}>
          <aside className="document-rail">
            <div className="rail-section document-switcher"><div className="rail-heading"><span>文稿大纲</span><button disabled={busy} onClick={() => navigate({ kind: "new" })} title="新建文稿"><Plus size={17} /></button></div><label className="document-picker"><span className="visually-hidden">打开文稿</span><select value={document.id} disabled={busy} onChange={(event) => navigate({ kind: "open", id: event.target.value })}>{documents.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><ChevronDown size={15} /></label></div>
            <div className="rail-section outline">{outline.length ? outline.map((item, index) => <button key={item.id} onClick={() => window.document.querySelector(`[data-paragraph-id="${item.id}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" })}><span>{String(index + 1).padStart(2, "0")}</span>{item.text}</button>) : <p>较短的标题会显示在这里。</p>}</div>
            <div className="rail-footer"><span>自动删除：{new Date(document.expiresAt).toLocaleDateString()}</span><strong>{document.currentVersion.wordCount.toLocaleString()} 词</strong></div>
          </aside>

          <section className="editor-region">
            {message ? <div className="workspace-message" role="status">{message}</div> : null}
            <div className="paper-scroller"><PaperEditor paragraphs={paragraphs} spans={spans} stale={stale} disabled={busy || Boolean(confirmation)} onParagraphChange={updateParagraph} onSelection={setSelection} onRiskSpan={reviewRiskSpan} /></div>
            <div className="editor-toolbar" aria-label="编辑器工具"><button title="撤销" disabled={busy} onPointerDown={event => event.preventDefault()} onClick={() => window.document.execCommand("undo")}><Undo2 size={17} /></button><button title="重做" disabled={busy} onPointerDown={event => event.preventDefault()} onClick={() => window.document.execCommand("redo")}><Redo2 size={17} /></button><span className="toolbar-separator" /><span className="toolbar-style">纯文本 · 不保留原排版</span>{dirty ? <><span className="toolbar-separator" /><button className="save-action" disabled={busy} onClick={() => void run(saveDraft)}><Save size={16} />保存版本</button></> : null}</div>
            <footer className="editor-status"><span>英文课程论文</span><span>{!document.analysis ? "当前版本尚未检测" : stale ? "检测结果需要刷新" : "检测结果与当前版本一致"}</span></footer>
          </section>

          <Inspector tab={tab} collapsed={inspectorCollapsed} onToggleCollapsed={() => setInspectorCollapsed((value) => !value)} document={{ ...document, analysis: document.analysis ? { ...document.analysis, isStale: stale } : null }} batchPatches={activeBatch} onBatchDecision={ids => void run(() => decideBatch(ids))} selectedText={selection.text} pendingPatch={pendingPatch} instruction={instruction} contextScope={contextScope} fullDocumentConfirmed={fullDocumentConfirmed} initialOneClickAvailable={initialOneClickAvailable} initialOneClickTargetText={initialOneClickTargetText} busy={busy} onTab={openInspector} onInstruction={setInstruction} onContextScope={changeContextScope} onFullDocumentConfirmed={setFullDocumentConfirmed} onAnalyze={() => void run(analyze)} onInitialOneClick={() => void run(initialOneClickRewrite)} onPropose={() => void run(propose)} onAccept={(patch) => void run(() => accept(patch))} onReject={(patch) => void run(() => reject(patch))} onRestore={restore} />
        </div>
      </section>
    </main>
  );
}
