# 公开本地体验发布验证 — 2026-10-08

## 范围

新的目标为中文/英文学生写作，取消接近Turnitin的研究目标。运营主体及联系邮箱尚未确定，因此本次可发布范围是公开首页、说明页面和浏览器本地体验；学生云端注册、公众真实AI及收费均关闭。现有所有者Pangram/DeepSeek模式和TOTP状态不改。

## 验证方法与本地结果

| 检查 | 结果与边界 |
|---|---|
| Python全套 | 215项通过；含新增24项公众门控、身份隔离、恢复/注销、中文闭环和费用回归；未调用真实Provider |
| 前端单元/SSR | 27项通过，含新增本地规则、中文计数、Unicode高亮及公开文案边界 |
| Node发布/扫描脚本 | 12项通过 |
| TypeScript | 通过 |
| Next.js静态构建 | 15.5.27，真实生产API地址和Pages子路径构建通过；随后恢复源代码中的占位config.js |
| 静态及已跟踪源密钥扫描 | 通过；新增文件进入暂存后须再次扫描。扫描匹配只报告文件，不输出秘密 |
| 前端依赖审计 | pnpm audit --prod无已知漏洞；Next、sharp、source-map-js已升级 |
| Python依赖审计 | requirements解析集和本机安装环境审计均无已知漏洞；anyio/lxml/urllib3安全下限、pytest及pip已更新 |
| 隔离Mock闭环 | 登陆、模拟套餐、英文文稿、分类高亮、批量预览/确认、恢复、单补丁、过期、复检、比较、有效DOCX、删除与会话撤销通过 |
| 中文闭环 | 合成中文创建→Mock检测→建议→接受→检测过期→主动复检→DOCX→删除通过（后端集成测试） |
| 桌面与手机浏览器 | headless Chromium实渲染1440×1000和390×844核心检查通过；自检/预览/接受/撤销/实际TXT下载、过期提示、说明对话框焦点/Escape、登录门控、无横向溢出 |
| 浏览器内容网络隔离 | 两种尺寸均0个写请求、0个控制台错误，无localStorage/sessionStorage正文；页面资源/公开配置GET不属于正文上传 |
| Docker | 本机没有Docker，未声称本地镜像构建通过；以Railway构建和健康检查为后续部署证据 |

本轮没有Browser技能插件，因此依前端验收技能的缺失插件备用路径使用本机Playwright；临时QA脚本和截图在仓库外。全部文稿为专门生成的无敏感测试内容。隔离smoke确认正文、对象、会话、临时数据库和Provider调用表清理完成；pytest运行数据库也是独立临时数据，不是生产数据库。

已修复审计中发现的依赖问题；UTF-8模式下Windows icacls输出原生编码导致ACL测试解码失败，改为检查原始字节，未跳过权限断言。仍有Starlette/httpx和AnyIO别名弃用提醒，不等于运行失败。

## 生产验收边界

发布前本机Pages/GitHub检查通过，但Railway域名TLS连接中断；不能从连接失败推断余额、故障原因或生产模式，也不能沿用历史成功记录当作本轮通过。提交/推送后按同一SHA核对Pages、Railway commit status和Production smoke，另从真实Pages跑匿名本地体验。本文件不把预发布测试当作实际部署成功，最终交付须给出具体发布证据和任何未通过项。

新增Production smoke检查公开首页和 `/api/v1/public/config`，默认要求registrationEnabled=false、publicAiEnabled=false、localExperienceAvailable=true，同时保留401、CORS、Provider模式等原有验证。Smoke不创建文稿、不登录、不调用付费Provider，也不证明公众云端合规和国内各学校网络可达。

## 未完成项目

运营主体/邮箱、明确处理区域和供应商条款、适用登记/标识及跨境安排、独立中文误报评测、国内网络测试、PostgreSQL多租户并发/Redis失败和恢复演练、邀请防滥用、支持响应、公开定价/退款、历史密码轮换均是云端开放前事项。不得恢复TOTP或读取原凭据来“补齐验收”。本次0个真实Provider调用，不充值、不购买、不新增套餐；既有基础设施账单未核对，不能宣称全部运营零费用。

复现：`python -m pytest tests -q`、`pnpm test`、`pnpm typecheck`、设置Pages子路径和真实API公共地址后`pnpm build`、`pnpm check:secrets`、`pnpm audit --prod`、`python -m pip_audit -r services/api/requirements.txt`、`scripts/start-staging.ps1 build`及`smoke`。不要复制生产凭据到测试环境。步骤和门控见[公开上线说明](PUBLIC_LAUNCH.md)。
