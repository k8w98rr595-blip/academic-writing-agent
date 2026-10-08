"use client";

import { FormEvent, useEffect, useState } from "react";
import { ArrowRight, LockKeyhole, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";
import type { PublicConfig } from "./PublicHome";

type Props = {
  busy: boolean;
  error: string;
  onLogin: (email: string, password: string, totpCode: string) => Promise<void>;
  onBack: () => void;
  onRegistered: (token: string) => Promise<void>;
};

export function LoginScreen({ busy, error, onLogin, onBack, onRegistered }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [requiresTotp, setRequiresTotp] = useState(false);
  const [mode, setMode] = useState<"login" | "register" | "recover">("login");
  const [consent, setConsent] = useState(false);
  const [cloudConsent, setCloudConsent] = useState(false);
  const [recoveryInput, setRecoveryInput] = useState("");
  const [notice, setNotice] = useState("");
  const [working, setWorking] = useState(false);
  const [recovery, setRecovery] = useState<{ key: string; token?: string } | null>(null);
  useEffect(() => {
    api<PublicConfig>("/api/v1/public/config").then(setConfig).catch(() => {});
    api<{ requiresTotp: boolean }>("/api/v1/auth/status").then(s => setRequiresTotp(s.requiresTotp)).catch(() => {});
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (mode === "login") { await onLogin(email, password, totp); return; }
    setWorking(true); setNotice("");
    try {
      if (mode === "register") {
        const result = await api<{ session_token: string; recovery_key: string }>("/api/v1/auth/register", { method: "POST", body: JSON.stringify({ username: email, password, accepted_terms_version: config?.termsVersion, adult_confirmed: consent, cloud_storage_consent: cloudConsent }) });
        setRecovery({ key: result.recovery_key, token: result.session_token });
      } else {
        const result = await api<{ recovery_key: string }>("/api/v1/auth/recover", { method: "POST", body: JSON.stringify({ username: email, recovery_key: recoveryInput, new_password: password }) });
        setRecovery({ key: result.recovery_key });
      }
      setPassword(""); setRecoveryInput("");
    } catch (cause) { setNotice(cause instanceof Error ? cause.message : "账号操作失败，请稍后重试"); }
    finally { setWorking(false); }
  }

  return (
    <main className="auth-shell">
      <aside className="auth-brand" aria-label="Paperlight">
        <div className="auth-brand-mark"><span className="brand-mark inverse">P</span><strong>Paperlight</strong></div>
        <div className="auth-statement"><span>STUDENT WRITING WORKSPACE</span><h2>让修改过程更清楚，<br />让作者始终掌握决定权。</h2><p>中文与英文写作、可审阅修改与版本记录，集中在私密工作台中。</p></div>
        <div className="auth-trust"><ShieldCheck size={18} /><span>文稿按账号隔离 · 无需实名学生信息</span></div>
      </aside>
      <section className="auth-panel" aria-labelledby="login-title">
        <div className="auth-heading">
          <span className="auth-icon" aria-hidden="true"><LockKeyhole size={20} /></span>
          <div><span className="eyebrow">PRIVATE WORKSPACE</span><h1 id="login-title">{mode === "login" ? "登录 Paperlight" : mode === "register" ? "创建学生账号" : "用恢复码重设密码"}</h1><p>{mode === "register" ? "不收集姓名、学校、学号。请保存一次性恢复码。" : "进入你的私密写作工作台。"}</p></div>
        </div>
        {recovery ? <div className="auth-form"><h2>请先保存恢复码</h2><p>恢复码仅本次显示，可用于重设密码。不要发送到聊天、邮件或截图。下次恢复后旧码失效。</p><input aria-label="账号恢复码" readOnly value={recovery.key} />{notice ? <p role="alert">{notice}</p> : null}<button className="button primary" disabled={working} onClick={async () => { setWorking(true); try { if (recovery.token) await onRegistered(recovery.token); else { setMode("login"); setNotice("密码已更新，请重新登录"); } setRecovery(null); } catch { setNotice("账号已创建，但工作台暂时无法加载；请保留恢复码并稍后重试。"); } finally { setWorking(false); } }}>我已安全保存，继续</button></div> : <form onSubmit={submit} className="auth-form">
          <label>{mode === "login" ? "用户名或所有者邮箱" : "用户名（3–32位英文、数字或下划线，字母开头）"}<input autoComplete="username" type="text" value={email} maxLength={320} onChange={(event) => setEmail(event.target.value)} required /></label>
          <label>{mode === "recover" ? "新密码" : "密码（至少12个字符）"}<input autoComplete={mode === "login" ? "current-password" : "new-password"} type="password" minLength={12} maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          {mode === "login" && requiresTotp ? <label>所有者认证器代码<input autoComplete="one-time-code" inputMode="numeric" value={totp} onChange={(event) => setTotp(event.target.value.replace(/\D/g, "").slice(0, 6))} /></label> : null}
          {mode === "recover" ? <label>恢复码<input autoComplete="off" value={recoveryInput} onChange={e => setRecoveryInput(e.target.value)} required /></label> : null}
          {mode === "register" ? <><label className="context-confirm"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} required /><span>我已满18岁，并已阅读首页的使用说明与隐私说明。</span></label><label className="context-confirm"><input type="checkbox" checked={cloudConsent} onChange={e => setCloudConsent(e.target.checked)} required /><span>我单独同意把脱敏文稿上传到已说明的境外云端，默认7天删除；真实模型处理需另行确认。</span></label></> : null}
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          {notice ? <p role="status">{notice}</p> : null}
          <button className="button primary wide" disabled={busy || working}>{busy || working ? "正在处理..." : <>{mode === "login" ? "进入工作台" : mode === "register" ? "创建账号" : "重设密码"}<ArrowRight size={17} /></>}</button>
        </form>}
        {!recovery ? <div className="public-actions"><button className="text-action" onClick={() => { setMode(mode === "recover" ? "login" : "recover"); setNotice(""); }}>恢复码找回</button>{config?.registrationEnabled ? <button className="text-action" onClick={() => { setMode(mode === "register" ? "login" : "register"); setNotice(""); }}>{mode === "register" ? "已有账号登录" : "注册学生账号"}</button> : null}<button className="text-action" onClick={onBack}>返回公开首页</button></div> : null}
        <p className="privacy-footnote">论文全文、访问令牌与模型密钥不会写入浏览器日志。</p>
      </section>
    </main>
  );
}
