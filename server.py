#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mac mini 监控数据服务 (macOS 26 / M5 Pro)
- 每 1.5 秒采集: CPU占用 / 内存 / 网络速率 / 磁盘 / 热压力 / 时间 / 运行时间
- HTTP: GET /  -> 仪表盘页面;  GET /api -> JSON 数据
- 不依赖 SMC 温度接口（macOS 26 已收紧），全部走系统命令，非 root 可运行
"""
import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8080
INTERVAL = 1.5  # 采集间隔秒

BASE_DIR = Path(__file__).resolve().parent

# ---------- 数据采集 ----------

def run(cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=6)
        return p.stdout
    except Exception:
        return ""


def parse_cpu():
    """top 采样: busy = user + sys (%, 与 Activity Monitor 口径相近)"""
    out = run("top -l 1 -n 0")
    m = re.search(r"CPU usage:\s*([\d.]+)%\s*user,\s*([\d.]+)%\s*sys", out)
    if not m:
        return None
    busy = round(float(m.group(1)) + float(m.group(2)), 1)
    return {"pct": busy, "user": float(m.group(1)), "sys": float(m.group(2))}


def parse_mem():
    """vm_stat (macOS 26, 16KB页): 可用 = free + inactive(可回收缓存) + speculative"""
    total = 0
    try:
        total = int(run("sysctl -n hw.memsize").strip())
    except Exception:
        pass
    out = run("vm_stat")
    page = 4096
    m = re.search(r"page size of (\d+)", out)
    if m:
        page = int(m.group(1))
    free = inactive = speculative = 0
    m = re.search(r"Pages free:\s*(\d+)", out)
    if m:
        free = int(m.group(1))
    m = re.search(r"Pages inactive:\s*(\d+)", out)
    if m:
        inactive = int(m.group(1))
    m = re.search(r"Pages speculative:\s*(\d+)", out)
    if m:
        speculative = int(m.group(1))
    used = max(total - (free + inactive + speculative) * page, 0)
    pct = round(used / total * 100, 1) if total else 0
    press = "正常"
    mp = run("/usr/bin/memory_pressure")
    m = re.search(r"Memory pressure:\s*(\w+)", mp)
    if m:
        press = m.group(1)
    return {"used": used, "total": total, "pct": pct, "press": press}


class NetSnap:
    def __init__(self):
        self.in_bytes = 0
        self.out_bytes = 0
        self.ts = 0


def net_total():
    """所有 en* 接口累计字节 (netstat -ib)"""
    out = run("netstat -ib")
    tin = tout = 0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[0].startswith("en"):
            try:
                tin += int(parts[6])   # Ibytes
                tout += int(parts[9])  # Obytes
            except (ValueError, IndexError):
                pass
    return tin, tout


def parse_net(prev: NetSnap) -> dict:
    now_tin, now_tout = net_total()
    now = time.time()
    if prev.ts:
        dt = now - prev.ts
        down = max(now_tin - prev.in_bytes, 0) / dt if dt > 0 else 0
        up = max(now_tout - prev.out_bytes, 0) / dt if dt > 0 else 0
        # 计数器重置保护
        if now_tin < prev.in_bytes or now_tout < prev.out_bytes:
            down = up = 0.0
    else:
        down = up = 0.0
    prev.in_bytes, prev.out_bytes, prev.ts = now_tin, now_tout, now
    return {"down": down, "up": up}


def parse_disk():
    """返回卷列表(Ti600 + 系统盘), main 为 Ti600 优先"""
    out = run("df -k")
    vols = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        if parts[8].startswith("/Volumes/Ti600"):
            vols.append({"label": "Ti600", "used": int(parts[2]) * 1024,
                         "total": int(parts[1]) * 1024, "pct": int(parts[4].rstrip("%"))})
        elif parts[8] == "/System/Volumes/Data":
            vols.append({"label": "系统盘", "used": int(parts[2]) * 1024,
                         "total": int(parts[1]) * 1024, "pct": int(parts[4].rstrip("%"))})
    if not vols:
        return None
    main = next((v for v in vols if v["label"] == "Ti600"), vols[0])
    return {"main": main, "volumes": vols}


def parse_therm():
    """pmset -g therm: 热压力等级"""
    out = run("pmset -g therm")
    if "No thermal warning level" in out:
        return "正常"
    if "CPU_Scheduler_Limit" in out or "thermal warning" in out.lower():
        return "偏高(限频)"
    return "未知"


def parse_uptime():
    out = run("/usr/bin/uptime")
    m = re.search(r"up\s+([^,]+),", out)
    return m.group(1).strip() if m else "?"


# ---------- 采集循环 ----------

data = {
    "cpu": None, "mem": None, "net": {"down": 0, "up": 0},
    "disk": None, "therm": "正常", "time": "", "uptime": "?",
    "ok": False,
}
net_snap = NetSnap()
lock = threading.Lock()


def collect():
    global net_snap
    while True:
        try:
            cpu = parse_cpu()
            mem = parse_mem()
            net = parse_net(net_snap)
            disk = parse_disk()
            therm = parse_therm()
            uptime = parse_uptime()
            now = time.strftime("%H:%M:%S")
            snapshot = {
                "cpu": cpu, "mem": mem, "net": net, "disk": disk,
                "therm": therm, "time": now, "uptime": uptime, "ok": True,
            }
            with lock:
                data.update(snapshot)
        except Exception:
            pass
        time.sleep(INTERVAL)


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store, no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api":
            with lock:
                payload = json.dumps(data).encode("utf-8")
            self._send(payload, "application/json; charset=utf-8")
        elif path == "/":
            page = (BASE_DIR / "index.html").read_bytes()
            self._send(page, "text/html; charset=utf-8")
        else:
            self.send_response(404)
            self.end_headers()


def main():
    threading.Thread(target=collect, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Mac mini monitor: http://{HOST}:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
