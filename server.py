#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mac mini 监控服务 · 精简大字版（wokyis M5 小屏）

只采集关键信息: CPU / 内存 / CPU温度(MFC) / 散热状态 / 运行时长
温度来源: Macs Fan Control 主窗口(AppleScript UI 读取, 需已授权辅助功能, 主窗口保持打开)
"""
import json
import os
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

HOST, PORT = "127.0.0.1", 8080
MEM_TOTAL = 51539607552   # 48 GB
PAGE = 16384              # macOS 26 页大小 16KB


def run(cmd, timeout=6):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "").strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def parse_cpu():
    """top 采样 user + sys"""
    out = run("top -l 1 -n 0 | rg 'CPU usage' | tail -1")
    m = re.search(r"(\d+(?:\.\d+)?)%\s+user.*?(\d+(?:\.\d+)?)%\s+sys", out)
    if not m:
        return None
    user, sys_ = float(m.group(1)), float(m.group(2))
    return {"user": round(user, 1), "sys": round(sys_, 1), "pct": round(user + sys_, 1)}


def parse_mem():
    """vm_stat: 可用 = free + inactive + speculative"""
    out = run("vm_stat")
    if not out:
        return None

    def g(k):
        m = re.search(k + r":\s+(\d+)", out)
        return int(m.group(1)) * PAGE if m else 0

    free = g("Pages free")
    inactive = g("Pages inactive")
    spec = g("Pages speculative")
    used = max(0, min(MEM_TOTAL, MEM_TOTAL - (free + inactive + spec)))
    return {"used": used, "total": MEM_TOTAL, "pct": round(used / MEM_TOTAL * 100, 1)}


_TEMP_CACHE = {"at": 0.0, "val": None}


def parse_mfc_temp():
    """读取 Macs Fan Control 主窗口传感器表（3 秒缓存）

    MFC 窗口 AX 结构: splitter group 1 -> table 1（两列: 传感器名/温度值）
    读取 title 交替返回 [名称, 值, 名称, 值, ...]，优先取 CPU Core Average。
    需要: 辅助功能已授权 + MFC 主窗口保持打开（可最小化）。
    """
    now = time.time()
    if now - _TEMP_CACHE["at"] < 3:
        return _TEMP_CACHE["val"]
    script = ('tell application "System Events" to tell process "Macs Fan Control" '
              'to get title of every static text of table 1 of splitter group 1 of window 1')
    try:
        p = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=8)
        text = p.stdout if p.returncode == 0 else ""
    except Exception:
        text = ""
    val = None
    if text:
        items = [x.strip() for x in text.split(",")]
        pairs = []
        for i in range(0, len(items) - 1, 2):
            # 奇数位是传感器名，偶数位是数值
            name = items[i]
            if name and not name.replace(".", "").isdigit():
                pairs.append((name, items[i + 1]))
        for name, v in pairs:
            if name == "CPU Core Average":
                try:
                    val = float(v)
                    break
                except ValueError:
                    pass
        if val is None:
            for name, v in pairs:
                if "CPU" in name or "Die" in name:
                    try:
                        val = float(v)
                        break
                    except ValueError:
                        pass
        if val is None and pairs:
            try:
                val = float(pairs[0][1])
            except ValueError:
                pass
    _TEMP_CACHE["at"] = now
    _TEMP_CACHE["val"] = val
    return val


def parse_therm():
    """pmset -g therm 热压力等级"""
    out = run("pmset -g therm")
    if not out:
        return "正常"
    if re.search(r"(?:CPU|GPU)_Scheduler_Limit:\s*[1-9]", out):
        return "偏高(限频)"
    return "正常"


def parse_uptime():
    """uptime 原始格式: '8:18'(HH:MM=8小时18分) / '8 mins' / '3 days, 2:34'
    转成无歧义的 '8小时18分' / '3天2小时34分'"""
    out = run("uptime")
    if not out:
        return "--"
    m = re.search(r"up\s+(.+?),\s+\d+\s+user", out)
    raw = m.group(1).strip() if m else ""
    if not raw:
        return "--"

    days = 0
    dm = re.search(r"(\d+)\s+days?", raw)
    if dm:
        days = int(dm.group(1))

    hm = re.search(r"(\d+):(\d+)", raw)
    if hm:
        h, mi = int(hm.group(1)), int(hm.group(2))
        parts = []
        if days:
            parts.append("%d天" % days)
        if h:
            parts.append("%d小时" % h)
        if mi:
            parts.append("%d分" % mi)
        return " ".join(parts) if parts else raw

    mm = re.search(r"(\d+)\s*mins?", raw)
    if mm:
        return "%d分钟" % int(mm.group(1))

    sm = re.search(r"(\d+)\s*secs?", raw)
    if sm:
        return "%d秒" % int(sm.group(1))

    return raw


def collect():
    return {
        "ok": True,
        "time": time.strftime("%H:%M:%S"),
        "cpu": parse_cpu(),
        "mem": parse_mem(),
        "temp": parse_mfc_temp(),
        "therm": parse_therm(),
        "uptime": parse_uptime(),
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api":
            body = json.dumps(collect(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
        elif self.path in ("/", "/index.html"):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
            with open(path, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_response(404)
            body = b"not found"
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("Mac mini monitor: http://%s:%d" % (HOST, PORT))
    HTTPServer((HOST, PORT), Handler).serve_forever()
