"use client";

import { useEffect, useRef, useState } from "react";

export type PublicConfig = { registrationEnabled: boolean; publicAiEnabled: boolean; termsVersion: string; operator: string; supportEmail: string; retentionDays: number };

export function PublicHome({ onExperience, onLogin }: { onExperience: () => void; onLogin: () => void }) {
  // Publication policy, not a live backend status. Cloud activation requires
  // updating the public operator/contact disclosures as well as backend gates.
  const config: PublicConfig = { registrationEnabled: false, publicAiEnabled: false, termsVersion: "2026-10-08", operator: "", supportEmail: "", retentionDays: 7 };
  const [info, setInfo] = useState<"privacy" | "terms" | "help" | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (info) dialog.current?.showModal(); }, [info]);
  return <main className="public-shell">
    <header className="public-header"><div className="brand-lockup"><span className="brand-mark">P</span><strong>Paperlight</strong></div><button className="button secondary" onClick={onLogin}>登录工作台</button></header>
    <section className="public-hero"><span className="eyebrow">面向中文与英文学生写作</span><h1>把想法写清楚，<br />把修改握在自己手里。</h1><p>从课程报告到论文草稿，检查表达、审阅修改、保留版本。先用本地体验熟悉流程，文稿留在你的浏览器里。</p><div className="public-actions"><button className="button primary" onClick={onExperience}>免费本地体验</button><button className="button secondary" onClick={onLogin}>{config?.registrationEnabled ? "注册学生账号" : "已有账号登录"}</button></div><small>本地体验无需账号、无需上传，没有模型调用费用。</small></section>
    <section className="public-features" aria-label="功能说明"><article><span>01 / 写作</span><h2>中文与英文</h2><p>本地自检关注长句、重复段落与来源核验提示；云端工作台支持分章导入和编辑。</p></article><article><span>02 / 修改</span><h2>先审阅，再接受</h2><p>修改建议保留原文对照。作者决定接受或拒绝，云端版本可恢复。</p></article><article><span>03 / 风险</span><h2>理解检测的边界</h2><p>AI 写作风险是概率性信号，不能证明作者身份或学术不端，不承诺学校检测结果。</p></article></section>
    <section className="public-status"><h2>当前开放范围</h2><p>浏览器本地写作体验已开放。{config?.registrationEnabled ? "学生云端注册已开放。" : "学生云端注册暂未开放。"}{config?.publicAiEnabled ? "真实 AI 服务需登录并单独确认文稿处理说明。" : "面向公众的真实模型检测与改写尚未开放。"}</p><p>云端工作台支持中文 500–12,000 字/词、英文 500–5,000 词；DOCX 按纯文本转换，不保留原 Word 排版。请保留原稿。</p></section>
    <footer className="public-footer"><div><button onClick={() => setInfo("privacy")}>隐私与数据说明</button><button onClick={() => setInfo("terms")}>使用说明</button><button onClick={() => setInfo("help")}>帮助与反馈</button></div><span>{config?.operator || "公开本地体验 · 云端运营信息待确认"}</span></footer>
    {info ? <dialog ref={dialog} className="public-modal" aria-label="服务说明" onCancel={() => setInfo(null)}><section><button autoFocus className="button secondary" onClick={() => setInfo(null)}>关闭说明</button>
      {info === "privacy" ? <><h2>隐私与数据说明</h2><p>本地体验中的文稿在页面内存中处理，不发送给服务器或模型，也不写入浏览器持久存储。页面资源请求和公开服务状态请求仍可能由托管平台处理网络信息。</p><p>登录后的云端文稿会上传到现有境外云部署；默认保存 {config?.retentionDays || 7} 天，可主动删除。真实 AI 服务如开放，检测文本会发送给 Pangram，所选修改片段及确认的上下文会发送给 DeepSeek。</p><p>请勿提交姓名、学号、联系方式、未公开研究、第三方隐私或涉密材料。文稿不默认作为 Paperlight 的模型训练数据。账号密码使用不可逆哈希，恢复码只在创建或恢复时显示。</p><p>云端注册和公众 AI 服务开放前，需要确认运营主体、处理区域、供应商数据条款和适用的登记要求；公开本地体验不代表这些手续已经完成。</p></> : info === "terms" ? <><h2>使用说明</h2><p>Paperlight 用于作者主导的写作辅助，不能替代事实核查、引用核验和学术判断。请遵守课程要求，不用于代写、伪造材料或隐瞒应当披露的 AI 使用。</p><p>云端学生账号当前面向18岁及以上使用者。本地规则提示、演示结果和真实 Provider 结果均应按各自标签理解。</p><p>AI 修改建议须经作者审阅；导出使用过 AI 修改的文稿将提示修改来源。当前不对公众开放收费，未来价格需另行公示。</p></> : <><h2>帮助与反馈</h2><p>长论文请分章处理；DOCX 含公式、脚注、图片、修订或复杂表格时，请保留排版原稿并使用经核对的正文副本。</p><p>学生账号请保存一次性恢复码；未提供邮件找回功能。所有者仍通过原来的部署凭据登录。</p>{config?.supportEmail ? <p>联系邮箱：<a href={`mailto:${config.supportEmail}`}>{config.supportEmail}</a></p> : <p>公众云端服务的联系邮箱尚未配置，正式开放前会在此公布。</p>}</>}
    </section></dialog> : null}
  </main>;
}
