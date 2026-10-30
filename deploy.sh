#!/bin/bash
# 同步 Ti600 开发源 -> 系统盘运行副本，并重启 launchd 服务
# 用法: ./deploy.sh   (改完 server.py/index.html 后执行一次)
set -e
SRC="/Volumes/Ti600/dotfile/mac-mini-monitor"
DST="$HOME/Doubao/apps/mac-mini-monitor"
LABEL="com.persilee.mac-mini-monitor"

if [ ! -d "$SRC" ]; then
  echo "错误: Ti600 未挂载或目录不存在 ($SRC)" >&2
  exit 1
fi

mkdir -p "$DST"
cp "$SRC/server.py" "$SRC/index.html" "$DST/"
echo "已同步: $SRC -> $DST"

UID_NUM=$(id -u)
launchctl kickstart -k gui/$UID_NUM/$LABEL 2>/dev/null \
  && echo "服务已重启 (launchd: $LABEL)" \
  || echo "警告: kickstart 失败，请检查 launchd 任务"
sleep 2
curl -s -m 3 http://127.0.0.1:8080/api >/dev/null \
  && echo "仪表盘正常: http://127.0.0.1:8080" \
  || echo "警告: 服务未响应，检查日志 /tmp/mac-mini-monitor.log"
