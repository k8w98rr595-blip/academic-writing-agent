"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, CreditCard, ExternalLink, X } from "lucide-react";
import { api } from "@/lib/api";
import type { BillingSummary } from "@/lib/types";

const METER_LABELS: Record<string, string> = {
  documents_active: "在用文稿",
  storage_bytes: "文稿存储",
  ai_detection_runs: "每月 AI 风险检测",
  ai_rewrite_runs: "每月 Agent 改写",
};

function quantity(meter: string, value: number): string {
  if (meter === "storage_bytes") return `${Math.round(value / 1024 / 1024)} MB`;
  return value.toLocaleString();
}

type Props = { onClose: () => void };

export function BillingPanel({ onClose }: Props) {
  const [summary, setSummary] = useState<BillingSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reconcileAttempt, setReconcileAttempt] = useState(0);

  const refresh = useCallback(async () => {
    setSummary(await api<BillingSummary>("/api/v1/billing/summary"));
  }, []);

  useEffect(() => {
    void Promise.all([
      refresh(),
      api<void>("/api/v1/billing/events", {
        method: "POST",
        body: JSON.stringify({ event_name: "pro_page_viewed", trigger: "billing_panel" }),
      }),
    ]).catch((cause) => setError(cause instanceof Error ? cause.message : "无法读取套餐信息"));
  }, [refresh]);

  useEffect(() => {
    if (!summary || summary.mode !== "stripe" || summary.plan.key === "pro" || reconcileAttempt >= 8) return;
    const returnedFromCheckout = typeof window !== "undefined"
      && new URLSearchParams(window.location.search).get("billing") === "success";
    if (!returnedFromCheckout) return;
    const timer = window.setTimeout(() => {
      void refresh().finally(() => setReconcileAttempt((attempt) => attempt + 1));
    }, 1500);
    return () => window.clearTimeout(timer);
  }, [reconcileAttempt, refresh, summary]);

  async function startCheckout() {
    setBusy(true);
    setError("");
    try {
      const response = await api<{ url: string }>("/api/v1/billing/checkout-session", {
        method: "POST",
        body: JSON.stringify({ trigger: "billing_panel" }),
      });
      if (summary?.mode === "test") await refresh();
      else window.location.assign(response.url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法开始结账");
    } finally {
      setBusy(false);
    }
  }

  async function openPortal() {
    setBusy(true);
    setError("");
    try {
      const response = await api<{ url: string }>("/api/v1/billing/portal-session", {
        method: "POST",
        body: JSON.stringify({ trigger: "billing_panel" }),
      });
      window.location.assign(response.url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法打开订阅管理页");
    } finally {
      setBusy(false);
    }
  }

  async function setTestPlan(plan: "free" | "pro") {
    setBusy(true);
    try {
      await api<void>("/api/v1/billing/test/plan", { method: "POST", body: JSON.stringify({ plan }) });
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="billing-backdrop" role="presentation">
      <section className="billing-panel" role="dialog" aria-modal="true" aria-labelledby="billing-title">
        <header><div><span className="eyebrow">PLANS & USAGE</span><h1 id="billing-title">套餐与用量</h1><p>免费版保留完整核心闭环；Pro 面向更高频、更高资源消耗的写作。</p></div><button className="icon-button" onClick={onClose} aria-label="关闭套餐面板"><X /></button></header>
        {error ? <p className="form-error" role="alert">{error}</p> : null}
        {!summary ? <p className="billing-loading">正在读取套餐...</p> : <>
          <div className="plan-grid">
            {summary.plans.map((plan) => <article key={plan.key} className={`plan-card ${summary.plan.key === plan.key ? "current" : ""}`}>
              <div className="plan-title"><div><span>{plan.name}</span><h2>{plan.key === "free" ? "完整核心体验" : "高频与高额度"}</h2></div>{summary.plan.key === plan.key ? <strong>当前套餐</strong> : null}</div>
              <p>{plan.description}</p>
              <ul>{Object.entries(plan.quotas).map(([meter, limit]) => <li key={meter}><Check size={15} /><span>{METER_LABELS[meter] || meter}</span><strong>{quantity(meter, limit)}</strong></li>)}</ul>
              {plan.key === "pro" ? <p className="checkout-price-note">订阅价格、币种、优惠和税费以 Stripe Checkout 中配置的 recurring Price 为准。</p> : null}
            </article>)}
          </div>
          <section className="usage-section"><div><span className="eyebrow">CURRENT PERIOD</span><h2>本周期用量</h2></div><div className="usage-grid">{Object.entries(summary.usage).map(([meter, item]) => {
            const percent = item.limit ? Math.min(100, Math.round(item.used / item.limit * 100)) : 0;
            return <div className="usage-row" key={meter}><span>{METER_LABELS[meter] || meter}</span><strong>{quantity(meter, item.used)} / {quantity(meter, item.limit)}</strong><i><b style={{ width: `${percent}%` }} /></i></div>;
          })}</div></section>
          {summary.warnings.map((warning) => <p key={warning} className="billing-reconcile-note" role="alert">{warning}</p>)}
          <footer className="billing-actions">
            <div><strong>{summary.plan.name}</strong><span>{summary.subscription.cancelAtPeriodEnd ? "将在当前周期结束后转为 Free" : summary.subscription.status === "past_due" ? "付款失败宽限期内" : "权限由 Paperlight 统一管理"}</span></div>
            {summary.subscription.canManage ? <button className="button secondary" disabled={busy} onClick={() => void openPortal()}><CreditCard size={17} />管理订阅<ExternalLink size={14} /></button> : null}
            {summary.plan.key === "free" && summary.checkoutAvailable ? <button className="button primary" disabled={busy} onClick={() => void startCheckout()}><CreditCard size={17} />升级到 Pro</button> : null}
            {summary.mode === "disabled" ? <span className="billing-disabled-note">当前 owner-only 部署未开启收费。</span> : null}
          </footer>
          {summary.mode === "stripe" && summary.plan.key === "free" && reconcileAttempt > 0 ? <p className="billing-reconcile-note">支付结果正在通过签名 Webhook 对账；页面不会仅凭返回链接提前授予 Pro。</p> : null}
          {summary.mode === "test" ? <div className="test-billing-controls"><span>测试账单控制</span><button disabled={busy} onClick={() => void setTestPlan("free")}>切换 Free</button><button disabled={busy} onClick={() => void setTestPlan("pro")}>切换 Pro</button></div> : null}
        </>}
      </section>
    </div>
  );
}
