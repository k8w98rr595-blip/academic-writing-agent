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
      <header className="library-header"><div className="brand-lockup"><span className="brand-mark">P</span><strong>Paperlight</strong></div><button className="icon-text-button" onClick={onLogout}><LogOut size={17} />退出登录</button></header>
      <div className="library-grid">
        <aside className="recent-rail"><span className="library-rail-label">文稿库</span><h2>最近文稿</h2>{documents.length ? documents.map((item) => <button key={item.id} className="recent-row" onClick={() => onOpen(item.id)}><strong>{item.title}</strong><span>{new Date(item.updatedAt).toLocaleDateString()}</span></button>) : <p>尚无文稿。</p>}</aside>
        <section className="create-panel" aria-labelledby="create-title">
          <div className="create-heading"><span className="large-icon"><FilePlus2 /></span><div><span className="eyebrow">NEW REVIEW</span><h1 id="create-title">开始一次论文审阅</h1><p>粘贴英文论文，或导入通过安全校验的 .docx 文件。当前支持 800 至 5,000 个英文单词。</p></div></div>
          <form onSubmit={submit}>
            <label className="field-label">文稿标题<input value={title} maxLength={180} onChange={(event) => setTitle(event.target.value)} required /></label>
            <div className="source-tabs" role="group" aria-label="文稿来源">
              <button type="button" className={!file ? "active" : ""} onClick={() => setFile(null)}>粘贴文本</button>
              <label className={file ? "active upload-tab" : "upload-tab"}><Upload size={16} />导入 .docx<input className="visually-hidden" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>
            </div>
            {file ? <div className="file-choice"><Upload size={18} /><div><strong>{file.name}</strong><span>{Math.ceil(file.size / 1024)} KB · 将在服务端执行安全校验</span></div></div> : <div className="paper-input-wrap"><textarea value={text} onChange={(event) => setText(event.target.value)} placeholder="在此粘贴论文，并保留段落分隔..." /><div className="input-footer"><span className={words >= 800 && words <= 5000 ? "valid" : ""}>{words.toLocaleString()} / 800 至 5,000 词</span><button type="button" className="text-action" onClick={() => setText(makeDemoPaper())}><WandSparkles size={15} />使用安全演示论文</button></div></div>}
            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <button className="button primary create-submit" disabled={busy || !title.trim() || (!file && (words < 800 || words > 5000))}>{busy ? "正在创建..." : "创建私密工作台"}</button>
          </form>
        </section>
      </div>
    </main>
  );
}
