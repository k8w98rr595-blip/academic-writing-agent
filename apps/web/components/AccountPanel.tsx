"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ActionDialog } from "./ActionDialog";

type Account = { role: "owner" | "student"; username: string; canUseRealAi: boolean; providerConsent?: boolean; termsVersion?: string };

export function AccountPanel({ onClose, onEnded }: { onClose: () => void; onEnded: () => Promise<void> }) {
  const [account, setAccount] = useState<Account | null>(null);
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => { api<Account>("/api/v1/account").then(setAccount).catch(() => setMessage("账号信息暂时无法加载")); }, []);
  async function change(kind: "password" | "delete" | "consent") {
    setBusy(true); setMessage("");
    try {
      if (kind === "consent") {
        await api("/api/v1/account/provider-consent", { method: "POST", body: JSON.stringify({ consent: !account?.providerConsent, accepted_terms_version: account?.termsVersion }) });
        setAccount(account ? { ...account, providerConsent: !account.providerConsent } : null);
      } else {
        await api(kind === "delete" ? "/api/v1/account" : "/api/v1/account/password", { method: kind === "delete" ? "DELETE" : "POST", body: JSON.stringify(kind === "delete" ? { password } : { current_password: password, new_password: newPassword }) });
        setPassword(""); setNewPassword(""); await onEnded();
      }
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : "操作未完成，请重试"); }
    finally { setBusy(false); }
  }
  return <ActionDialog title="账号与数据设置" busy={busy} onCancel={onClose}>
    {account ? <><p>{account.username} · {account.role === "owner" ? "所有者账号" : "学生账号"}</p>
      {account.role === "owner" ? <p>所有者密码与认证器配置继续由部署变量管理，此处不会修改。公开注册和公众 AI 服务默认关闭。</p> : <>
        <p>真实模型处理是单独的授权，可随时撤回；撤回不撤销已经发送给供应商的数据。文稿默认七天删除，可在工作台立即删除。</p>
        <p>授权时，检测正文会发送给 Pangram，修改片段及确认的上下文会发送给 DeepSeek；云端使用境外部署，请勿提交个人信息或未公开研究。</p>
        {account.canUseRealAi || account.providerConsent ? <button className="button secondary" disabled={busy} onClick={() => void change("consent")}>{account.providerConsent ? "撤回供应商处理授权" : "单独同意供应商处理脱敏文稿"}</button> : <p>公众真实 AI 尚未开放；当前不会向新学生账号提供真实调用。</p>}
        <div className="account-form"><label>当前密码<input type="password" autoComplete="current-password" value={password} minLength={12} maxLength={256} onChange={e => setPassword(e.target.value)} /></label><label>新密码<input type="password" autoComplete="new-password" value={newPassword} minLength={12} maxLength={256} onChange={e => setNewPassword(e.target.value)} /></label></div>
        <button className="button secondary" disabled={busy || password.length < 12 || newPassword.length < 12} onClick={() => void change("password")}>修改密码并退出所有会话</button>
        <p>注销会删除账号、文稿、版本、检测与修改记录。无正文的计费和调用风控记录按既定保留周期清理；注销不会删除供应商持有的副本。</p>
        {confirmDelete ? <><p role="alert">注销不可恢复，请再次确认；当前密码用于验证身份。</p><button className="button danger-confirm" disabled={busy || password.length < 12} onClick={() => void change("delete")}>确认注销并删除文稿</button><button className="button secondary" disabled={busy} onClick={() => setConfirmDelete(false)}>取消注销</button></> : <button className="button danger-outline" disabled={busy} onClick={() => setConfirmDelete(true)}>注销学生账号</button>}
      </>}
    </> : <p>正在加载账号设置…</p>}
    {message ? <p role="alert">{message}</p> : null}<div><button autoFocus className="button secondary" disabled={busy} onClick={onClose}>关闭设置</button></div>
  </ActionDialog>;
}
