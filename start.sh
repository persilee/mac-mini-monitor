#!/bin/bash
# Mac mini 监控仪表盘启动脚本
# 用法: ./start.sh   (停止: 重新运行本脚本即重启; 或 pkill -f "server.py")
cd "$(dirname "$0")"

PYTHON=/usr/bin/python3   # 系统自带 python，稳定可用
[ -x "$PYTHON" ] || PYTHON=python3

# 停掉旧实例（按端口找，避免误杀）
lsof -ti :8080 | xargs kill 2>/dev/null
sleep 1

# 启动数据服务
nohup "$PYTHON" server.py > /tmp/mac-mini-monitor.log 2>&1 &
sleep 1.5

# 打开仪表盘（默认浏览器）
open "http://localhost:8080"

echo "仪表盘已启动: http://localhost:8080"
echo "日志: /tmp/mac-mini-monitor.log"
echo "停止: pkill -f server.py"
