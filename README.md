# 抖音内容采集与飞书推送系统

按关键词 / 话题搜索抖音内容，自动下载图片和视频，通过飞书自建应用机器人推送到指定群聊，支持 LLM 相关性过滤和定时任务。

## 功能特性

- **持续去重搜索**：搜索时实时跳过历史已见内容，持续翻页直到凑够目标数量的新内容，不再出现「搜索 5 条但新内容只有 1 条」
- **多种采集方式**：关键词搜索、话题抓取，支持排序 / 时间 / 内容类型过滤
- **定时调度**：Cron 表达式配置，支持每天、工作日、每周等多种调度方式
- **LLM 相关性过滤**：接入 OpenAI 兼容接口，用封面图（视觉）+ 文字描述判断相关性
- **飞书机器人推送**：通过自建应用机器人发送卡片消息到指定群聊，支持多渠道
- **多账号 Cookie**：管理多个抖音账号 Cookie，支持设默认账号
- **任务记录 + 采集明细**：任务记录内嵌采集明细，展示新内容数 / 下载数 / 推送数，失败原因和诊断信息直接可见
- **Web UI**：React + TailwindCSS 管理界面，支持配置增删改、任务手动触发、结果筛选

## 快速开始

### 1. 安装依赖

```bash
# Python 依赖
uv sync

# 安装 Playwright Chromium（签名服务需要）
uv run playwright install chromium

# 前端构建
cd frontend && npm install && npm run build && cd ..
```

### 2. 启动服务

```bash
./start.sh    # 后台启动（已运行则跳过）
./stop.sh     # 停止服务

# 或直接前台运行
uv run python -m backend.main
```

访问 **http://localhost:8000**

> **关于搜索实现**：搜索时通过 Playwright 驱动真实 Chromium 浏览器访问抖音搜索页，拦截响应直接取数据，完全绕过签名验证问题。每次搜索任务会启动独立浏览器进程，约 15-20s 完成。

### 3. 获取抖音 Cookie

```bash
# 方式一：扫码自动获取（推荐）
uv run python get_cookie.py
```

> `get_cookie.py` 会打开浏览器，登录成功后自动跳转抖音搜索页等待 `msToken` 写入，再提取完整 Cookie 并写入 `.env`。

Cookie 中需包含以下关键字段才有效：`sessionid`、`uid_tt`、`msToken`、`s_v_web_id`。

进入 **Cookie 管理** → 新增账号，粘贴 Cookie，设为默认。

> Cookie 有效期约数天至数周，失效时任务记录的「状态」列会显示「需要人机验证（Cookie 已失效，请重新获取）」。

### 4. 配置飞书机器人（可选）

