"use client";

import { FormEvent, useMemo, useState } from "react";
import { FilePlus2, LogOut, Upload, WandSparkles } from "lucide-react";
import type { DocumentListItem } from "@/lib/types";
import { countWords, makeDemoPaper } from "@/lib/text";

type Props = {
  busy: boolean;
  error: string;
  documents: DocumentListItem[];
  onCreate: (form: FormData) => Promise<void>;
  onOpen: (id: string) => void;
  onLogout: () => void;
};

export function CreateDocument({ busy, error, documents, onCreate, onOpen, onLogout }: Props) {
  const [title, setTitle] = useState("Ethics of Data Reuse");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const words = useMemo(() => countWords(text), [text]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const form = new FormData();
    form.set("title", title);
    if (file) form.set("file", file);
    else form.set("text", text);
    void onCreate(form);
  }

  return (
    <main className="library-shell">
      <header className="library-header"><div className="brand-lockup"><span className="brand-mark">P</span><strong>Paperlight</strong></div><button className="icon-text-button" onClick={onLogout}><LogOut size={17} />Sign out</button></header>
      <div className="library-grid">
        <aside className="recent-rail"><h2>Recent documents</h2>{documents.length ? documents.map((item) => <button key={item.id} className="recent-row" onClick={() => onOpen(item.id)}><strong>{item.title}</strong><span>{new Date(item.updatedAt).toLocaleDateString()}</span></button>) : <p>No documents yet.</p>}</aside>
        <section className="create-panel" aria-labelledby="create-title">
          <div className="create-heading"><span className="large-icon"><FilePlus2 /></span><div><h1 id="create-title">Start a coursework review</h1><p>Paste an English paper or import a safe .docx file. V1 supports 800–5,000 words.</p></div></div>
          <form onSubmit={submit}>
            <label className="field-label">Document title<input value={title} maxLength={180} onChange={(event) => setTitle(event.target.value)} required /></label>
            <div className="source-tabs" role="group" aria-label="Document source">
              <button type="button" className={!file ? "active" : ""} onClick={() => setFile(null)}>Paste text</button>
              <label className={file ? "active upload-tab" : "upload-tab"}><Upload size={16} />Import .docx<input className="visually-hidden" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>
            </div>
            {file ? <div className="file-choice"><Upload size={18} /><div><strong>{file.name}</strong><span>{Math.ceil(file.size / 1024)} KB · server-side validation required</span></div></div> : <div className="paper-input-wrap"><textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="Paste the paper with paragraph breaks…" /><div className="input-footer"><span className={words >= 800 && words <= 5000 ? "valid" : ""}>{words.toLocaleString()} / 800–5,000 words</span><button type="button" className="text-action" onClick={() => setText(makeDemoPaper())}><WandSparkles size={15} />Use safe demo paper</button></div></div>}
            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <button className="button primary" disabled={busy || !title.trim() || (!file && (words < 800 || words > 5000))}>{busy ? "Creating…" : "Create private workspace"}</button>
          </form>
        </section>
      </div>
    </main>
  );
}
