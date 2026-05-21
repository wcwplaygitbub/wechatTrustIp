# 企业微信可信 IP 自动更新服务

自动监控公网 IP 变化，在企业微信管理后台更新可信 IP 列表，防止异地登录被踢。

## 功能特性

- **IP 自动检测**：每 10 分钟检测一次公网 IP（或自定义 cron 表达式）
- **启动校验**：服务重启时自动登录企业微信，检查可信 IP 与当前公网 IP 是否一致，不同则自动更新
- **可信 IP 自动更新**：IP 变化时自动打开浏览器登录企业微信管理后台更新可信 IP
- **扫码登录**：Cookie 失效后推送二维码到企业微信群，点击即可扫码登录（无需手动处理）
- **验证码免登录**：需要短信验证码时，推送一次性免登录链接到企业微信，点击直接输入验证码
- **SSE 实时推送**：状态变化（验证码、二维码等）通过 Server-Sent Events 实时推送到浏览器，无需轮询
- **Webhook 通知**：IP 更新结果通过企业微信群机器人推送通知
- **Web 控制台**：`/console` 提供状态面板、日志查看、配置管理、密码修改等功能，支持移动端访问
- **Session 保护**：保活操作不访问登录页，避免踢掉已登录的企业微信客户端

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium --with-deps
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的配置
```

主要配置项：

| 配置项 | 说明 | 参考文档 |
|--------|------|----------|
| `WEWORK_APP_IDS` | 企业微信应用 ID，多个用逗号分隔 | [如何获取](企业微信应用%20ID获取.md) |
| `WEWORK_WEBHOOK_KEY` | 企业微信群机器人 Webhook Key | [如何获取](企业微信群通知%20webhook%20获取.md) |
| `IP_CHECK_CRON` | IP 检测周期，默认 `*/10 * * * *` | - |
| `PORT` | 服务端口，默认 `8000` | - |
| `CONSOLE_USERNAME` | 控制台用户名，默认 `admin` | - |
| `CONSOLE_PASSWORD` | 控制台密码，默认 `admin123` | - |
| `CONSOLE_URL` | 控制台外部访问地址，用于生成验证码免登录链接 | - |

```env
WEWORK_APP_IDS=your_app_id_here
WEWORK_WEBHOOK_KEY=your_webhook_key_here
IP_CHECK_CRON=*/10 * * * *
PORT=8000
CONSOLE_USERNAME=admin
CONSOLE_PASSWORD=admin123
CONSOLE_URL=http://your-server-ip:8000/console/
```

### 3. 启动服务

```bash
python -m app.main
```

### 4. 访问控制台

- 控制台：http://localhost:8000/console/
- 默认账号：`admin` / `admin123`

## 控制台功能

| 页面 | 路径 | 说明 |
|------|------|------|
| 状态面板 | `/console/` | 显示当前公网 IP、已注册 IP、Cookie 状态，下次检测时间，实时 SSE 推送 |
| 日志 | `/console/logs` | 查看最近 200 条运行日志，扫码相关日志内嵌二维码 |
| 配置 | `/console/config` | 修改 IP 检测周期、应用 ID、控制台地址，支持热更新 |
| 修改密码 | `/console/password` | 修改控制台登录密码 |
| 验证码输入 | `/console/captcha?t=xxx` | 一次性免登录验证码输入页（由通知链接直接打开） |

## 操作说明

### 首次登录

服务启动后，若无有效 Cookie，控制台首页会显示二维码。用企业微信扫描即可登录，Cookie 会自动保存。

### 手动操作

- **触发 IP 检测**：立即执行一次 IP 检测（不影响定时任务）
- **强制更新 IP**：即使 IP 未变化也强制更新一遍（用于测试）
- **清除 Cookie**：删除本地 Cookie，需要重新扫码登录

## 部署

### Docker 部署

```bash
# 启动服务
docker-compose up -d
```

## 项目结构

```
app/
├── __init__.py
├── browser.py      # Playwright 浏览器操作（登录、IP 更新）
├── config.py      # 配置管理
├── console.py     # Web 控制台路由
├── cookie_manager.py  # Cookie 持久化
├── ip_checker.py  # 公网 IP 获取
├── log_buffer.py  # 日志环形缓冲区
├── main.py        # FastAPI 入口
├── notifier.py    # 企业微信 Webhook 通知
└── scheduler.py   # 定时任务调度

templates/          # Web 控制台模板
data/               # Cookie、IP 等运行时数据（git 忽略）
```

## 工作原理

1. **启动校验**：服务启动时自动登录企业微信管理后台，读取当前可信 IP 并与公网 IP 对比，不一致则立即更新
2. **IP 检测**：通过多个 IP 查询服务获取当前公网 IP，与本地保存的 IP 对比
3. **IP 变化**：启动 Playwright 浏览器，用已有 Cookie 访问企业微信管理后台
4. **Cookie 失效**：打开登录页获取新二维码，推送到企业微信群，扫码后自动保存新 Cookie
5. **验证码处理**：检测到短信验证码页面时，生成一次性免登录链接推送到企业微信，用户点击即可输入验证码；验证码错误时自动重发新链接（最多 3 次）
6. **实时推送**：前端通过 SSE 接收后端事件，状态变化即时更新，无需轮询
7. **Session 保护**：保活操作直接访问后台首页（`/wework_admin/frame`），不经过登录页，避免淘汰客户端会话

## 注意事项

- Cookie 有效期通常为几小时到几天，失效后会自动推送二维码
- 不要在企业微信客户端登录的状态下频繁访问管理后台登录页，否则可能导致客户端被踢
- 保活任务已默认关闭，Cookie 只在 IP 检测时顺带检查，避免不必要的会话刷新