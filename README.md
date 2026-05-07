# WeChat Work Trusted IP Auto-Updater Service

一个自动检测公网IP变化并通过 Playwright 浏览器自动化更新企业微信可信IP列表的Python服务。

## 项目结构

```
wechat/
├── app/                    # 应用代码目录
│   ├── __init__.py        # Python 包初始化
│   └── config.py          # 配置管理模块
├── data/                  # 数据存储目录
│   ├── cookies.json      # 浏览器Cookie存储
│   └── current_ip.txt    # 当前IP记录
├── tests/                 # 测试代码目录
├── .env.example          # 环境变量示例文件
├── requirements.txt      # Python依赖包列表
├── .gitignore           # Git忽略文件
└── README.md            # 项目说明文档
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install  # 安装浏览器驱动
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填入你的配置：

```bash
cp .env.example .env
```

然后编辑 `.env` 文件：

```env
# 企业微信应用 ID（逗号分隔）
WEWORK_APP_IDS=your_app_id_1,your_app_id_2

# 群机器人 Webhook Key
WEWORK_WEBHOOK_KEY=your_webhook_key

# IP 检测周期（cron 表达式，默认每 10 分钟）
IP_CHECK_CRON=*/10 * * * *

# Cookie 保活间隔（分钟，默认 20）
KEEP_ALIVE_INTERVAL_MINUTES=20

# Playwright 无头模式（默认 true）
HEADLESS=true

# 二维码扫码等待超时（秒，默认 120）
QR_TIMEOUT_SECONDS=120

# 服务端口（默认 8000）
PORT=8000
```

### 3. 验证配置

运行以下命令验证配置是否正确：

```bash
python -c "from app.config import settings; print('Config loaded, app_ids:', settings.wework_app_ids)"
```

### 4. 启动服务

待完善...

## 功能特性

- 🔍 自动检测公网IP变化
- 🤖 Playwright 自动化登录企业微信
- 📡 定时任务自动更新IP列表
- 📨 微信群机器人通知
- 💾 Cookie持久化管理
- 🛡️ 配置验证和错误处理

## 开发进度

- ✅ Task 1: 项目脚手架 + 配置管理模块
- 🚧 Task 2: IP 检测模块
- 🚧 Task 3: Cookie 管理模块
- 🚧 Task 4: 通知模块
- 🚧 Task 5: 浏览器操作模块
- 🚧 Task 6: 定时任务调度模块
- 🚧 Task 7: FastAPI 入口
- 🚧 Task 8: Docker 部署文件
- 🚧 Task 9: 集成验证