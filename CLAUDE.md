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
2. 启动持久签名服务进程（`backend/crawler/sign_server.py`，端口 18690，进程级单例，重启后端无需重启）
3. `DouyinSearcher` 通过 Playwright 无头 Chromium 拦截抖音搜索响应取数据（绕过 `a_bogus` 签名）
4. 去重：对比 `SeenRecord` 表，不足目标数自动翻页（最多搜索目标数 × 5 条）
5. 可选 LLM 相关性过滤（`backend/llm.py`，OpenAI 兼容接口）
6. 下载图片/视频到 `downloads/`（路径可在系统设置修改）
7. 飞书卡片推送（`backend/notify/feishu.py`，自建应用机器人）
8. 写 JSONL 采集日志（`downloads/logs/YYYY-MM-DD.jsonl`）
9. 写 `TaskRecord` / `DownloadRecord`

### Cron 调度（`backend/scheduler.py`）

使用 APScheduler `CronTrigger`。`cron` 字段支持分号分隔多段（如 `0 9 * * *;0 18 * * *`）。每次 CRUD 配置后调用 `sync_jobs()` 全量重建任务。

**注意**：`day_of_week` 使用 `mon-fri` 表示工作日（APScheduler 中 `1-5` = 周二到周六，是已知的历史 Bug，scheduler.py 内有向后兼容转换）。

### 数据模型（`backend/models.py`）

核心表：`SearchConfig`、`TaskRecord`、`DownloadRecord`（单次下载记录）、`SeenRecord`（去重集合，按 `config_id` 隔离）、`CookieAccount`、`NotifyChannel`、`LLMConfig`、`AppSetting`。

### 前端结构

React 18 + TypeScript + TailwindCSS v4 + Vite。路由为页面级组件（`src/pages/`），与后端通信全部通过 `src/api/client.ts` 的 axios 封装。`SchedulePicker` 组件负责将 UI 模式（daily/weekday/weekly/interval/advanced）转换为 cron 字符串。

### 签名服务进程

`backend/crawler/sign_server.py` 是独立 HTTP 服务（端口 18690），由 `task_runner.py` 在首次任务时惰性启动并常驻。它维护一个持久 Playwright 页面，每次签名请求只需约 3s（冷启动约 15s）。后端重启不影响已运行的签名服务进程。