前置准备：
1. 在[飞书开放平台](https://open.feishu.cn)创建**自建应用**
2. 开启权限：`im:message`（发送消息）
3. 将机器人添加到目标群聊

进入 **通知渠道** → 新增渠道，填写 App ID / App Secret，保存后点「查询机器人所在群」选择目标群。

> 飞书推送需要网络能访问 `open.feishu.cn`。如在受限网络环境下，启动服务前设置代理环境变量：
> ```bash
> HTTPS_PROXY=http://127.0.0.1:7890 uv run python -m backend.main
> ```

### 5. 配置 LLM 过滤（可选）

进入 **LLM 配置** → 新增配置，填写 OpenAI 兼容接口的 Base URL、API Key 和模型名，点「测试」验证，设为默认。

支持任意 OpenAI 兼容接口，如 DeepSeek、阿里云 Qwen 等。视觉过滤需模型支持多模态（如 GPT-4o、Qwen-VL）。

### 6. 创建搜索配置

进入 **搜索配置** → 新建配置：

| 字段 | 说明 |
|------|------|
| 关键词 / 话题 ID | 关键词搜索填关键词；话题抓取填话题的 `ch_id` |
| 搜索类型 | `关键词搜索` 或 `话题抓取` |
| 排序方式 | 综合 / 最多点赞 / 最新 |
| 发布时间 | 不限 / 一天内 / 一周内 / 半年内 |
| 内容类型 | 不限 / 视频 / 图文 |
| 采集数量 | 目标新内容条数（去重后，不足时自动翻页补齐） |
| 定时 Cron | Cron 表达式，如 `0 9 * * 1-5`（工作日 9 点） |
| 通知渠道 | 绑定飞书群，留空则使用默认渠道 |
| LLM 过滤 | 开启后用 AI 判断内容相关性 |

点卡片上的 **▶ 立即执行**，切换到 **任务记录** 查看执行状态和采集明细。

---

## 数据存储

| 位置 | 内容 |
|------|------|
| `douyin.db` | SQLite 数据库，存储所有配置和记录 |
| `downloads/` | 下载的视频（`.mp4`）和图片（`.jpg`）文件（默认路径，可在系统设置修改） |
| `downloads/logs/YYYY-MM-DD.jsonl` | 每日采集明细日志 |

## 页面导航

| 页面 | 功能 |
|------|------|
| 搜索配置 | 管理采集任务，手动触发执行 |
| 任务记录 | 查看每次执行状态、新内容数 / 下载数 / 推送数；点「详情」展开采集明细；支持按配置 / 状态 / 时间 / 有无数据筛选 |
| LLM 配置 | 配置相关性过滤的 AI 接口 |
| Cookie 管理 | 管理抖音账号 Cookie |
| 通知渠道 | 配置飞书机器人推送目标群 |
| 系统设置 | 配置文件下载目录 |

---

## 技术架构

### 搜索实现

抖音 Web 搜索 API 需要 `a_bogus` 动态签名参数，难以直接伪造。本项目通过 Playwright 驱动真实 Chromium 浏览器搜索：

1. 每次搜索任务启动一个无头 Chromium 实例，注入登录 Cookie
2. 访问抖音搜索页，通过 `page.route` 拦截 `general/search/single` 的响应，直接读取 JSON 数据
3. 滚动页面触发翻页，直到凑够目标数量的新内容
4. 浏览器自己生成签名、自己发请求，完全绕过签名问题

### 搜索去重逻辑

每个搜索配置维护独立的 `SeenRecord` 集合。搜索时将历史已见 `aweme_id` 传入搜索器，搜索器内部实时过滤，不足目标数量则自动翻页，直到累计够目标数量的新内容或 API 无更多数据（最多搜索目标数量 × 5 条）。

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 · FastAPI · SQLModel · APScheduler · httpx |
| 前端 | React 18 · TypeScript · Vite · TailwindCSS v4 |
| 搜索 | Playwright Chromium（无头浏览器 + 响应拦截） |
| 数据库 | SQLite（通过 SQLModel/SQLAlchemy） |
| 包管理 | uv（Python）· npm（前端） |

### 项目结构

```
douyin-crawler/
├── backend/
│   ├── crawler/
│   │   ├── client.py        # HTTP 客户端（请求头、文件下载）
│   │   ├── search.py        # 关键词 / 话题搜索（持续翻页去重）
│   │   ├── downloader.py    # 视频 / 图片下载
│   │   └── sign_server.py   # 签名服务（Playwright 拦截 a_bogus）
│   ├── notify/
│   │   └── feishu.py        # 飞书机器人推送（卡片消息、图片上传）
│   ├── routers/             # FastAPI 路由（configs/tasks/logs/cookies/channels/llm）
│   ├── database.py          # SQLite 引擎
│   ├── models.py            # 数据模型（SQLModel）
│   ├── scheduler.py         # APScheduler 定时任务管理
│   ├── task_runner.py       # 任务执行流水线（搜索→去重→LLM→下载→推送→日志）
│   ├── llm.py               # LLM 相关性检测
│   └── logger.py            # JSONL 采集日志读写
├── frontend/                # React 前端（构建产物由 FastAPI 静态服务）
├── tests/                   # 单元测试
├── get_cookie.py            # 扫码获取抖音 Cookie 工具
└── douyin.db                # SQLite 数据库（自动创建）
```

## 注意事项

- 本项目仅供个人学习和研究使用，请遵守抖音平台相关规定
- Cookie 失效时任务会显示明确的诊断原因，重新运行 `get_cookie.py` 获取新 Cookie 即可
- 签名服务（`sign_server.py`）需保持运行，重启后端时无需重启签名服务
- 飞书机器人需先在开放平台开启 `im:message` 权限并通过审核
- LLM 视觉过滤需要模型支持多模态（如 GPT-4o、Qwen-VL）
