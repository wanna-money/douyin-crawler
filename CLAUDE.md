# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# 启动/停止服务（后台运行，前端有变更时自动重新构建）
./start.sh
./stop.sh

# 直接前台运行后端
uv run python -m backend.main

# 前端开发
cd frontend && npm run dev       # 开发服务器（Vite HMR）
cd frontend && npm run build     # 生产构建到 frontend/dist/

# 运行测试
uv run pytest                    # 全部测试
uv run pytest tests/test_routers.py          # 单个文件
uv run pytest tests/test_routers.py::test_x  # 单个测试

# 获取/刷新抖音 Cookie
uv run python get_cookie.py

# 代理（飞书推送需要时）
HTTPS_PROXY=http://127.0.0.1:7890 uv run python -m backend.main
```

## 架构概览

**单进程 FastAPI 后端**，静态服务前端 `frontend/dist/`，SQLite 持久化，APScheduler 内嵌定时任务。

### 任务流水线（`backend/task_runner.py`）

`run_task(config_id)` 是核心入口，被定时调度器和 `POST /api/tasks/trigger/{id}` 共同调用。流程：

1. 读 `SearchConfig` + 默认 Cookie + 通知渠道
2. `DouyinSearcher` 通过 Playwright 无头 Chromium 拦截抖音搜索响应取数据（完全绕过 `a_bogus` 签名，不再使用 sign_server）
3. 去重：对比 `SeenRecord` 表，不足目标数自动翻页（最多翻 5 页避免触发风控）
4. 可选 LLM 相关性过滤（`backend/llm.py`，OpenAI 兼容接口）
5. 下载图片/视频封面到 `downloads/`（路径可在系统设置修改）；视频只下载封面图，不下载视频本体
6. 飞书卡片推送（`backend/notify/feishu.py`，`FeishuBotNotifier`，自建应用机器人）
7. **推送成功后**才写入 `SeenRecord`，避免推送失败导致内容永久丢失
8. 写 JSONL 采集日志（`downloads/logs/YYYY-MM-DD.jsonl`）
9. 写 `TaskRecord` / `DownloadRecord`

### 搜索实现（`backend/crawler/search.py`）

`DouyinSearcher.search_keyword()` 在独立线程的新 event loop 里运行 Playwright，不阻塞 uvicorn 主 loop。拦截 `general/search/single` 和 `general/search/stream` 两种接口，支持 chunked 响应格式解析。话题搜索（`search_hashtag`）使用 HTTP API 直接请求，不走 Playwright。

### Cron 调度（`backend/scheduler.py`）

使用 APScheduler `CronTrigger`。`cron` 字段支持分号分隔多段（如 `0 9 * * *;0 18 * * *`）。每次 CRUD 配置后调用 `sync_jobs()` 全量重建任务。

**注意**：`day_of_week` 使用 `mon-fri` 表示工作日（APScheduler 中 `1-5` = 周二到周六，是已知的历史 Bug，scheduler.py 内有向后兼容转换）。

### 数据模型（`backend/models.py`）

核心表：`SearchConfig`、`TaskRecord`、`DownloadRecord`（单次下载记录）、`SeenRecord`（去重集合，按 `config_id` 隔离）、`CookieAccount`、`NotifyChannel`、`LLMConfig`、`AppSetting`。

### 前端结构

React 18 + TypeScript + TailwindCSS v4 + Vite。路由为页面级组件（`src/pages/`），与后端通信全部通过 `src/api/client.ts` 的 axios 封装。`SchedulePicker` 组件负责将 UI 模式（daily/weekday/weekly/interval/advanced）转换为 cron 字符串。

### 飞书通知渠道（`backend/notify/feishu.py`）

`FeishuBotNotifier`（别名 `FeishuNotifier`）使用自建飞书应用机器人（app_id + app_secret + chat_id），通过 lark-oapi SDK 构建 Schema 2.0 卡片消息。`NotifyChannel.channel_type` 目前固定为 `feishu_bot`。tenant_access_token 有内存缓存（过期前 6 分钟刷新）。

### 测试结构

测试使用内存 SQLite 引擎（`get_engine(":memory:")`）+ `create_app(engine=engine)` 注入，不依赖真实数据库。Playwright/Cookie/LLM/飞书相关测试均 mock 外部调用。`pyproject.toml` 配置 `asyncio_mode = "auto"`，异步测试直接用 `async def test_*`。

### 签名服务（遗留）

`backend/crawler/sign_server.py` 是早期独立 HTTP 签名服务（端口 18690），当前主流程已改为 Playwright 直接拦截，不再依赖此服务。代码保留供参考，`.pids/sign_server.pid` 为其进程 PID 文件。
