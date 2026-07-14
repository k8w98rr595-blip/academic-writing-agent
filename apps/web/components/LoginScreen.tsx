"use client";

import { FormEvent, useState } from "react";
import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";

type Props = {
  busy: boolean;
  error: string;
  onLogin: (email: string, password: string, totpCode: string) => Promise<void>;
};

export function LoginScreen({ busy, error, onLogin }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    void onLogin(email, password, totp);
  }

  return (
    <main className="auth-shell">
      <aside className="auth-brand" aria-label="Paperlight">
        <div className="auth-brand-mark"><span className="brand-mark inverse">P</span><strong>Paperlight</strong></div>
        <div className="auth-statement"><span>ACADEMIC WRITING WORKSPACE</span><h2>让修改过程更清楚，<br />让作者始终掌握决定权。</h2><p>检测证据、可撤销改写与版本记录，集中在一个私密工作台中。</p></div>
        <div className="auth-trust"><ShieldCheck size={18} /><span>仅限所有者访问</span></div>
      </aside>
      <section className="auth-panel" aria-labelledby="login-title">
        <div className="auth-heading">
          <span className="auth-icon" aria-hidden="true"><LockKeyhole size={20} /></span>
          <div><span className="eyebrow">PRIVATE WORKSPACE</span><h1 id="login-title">登录 Paperlight</h1><p>进入你的私密论文工作台。</p></div>
        </div>
        <form onSubmit={submit} className="auth-form">
          <label>邮箱<input autoComplete="username" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          <label>密码<input autoComplete="current-password" type="password" minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          <label>认证器代码 <span className="optional-label">启用时填写</span><input autoComplete="one-time-code" inputMode="numeric" value={totp} onChange={(event) => setTotp(event.target.value.replace(/\D/g, "").slice(0, 6))} /></label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="button primary wide" disabled={busy}>{busy ? "正在登录..." : <>进入工作台<ArrowRight size={17} /></>}</button>
        </form>
        <p className="privacy-footnote">论文全文、访问令牌与模型密钥不会写入浏览器日志。</p>
      </section>
    </main>
  );
}
