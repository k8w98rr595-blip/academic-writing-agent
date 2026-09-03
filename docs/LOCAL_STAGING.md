# 独立本地测试环境

这是一套可复现的**本地功能预演环境**，不是公开测试站，也不是 Railway/PostgreSQL/Redis 的等价部署；生产仍使用 Pangram + DeepSeek，客户收费保持关闭。

## 已隔离的边界

| 项目 | 本地测试 | 与生产的关系 |
|---|---|---|
| 前端 | `http://127.0.0.1:3100/academic-writing-agent/` | 独立浏览器来源、Session 存储和 Pages 子路径构建 |
| 后端 | `http://127.0.0.1:8100` | `APP_ENV=local-staging`，仅绑定回环地址 |
| 数据 | `.staging/local/paperlight.db`、`.staging/local/objects/` | 独立 SQLite/对象目录，不连接生产数据库 |
| 任务 | `JOB_MODE=eager`，Redis 为空 | 不连接生产或本机开发队列 |
| 检测与改写 | `mock` / `mock` | 禁止真实 Provider、Key、付费与数据上传开关 |
| 套餐 | `BILLING_MODE=test` | 本地模拟 Free/Pro，不创建 Stripe 请求 |
| 账号 | `owner@staging.paperlight.local` | 启动时自行设置独立测试密码；不读取生产密码 |
| 构建 | `.staging/builds/<随机目录>/web/out/` | 独立源码副本；不覆盖 `apps/web/public/config.js` 或生产输出 |

启动器不加载任何 `.env` 文件，并以允许名单构造子进程环境；真实服务凭据、代理变量、外部数据库地址和未知环境变量都不会继承。

后端额外拒绝错误主机/Origin、真实模型、Stripe、共享队列和越出 `.staging` 的路径；前端 CSP 只允许测试 API，运行时配置也拒绝非隔离地址；这些措施用于防误操作，不是抵御已经控制本机进程的恶意用户的安全沙箱。

## 运行（PowerShell）

先进入项目根目录；使用现有 `.venv` 和已安装依赖，没有时先创建 Python 环境并安装 `services/api/requirements-dev.txt`，然后运行 `pnpm install --frozen-lockfile`。

```powershell
# 1. 每次源代码变化后重建（不需要 Docker、账号或 Key）
.\scripts\start-staging.ps1 build

# 2. 无人值守的合成文稿闭环验收；成功后自动清除本轮临时数据库
.\scripts\start-staging.ps1 smoke

# 3. 自己体验；在终端隐蔽输入一个全新的测试密码，不要用生产密码
.\scripts\start-staging.ps1 serve
```

用浏览器打开上表前端地址，用测试邮箱与刚设置的密码登录；认证器留空；测试密码不打印、不写文件，后端仅接收进程内哈希；重启后重新设置密码，旧会话失效。

按 `Ctrl+C` 停止前后端；交互测试数据保留在 `.staging/local`，文稿仍遵守七天保留规则，也可在页面主动删除；没有自动删除任何已有凭据文件。

端口被占用时启动失败，不自动结束其他进程；Windows 后台 API 隐藏启动；完整构建目录含指向依赖目录的 junction/symlink，不要使用会跟随链接的递归清理工具。

## 自动验收内容

`smoke` 只使用内存中新生成的临时凭据和不少于 500 词的合成文稿，依次验证：隔离健康标记、Mock 模式、未登录 401、非法 Host/Origin 403、所有者登录、模拟升级、检测范围、结构化改写、接受补丁、旧结果过期、显式复检、风险变化、内存中 DOCX 导出、删除文稿、模拟降级和注销。

服务停止后检查文稿、版本、分析、补丁、改写会话、任务、Session、对象文件均为空，Provider 调用账本没有记录，然后仅删除本次 `smoke-*` 运行的临时数据库；不会清空 `.staging/local` 或生产数据。

GitHub Actions 的 `Isolated local staging` 工作流重建并执行同一脚本，不使用 Secrets，不发布网页，不部署 Railway，不保留文稿或数据库制品。

## 不应混淆的三个阶段

1. **本轮：本地模拟环境**，可验证功能和配额状态，但不代表 Stripe、云端并发或多用户安全已验收。
2. **后续：真实部署形态的 staging**，需另行批准 Railway 成本并建立独立服务、PostgreSQL、Redis、存储、域名与凭据，不能复制生产数据库或秘密；必须补测迁移、排队、并发、恢复与反向代理。
3. **后续：Stripe Sandbox 联调**，由所有者选择/创建独立 Sandbox，自行填写测试 Key、Webhook secret 与测试 Price ID，测试结账、续订失败、重复/乱序回调、取消与退款，不使用 live Key；当前 `local-staging` 故意拒绝 Stripe，不能通过改一个变量直接解除边界。

Stripe 官方说明：额外 Sandbox 与 live 配置隔离，默认 test-mode sandbox 部分设置可能与 live 共用；仪表盘处于测试视图并不能替代后端使用正确的测试 Key：[官方测试环境说明](https://docs.stripe.com/testing-use-cases)、[Sandboxes](https://docs.stripe.com/sandboxes)（核对于 2026-09-04）。

下一阶段优先实现**多用户账号与文稿隔离**并在本环境做越权测试，之后再进入 Stripe Sandbox；任何真实扣款、生产支付开关、生产认证变更或新云资源费用均需单独确认。
