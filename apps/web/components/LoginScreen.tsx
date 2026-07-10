"use client";

import { FormEvent, useState } from "react";
import { LockKeyhole } from "lucide-react";

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
      <section className="auth-panel" aria-labelledby="login-title">
        <div className="brand-lockup"><span className="brand-mark">P</span><strong>Paperlight</strong></div>
        <div className="auth-heading">
          <span className="auth-icon" aria-hidden="true"><LockKeyhole size={20} /></span>
          <div><h1 id="login-title">Owner workspace</h1><p>Private access for academic document review.</p></div>
        </div>
        <form onSubmit={submit} className="auth-form">
          <label>Email<input autoComplete="username" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required /></label>
          <label>Password<input autoComplete="current-password" type="password" minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          <label>Authenticator code <span className="optional-label">if enabled</span><input autoComplete="one-time-code" inputMode="numeric" value={totp} onChange={(event) => setTotp(event.target.value.replace(/\D/g, "").slice(0, 6))} /></label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button className="button primary wide" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <p className="privacy-footnote">Paper text never belongs in browser logs. Sessions end when this tab is closed.</p>
      </section>
    </main>
  );
}
