#!/bin/bash

cd "$(dirname "$0")"

PID_DIR=".pids"

stop_service() {
  local name=$1
  local pid_file="$PID_DIR/$name.pid"

  if [ ! -f "$pid_file" ]; then
    echo "[未运行] $name"
    return
  fi

  local pid
  pid=$(cat "$pid_file")

  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "[停止] $name (PID $pid)"
  else
    echo "[已停止] $name (PID $pid 不存在)"
  fi

  rm -f "$pid_file"
}

stop_service backend

pkill -f "uvicorn backend.main" 2>/dev/null && echo "[清理] 残留 backend 进程" || true

echo "✅ 所有服务已停止"
