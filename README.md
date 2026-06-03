# 抖音内容采集与飞书推送系统

按关键词 / 话题搜索抖音内容，自动下载图片和视频，通过飞书自建应用机器人推送到指定群聊，支持 LLM 相关性过滤和定时任务。

## 功能特性

- **多种采集方式**：关键词搜索、话题抓取，支持排序/时间/内容类型过滤
- **闹钟式定时调度**：每天、工作日、每周指定、每隔 N 小时，支持多个执行时间点
- **LLM 相关性过滤**：接入 OpenAI 兼容接口，用封面图（视觉）+ 文字描述判断相关性
- **飞书机器人推送**：通过自建应用机器人发送卡片消息到指定群聊，支持多渠道
- **多账号 Cookie**：管理多个抖音账号 Cookie，支持设默认账号
- **采集去重**：基于 `SeenRecord` 表，按配置维度去重，历史推送过的内容不再重复
- **本地日志**：采集明细按日期存储为 JSONL 文件，支持在 UI 中查看和删除
- **Web UI**：React + TailwindCSS 管理界面，支持配置增删改、任务手动触发、日志查看

## 快速开始

### 1. 安装依赖

```bash
# Python 依赖
uv sync

# 前端构建
cd frontend && npm install && npm run build && cd ..
```

### 2. 启动服务

```bash
uv run python -m backend.main
```

访问 **http://localhost:8000**

### 3. 配置向导（按顺序）

#### ① 获取抖音 Cookie

```bash
# 方式一：扫码自动获取（推荐）
uv run python get_cookie.py

# 方式二：手动获取
# 浏览器打开 https://www.douyin.com 并登录
# F12 → Console → 执行 copy(document.cookie)
```

进入 **Cookie 管理** → 新增账号，粘贴 Cookie，设为默认。

#### ② 配置飞书机器人

前置准备：
1. 在[飞书开放平台](https://open.feishu.cn)创建**自建应用**
2. 开启权限：`im:message`（发送消息）
3. 将机器人添加到目标群聊

进入 **通知渠道** → 新增渠道，填写 App ID / App Secret，保存后点「查询机器人所在群」选择目标群。

#### ③ 配置 LLM 过滤（可选）

进入 **LLM 配置** → 新增配置，填写 OpenAI 兼容接口的 Base URL、API Key 和模型名，点「测试」验证连通性，设为默认。

支持任意 OpenAI 兼容接口，如 DeepSeek、阿里云 Qwen 等。

#### ④ 创建搜索配置

进入 **搜索配置** → 新建配置：

| 字段 | 说明 |
|------|------|
| 关键词 / 话题 ID | 关键词搜索填关键词；话题抓取填话题的 `ch_id` |
| 搜索类型 | `关键词搜索` 或 `话题抓取` |
| 排序方式 | 综合 / 最多点赞 / 最新 |
| 发布时间 | 不限 / 一天内 / 一周内 / 半年内 |
| 内容类型 | 不限 / 视频 / 图文 |
| 采集数量 | 单次最多采集条数 |
| 执行时间 | 闹钟式定时，支持多个时间点 |
| 通知渠道 | 绑定指定飞书群，留空则使用默认渠道 |
| LLM 过滤 | 开启后用 AI 判断内容相关性 |

#### ⑤ 测试运行

点卡片上的 **▶ 立即执行**，切换到 **任务记录** 查看执行状态。

---

## 数据存储

| 位置 | 内容 |
|------|------|
| `douyin.db` | SQLite 数据库，存储所有配置和记录 |
| `downloads/` | 下载的视频（`.mp4`）和图片（`.jpg`）文件 |
| `downloads/logs/YYYY-MM-DD.jsonl` | 每日采集明细日志 |

下载目录可在 **系统设置** 中修改。

## 页面导航

| 页面 | 功能 |
|------|------|
| 搜索配置 | 管理采集任务，手动触发执行 |
| 任务记录 | 查看每次执行状态和统计数据 |
| 采集日志 | 查看每条采集内容的详细记录，按日期管理 |
| LLM 配置 | 配置相关性过滤的 AI 接口 |
| Cookie 管理 | 管理抖音账号 Cookie |
| 通知渠道 | 配置飞书机器人推送目标群 |
| 系统设置 | 配置文件下载目录 |

## 开发

### 运行测试

```bash
uv run pytest tests/ -v
```

当前 112 个测试用例，覆盖：爬虫核心、LLM 过滤、去重逻辑、飞书推送、路由 CRUD、日志读写。

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 · FastAPI · SQLModel · APScheduler · httpx |
| 前端 | React 18 · TypeScript · Vite · TailwindCSS v4 |
| 数据库 | SQLite（通过 SQLModel/SQLAlchemy） |
| 包管理 | uv（Python）· npm（前端） |

### 项目结构

```
douyin-crawler/
├── backend/
│   ├── crawler/         # 抖音爬虫（HTTP 客户端、关键词/话题搜索、文件下载）
│   ├── notify/          # 飞书机器人推送（卡片消息、图片上传）
│   ├── routers/         # FastAPI 路由（configs/tasks/logs/cookies/channels/llm）
│   ├── database.py      # SQLite 引擎，路径固定在项目根目录
│   ├── models.py        # 数据模型（SQLModel）
│   ├── schemas.py       # 请求/响应 Schema（Pydantic）
│   ├── scheduler.py     # APScheduler 定时任务管理
│   ├── task_runner.py   # 任务执行流水线（搜索→去重→LLM→下载→推送→日志）
│   ├── llm.py           # LLM 相关性检测（支持封面图视觉判断）
│   └── logger.py        # JSONL 采集日志读写
├── frontend/            # React 前端（构建产物由 FastAPI 静态服务）
├── tests/               # 单元测试（112 个）
├── get_cookie.py        # 扫码获取抖音 Cookie 工具
└── douyin.db            # SQLite 数据库（自动创建）
```

## 注意事项

- 本项目仅供个人学习和研究使用
- Cookie 有效期约数天至数周，失效后需重新获取
- 飞书机器人需先在开放平台开启 `im:message` 权限并通过审核
- LLM 视觉过滤需要模型支持多模态（如 GPT-4o、Qwen-VL）
