"use client";

import { useEffect, useMemo, useState } from "react";
import { AlignLeft, Bold, ChevronDown, Download, FileClock, FileText, History, Italic, ListTree, LogOut, Plus, Redo2, Save, ShieldCheck, Sparkles, Trash2, Undo2 } from "lucide-react";
import { api, downloadExport } from "@/lib/api";
import type { DocumentListItem, PaperDocument, Paragraph, Patch, VersionSummary } from "@/lib/types";
import { Inspector, type InspectorTab } from "./Inspector";
import { PaperEditor } from "./PaperEditor";

type Props = {
  document: PaperDocument;
  documents: DocumentListItem[];
  onDocumentChange: (document: PaperDocument) => void;
  onRefresh: () => void;
  onOpen: (id: string) => void;
  onNew: () => void;
  onDeleted: () => void;
  onLogout: () => void;
};

type Confirmation =
  | { kind: "delete" }
  | { kind: "restore"; version: VersionSummary };

export function Workspace(props: Props) {
  const { document, documents, onDocumentChange, onOpen, onNew, onDeleted, onLogout } = props;
  const [paragraphs, setParagraphs] = useState<Paragraph[]>(document.currentVersion.paragraphs);
  const [dirty, setDirty] = useState(false);
  const [tab, setTab] = useState<InspectorTab>(document.analysis ? "detection" : "agent");
  const [selection, setSelection] = useState({ paragraphId: paragraphs[0]?.id || "", text: "" });
  const [instruction, setInstruction] = useState("Make this passage more specific and less formulaic without changing the claim.");
  const [rewriteSessionId, setRewriteSessionId] = useState("");
  const [pendingPatch, setPendingPatch] = useState<Patch | null>(() => document.patches.find((patch) => patch.status === "pending") || null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const spans = document.analysis?.result?.spans || [];
  const stale = dirty || Boolean(document.analysis?.isStale);

  useEffect(() => {
    setParagraphs(document.currentVersion.paragraphs);
    setDirty(false);
    setSelection({ paragraphId: document.currentVersion.paragraphs[0]?.id || "", text: "" });
    setRewriteSessionId("");
    setPendingPatch(document.patches.find((patch) => patch.status === "pending") || null);
    setConfirmation(null);
  }, [document.id, document.currentVersion.id]);

  useEffect(() => {
    setMessage("");
    setTab(document.analysis ? "detection" : "agent");
  }, [document.id]);

  const outline = useMemo(() => paragraphs.filter((paragraph) => paragraph.text.length < 80 && !/[.!?]$/.test(paragraph.text)).slice(0, 12), [paragraphs]);

  function updateParagraph(paragraphId: string, value: string) {
    setParagraphs((current) => current.map((paragraph) => paragraph.id === paragraphId ? { ...paragraph, text: value } : paragraph));
  }

  function openInspector(nextTab: InspectorTab) {
    setTab(nextTab);
    setInspectorCollapsed(false);
  }

  async function saveDraft(): Promise<PaperDocument> {
    if (!dirty) return document;
    setBusy(true);
    try {
      const payload = await api<{ document: PaperDocument }>(`/api/v1/documents/${document.id}`, {
        method: "PATCH",
        body: JSON.stringify({ base_version_id: document.currentVersion.id, paragraphs }),
      });
      setDirty(false);
      setRewriteSessionId("");
      setPendingPatch(null);
      onDocumentChange(payload.document);
      setParagraphs(payload.document.currentVersion.paragraphs);
      setMessage("Version saved");
      return payload.document;
    } finally {
      setBusy(false);
    }
  }

  async function analyze() {
    setBusy(true);
    setMessage("");
    try {
      const current = await saveDraft();
      await api(`/api/v1/documents/${current.id}/analyses`, { method: "POST" });
      const refreshed = await api<{ document: PaperDocument }>(`/api/v1/documents/${current.id}`);
      onDocumentChange(refreshed.document);
      setParagraphs(refreshed.document.currentVersion.paragraphs);
      setTab("detection");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  }

  async function propose() {
    setBusy(true);
    setMessage("");
    try {
      const current = await saveDraft();
      let sessionId = rewriteSessionId;
      if (!sessionId) {
        const created = await api<{ rewriteSession: { id: string } }>(`/api/v1/documents/${current.id}/rewrite-sessions`, { method: "POST", body: JSON.stringify({ version_id: current.currentVersion.id }) });
        sessionId = created.rewriteSession.id;
        setRewriteSessionId(sessionId);
      }
      const paragraphId = selection.paragraphId || current.currentVersion.paragraphs[0].id;
      const response = await api<{ patch: Patch }>(`/api/v1/rewrite-sessions/${sessionId}/messages`, { method: "POST", body: JSON.stringify({ instruction, paragraph_id: paragraphId, selected_text: selection.text }) });
      setPendingPatch(response.patch);
      setTab("agent");
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : "Unable to prepare patch");
    } finally {
      setBusy(false);
    }
  }

  async function accept(patch: Patch) {
    setBusy(true);
    try {
      const response = await api<{ document: PaperDocument }>(`/api/v1/patches/${patch.id}/accept`, { method: "POST", body: JSON.stringify({ expected_base_version_id: patch.baseVersionId }) });
      onDocumentChange(response.document);
      setParagraphs(response.document.currentVersion.paragraphs);
      setPendingPatch(null);
      setRewriteSessionId("");
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
      setMessage("Patch rejected; the document was not changed.");
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : "Unable to reject patch"); }
    finally { setBusy(false); }
  }

  function restore(version: VersionSummary) {
    setConfirmation({ kind: "restore", version });
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
    setConfirmation({ kind: "delete" });
  }

  async function confirmRemove() {
    setBusy(true);
    try { await api(`/api/v1/documents/${document.id}`, { method: "DELETE" }); onDeleted(); }
    finally { setBusy(false); }
  }

  return (
    <main className="workspace-shell">
      {confirmation ? <div className="confirmation-backdrop"><section className="confirmation-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirmation-title"><span className="eyebrow">CONFIRM ACTION</span><h2 id="confirmation-title">{confirmation.kind === "delete" ? "立即删除这篇文稿？" : `恢复版本 ${confirmation.version.number}？`}</h2><p>{confirmation.kind === "delete" ? "所有版本、检测结果、补丁、任务和导出文件都会被立即删除，此操作无法撤销。" : "所选版本会成为新的不可变版本，已有历史版本仍会保留。"}</p><div><button className="button secondary" disabled={busy} onClick={() => setConfirmation(null)}>取消</button><button className={confirmation.kind === "delete" ? "button danger-confirm" : "button primary"} disabled={busy} onClick={() => confirmation.kind === "delete" ? void confirmRemove() : void confirmRestore(confirmation.version)}>{confirmation.kind === "delete" ? "确认删除" : "确认恢复"}</button></div></section></div> : null}

      <aside className="studio-nav" aria-label="主要导航">
        <div className="studio-brand"><span className="brand-mark inverse">P</span><strong>Paperlight</strong></div>
        <nav>
          <button className={inspectorCollapsed ? "active" : ""} onClick={() => setInspectorCollapsed(true)} title="文稿"><FileText size={22} /><span>文稿</span></button>
          <button onClick={() => setInspectorCollapsed(true)} title="结构"><ListTree size={22} /><span>结构</span></button>
          <button className={!inspectorCollapsed && tab === "agent" ? "active" : ""} onClick={() => openInspector("agent")} title="写作助手"><Sparkles size={22} /><span>写作助手</span></button>
          <button className={!inspectorCollapsed && tab === "detection" ? "active" : ""} onClick={() => openInspector("detection")} title="AI 检测"><ShieldCheck size={22} /><span>AI 检测</span></button>
          <button className={!inspectorCollapsed && tab === "versions" ? "active" : ""} onClick={() => openInspector("versions")} title="版本"><History size={22} /><span>版本</span></button>
        </nav>
        <button className="studio-logout" title="退出登录" onClick={onLogout}><LogOut size={20} /><span>退出</span></button>
      </aside>

      <section className="workspace-stage">
        <header className="workspace-header">
          <div className="document-title-block"><h1>{document.title}</h1><div><span className="saved-state"><Save size={14} />{dirty ? "有未保存修改" : `版本 ${document.currentVersion.number} 已保存`}</span><span>{document.currentVersion.wordCount.toLocaleString()} 词</span></div></div>
          <div className="header-actions"><button className="button secondary compact" onClick={() => openInspector("versions")}><FileClock size={17} />版本</button><button className="button secondary compact" onClick={() => void downloadExport(document)}><Download size={17} />导出 DOCX</button><button className="button secondary compact desktop-only" onClick={remove} disabled={busy}><Trash2 size={17} />删除</button><button className="button primary compact" onClick={onNew}><Plus size={18} />新建文稿</button></div>
        </header>

        <div className={`workspace-grid ${inspectorCollapsed ? "inspector-collapsed" : ""}`}>
          <aside className="document-rail">
            <div className="rail-section document-switcher"><div className="rail-heading"><span>文稿大纲</span><button onClick={onNew} title="新建文稿"><Plus size={17} /></button></div><label className="document-picker"><span className="visually-hidden">打开文稿</span><select value={document.id} onChange={(event) => onOpen(event.target.value)}>{documents.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><ChevronDown size={15} /></label></div>
            <div className="rail-section outline">{outline.length ? outline.map((item, index) => <button key={item.id} onClick={() => window.document.querySelector(`[data-paragraph-id="${item.id}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" })}><span>{String(index + 1).padStart(2, "0")}</span>{item.text}</button>) : <p>较短的标题会显示在这里。</p>}</div>
            <div className="rail-footer"><span>自动删除：{new Date(document.expiresAt).toLocaleDateString()}</span><strong>{document.currentVersion.wordCount.toLocaleString()} 词</strong></div>
          </aside>

          <section className="editor-region">
            {message ? <div className="workspace-message" role="status">{message}</div> : null}
            <div className="paper-scroller"><PaperEditor paragraphs={paragraphs} spans={spans} stale={stale} onDirty={() => setDirty(true)} onParagraphBlur={updateParagraph} onSelection={setSelection} /></div>
            <div className="editor-toolbar" aria-label="编辑器工具"><button title="撤销" onClick={() => window.document.execCommand("undo")}><Undo2 size={17} /></button><button title="重做" onClick={() => window.document.execCommand("redo")}><Redo2 size={17} /></button><span className="toolbar-separator" /><span className="toolbar-style">正文</span><span className="toolbar-font">Source Serif 4</span><span className="toolbar-separator" /><button title="加粗" onClick={() => window.document.execCommand("bold")}><Bold size={17} /></button><button title="斜体" onClick={() => window.document.execCommand("italic")}><Italic size={17} /></button><button title="左对齐"><AlignLeft size={17} /></button>{dirty ? <><span className="toolbar-separator" /><button className="save-action" disabled={busy} onClick={() => void saveDraft()}><Save size={16} />保存版本</button></> : null}</div>
            <footer className="editor-status"><span>英文课程论文</span><span>{stale ? "检测结果需要刷新" : "检测结果与当前版本一致"}</span></footer>
          </section>

          <Inspector tab={tab} collapsed={inspectorCollapsed} onToggleCollapsed={() => setInspectorCollapsed((value) => !value)} document={document} selectedText={selection.text} pendingPatch={pendingPatch} instruction={instruction} busy={busy} onTab={openInspector} onInstruction={setInstruction} onAnalyze={() => void analyze()} onPropose={() => void propose()} onAccept={(patch) => void accept(patch)} onReject={(patch) => void reject(patch)} onRestore={restore} />
        </div>
      </section>
    </main>
  );
}
