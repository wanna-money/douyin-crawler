#!/bin/bash
set -e

cd "$(dirname "$0")"

PID_DIR=".pids"
mkdir -p "$PID_DIR" logs

# ── 前端构建（源码比 dist 新时才重新构建）────────────────
FRONTEND_SRC="frontend/src"
FRONTEND_DIST="frontend/dist/index.html"

should_build=false
if [ ! -f "$FRONTEND_DIST" ]; then
  should_build=true
  echo "[前端] dist 不存在，需要构建"
elif [ -n "$(find "$FRONTEND_SRC" -newer "$FRONTEND_DIST" 2>/dev/null)" ]; then
  should_build=true
  echo "[前端] 源码有变更，需要重新构建"
else
  echo "[前端] dist 已是最新，跳过构建"
fi

if [ "$should_build" = true ]; then
  echo "[前端] 构建中..."
  cd frontend && npm run build && cd ..
  echo "[前端] 构建完成"
fi

# ── 启动后端 ─────────────────────────────────────────────
if [ -f "$PID_DIR/backend.pid" ] && kill -0 "$(cat "$PID_DIR/backend.pid")" 2>/dev/null; then
  echo "[已运行] backend (PID $(cat "$PID_DIR/backend.pid"))"
else
  echo "[启动] backend..."
  nohup uv run python -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}" >> logs/backend.log 2>&1 &
  echo $! > "$PID_DIR/backend.pid"
  echo "  PID $! → logs/backend.log"
fi

echo ""
echo "等待服务就绪..."
for i in $(seq 1 15); do
  if curl -s -o /dev/null "http://localhost:${PORT:-8000}/api/tasks" 2>/dev/null; then
    echo "✅ 服务已就绪：http://localhost:${PORT:-8000}"
    exit 0
  fi
  sleep 1
done

echo "⚠️  服务启动超时，请查看日志："
echo "  tail -f logs/backend.log"
exit 1
