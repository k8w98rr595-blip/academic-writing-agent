"use client";

import { useEffect, useState } from "react";
import { acceptLocalProposal, CHINESE_SAMPLE, localProposal, writingReview } from "@/lib/writing";

export function PublicExperience({ onBack }: { onBack: () => void }) {
  const [text, setText] = useState(CHINESE_SAMPLE);
  const [history, setHistory] = useState<string[]>([]);
  const [review, setReview] = useState<{ source: string; value: ReturnType<typeof writingReview> } | null>(null);
  const [proposal, setProposal] = useState<ReturnType<typeof localProposal>>(null);
  const [message, setMessage] = useState("");
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);
  function exportText() {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "Paperlight-文稿.txt"; link.click();
    URL.revokeObjectURL(url); setDirty(false); setMessage("已导出当前文本，请确认下载完成。");
  }
  function back() { if (!dirty || window.confirm("尚有未导出的修改，确定离开并清空本地文稿？")) onBack(); }
  return <main className="public-shell">
    <header className="public-header"><strong>Paperlight / 本地写作体验</strong><button className="button secondary" onClick={back}>返回首页</button></header>
    <div className="local-intro"><h1>先把表达写清楚</h1><p>文本只在当前页面内存中处理，不上传、不持久保存。关闭页面前请导出。</p><p>这是规则驱动的写作自检和示例修改；没有调用 AI 模型，不提供 AI 生成百分比。</p></div>
    <div className="local-grid">
      <section className="local-paper"><label htmlFor="local-paper">中文或英文文稿</label><textarea id="local-paper" maxLength={50000} value={text} onChange={e => { setText(e.target.value); setDirty(true); setMessage(""); }} />
        <div className="public-actions"><button className="button primary" disabled={!text.trim()} onClick={() => { setReview({ source: text, value: writingReview(text) }); setMessage(""); }}>运行写作自检</button><button className="button" disabled={!text.trim()} onClick={exportText}>导出当前文本</button><button className="button" disabled={!history.length} onClick={() => { setText(history[history.length - 1]); setHistory(history.slice(0, -1)); setDirty(true); }}>撤销接受</button></div>
      </section>
      <aside className="local-results" aria-live="polite">
        <h2>自检与建议</h2>
        {review ? <><p>{review.value.metrics.count} {review.value.metrics.unit} · {review.value.paragraphs} 段</p>{review.source !== text ? <p className="form-error">结果已过期，请对当前文本重新自检。</p> : <ul>{review.value.notes.map(n => <li key={n}>{n}</li>)}</ul>}</> : <p>点击写作自检，查看句子、段落和来源核验提示。</p>}
        <button className="button wide" disabled={!text.trim()} onClick={() => { const result = localProposal(text); setProposal(result); setMessage(result ? "规则示例已生成，正文尚未改变。" : "没有匹配的示例开头，本地规则不生成新的内容。请自行修改，或在云端服务开放后使用写作助手。"); }}>生成规则修改示例</button>
        {proposal ? <div className="local-patch"><p>原文</p><blockquote>{proposal.original}</blockquote><p>建议</p><blockquote>{proposal.revised}</blockquote><div className="public-actions"><button className="button primary" disabled={proposal.source !== text} onClick={() => { setHistory([...history.slice(-9), text]); setText(acceptLocalProposal(text, proposal)); setDirty(true); setProposal(null); setMessage("已接受，可撤销。旧自检结果已过期。"); }}>接受建议</button><button className="button" onClick={() => { setProposal(null); setMessage("已保留原文。"); }}>保留原文</button></div></div> : null}
        {message ? <p role="status">{message}</p> : null}
        <p className="privacy-footnote">写作自检不会验证事实、引用真实性或论文作者身份，也不是论文查重。请遵守学校和课程的 AI 使用要求。</p>
      </aside>
    </div>
  </main>;
}
