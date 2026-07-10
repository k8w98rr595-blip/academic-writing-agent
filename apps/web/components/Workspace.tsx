"use client";

import { useEffect, useMemo, useState } from "react";
import { AlignLeft, Bold, ChevronDown, Download, FileText, Italic, LogOut, Plus, Redo2, Save, Trash2, Undo2 } from "lucide-react";
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
      {confirmation ? <div className="confirmation-backdrop"><section className="confirmation-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirmation-title"><h2 id="confirmation-title">{confirmation.kind === "delete" ? "Delete this document now?" : `Restore version ${confirmation.version.number}?`}</h2><p>{confirmation.kind === "delete" ? "Every version, analysis, patch, job, and export will be removed immediately. This cannot be undone." : "The selected text will become a new immutable version. Existing versions remain available."}</p><div><button className="button secondary" disabled={busy} onClick={() => setConfirmation(null)}>Cancel</button><button className={confirmation.kind === "delete" ? "button danger-confirm" : "button primary"} disabled={busy} onClick={() => confirmation.kind === "delete" ? void confirmRemove() : void confirmRestore(confirmation.version)}>{confirmation.kind === "delete" ? "Confirm deletion" : "Confirm restore"}</button></div></section></div> : null}
      <header className="workspace-header"><div className="brand-lockup"><span className="brand-mark">P</span><strong>Paperlight</strong></div><label className="document-picker"><span className="visually-hidden">Open document</span><select value={document.id} onChange={(event) => onOpen(event.target.value)}>{documents.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><ChevronDown size={16} /></label><div className="header-actions"><button className="button primary" onClick={onNew}><Plus size={17} />New document</button><button className="button secondary" onClick={() => void downloadExport(document)}><Download size={17} />Export .docx</button><button className="button danger-outline desktop-only" onClick={remove} disabled={busy}><Trash2 size={17} />Delete</button><button className="icon-button" title="Sign out" onClick={onLogout}><LogOut size={18} /></button></div></header>
      <div className="workspace-grid">
        <aside className="document-rail"><div className="rail-section"><div className="rail-heading"><span>Document</span><button onClick={onNew} title="New document"><Plus size={16} /></button></div><div className="active-document"><FileText size={17} /><div><strong>{document.title}</strong><span>{document.currentVersion.wordCount.toLocaleString()} words</span></div></div></div><div className="rail-section outline"><div className="rail-heading"><span>Outline</span></div>{outline.length ? outline.map((item, index) => <button key={item.id} onClick={() => window.document.querySelector(`[data-paragraph-id="${item.id}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" })}><span>{index + 1}.</span>{item.text}</button>) : <p>Short headings appear here.</p>}</div><div className="rail-footer"><span>Deletes {new Date(document.expiresAt).toLocaleDateString()}</span></div></aside>
        <section className="editor-region"><div className="editor-toolbar" aria-label="Editor tools"><button title="Undo" onClick={() => window.document.execCommand("undo")}><Undo2 size={17} /></button><button title="Redo" onClick={() => window.document.execCommand("redo")}><Redo2 size={17} /></button><span className="toolbar-separator" /><button title="Bold" onClick={() => window.document.execCommand("bold")}><Bold size={17} /></button><button title="Italic" onClick={() => window.document.execCommand("italic")}><Italic size={17} /></button><button title="Align left"><AlignLeft size={17} /></button><span className="toolbar-spacer" />{dirty ? <button className="save-action" disabled={busy} onClick={() => void saveDraft()}><Save size={16} />Save version</button> : <span className="saved-state"><Save size={15} />Version {document.currentVersion.number} saved</span>}</div>{message ? <div className="workspace-message" role="status">{message}</div> : null}<div className="paper-scroller"><PaperEditor paragraphs={paragraphs} spans={spans} stale={stale} onDirty={() => setDirty(true)} onParagraphBlur={updateParagraph} onSelection={setSelection} /></div><footer className="editor-status"><span>{document.currentVersion.wordCount.toLocaleString()} words</span><span>English coursework</span><span>{stale ? "Detection needs refresh" : "Analysis aligned"}</span></footer></section>
        <Inspector tab={tab} document={document} selectedText={selection.text} pendingPatch={pendingPatch} instruction={instruction} busy={busy} onTab={setTab} onInstruction={setInstruction} onAnalyze={() => void analyze()} onPropose={() => void propose()} onAccept={(patch) => void accept(patch)} onReject={(patch) => void reject(patch)} onRestore={restore} />
      </div>
    </main>
  );
}
