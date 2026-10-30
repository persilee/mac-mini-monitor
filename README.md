# Mac mini 小屏监控仪表盘

在 **wokyis M5 雷电5 扩展坞的小屏（1280×720）** 上显示 Mac mini 实时状态的翻页时钟风格仪表盘：**CPU / 内存 / CPU 温度 / 状态** 四张大卡，Dracula 多色渐变 + 圆头环形进度 + 平滑数字过渡。

- 访问地址：`http://127.0.0.1:8080`（本机）
- 数据接口：`http://127.0.0.1:8080/api`（1 秒更新一次 JSON）

---

## 预览

![monitor](./浮引截屏_2026-10-29_17-56-18.png)

## 重启电脑后怎么启动

**不需要手动启动**。服务由 **launchd 守护**（`com.persilee.mac-mini-monitor`）托管：

- **登录时自动启动**（RunAtLoad）
- **进程退出自动拉起**（KeepAlive）——休眠唤醒、意外退出都会自动恢复
- 运行副本在**系统盘** `~/Doubao/apps/mac-mini-monitor/`，不依赖 Ti600 挂载，掉盘也不影响服务

只需保证两点：
1. **MFC 在菜单栏**（温度数据源），建议勾选 MFC 的「开机启动」
2. 浏览器小屏打开 `http://127.0.0.1:8080` 并全屏

验证服务状态：`launchctl list | grep mac-mini-monitor`（第一列为 PID 即运行中）。

---

## 日常改代码（重要）

开发源在 Ti600（git 管理），运行副本在系统盘，**改完代码需要同步一次**：

```bash
cd /Volumes/Ti600/dotfile/mac-mini-monitor
# 改 server.py / index.html ...
git add -A && git commit -m "说明"
./deploy.sh        # 同步到系统盘 + 重启服务 + 自检
```

> 旧的 `./start.sh`（nohup 手动版）保留备用，但日常不再需要。

---

## 前置条件（温度显示必需）

CPU 温度来自 **Macs Fan Control (MFC)**，这是 macOS 26 上唯一能读出 M5 Pro 温度的通道。需要满足：

1. **MFC 已安装**：`brew install --cask macs-fan-control`
2. **辅助功能已授权**（两个都要）：
   - 系统设置 → 隐私与安全性 → 辅助功能 → **勾选 Macs Fan Control**
   - 系统设置 → 隐私与安全性 → 辅助功能 → 点「+」→ `Cmd+Shift+G` 输入 `/usr/bin/osascript` 添加（**launchd 服务进程读温度需要**，一次性）
3. **MFC 在菜单栏常驻**：温度从菜单栏常驻项直接读取（如 `75°C`），主窗口可以关闭；建议勾选 MFC 的「开机启动」

不满足时，温度卡会显示 `--` 和「请打开 MFC」。

---

## launchd 服务管理（可选）

```bash
# 查看状态（第一列为 PID = 运行中）
launchctl list | grep mac-mini-monitor

# 立即重启服务
launchctl kickstart -k gui/$(id -u)/com.persilee.mac-mini-monitor

# 停止服务（停止后不会再自动拉起）
launchctl bootout gui/$(id -u)/com.persilee.mac-mini-monitor

# 重新启用
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.persilee.mac-mini-monitor.plist

# 看日志
tail -f /tmp/mac-mini-monitor.log
```

配置：`~/Library/LaunchAgents/com.persilee.mac-mini-monitor.plist`（项目目录有同款副本）。

---

## 常见问题

**Q：温度卡显示 `--` 或「请打开 MFC」？**
A：确认 MFC 在运行、菜单栏能看到温度项（如 `75°C`）；确认「辅助功能」里已勾选 **MFC** 和 **osascript** 两项（launchd 服务读温度需要 osascript 授权）。主窗口关不关都不影响。

**Q：服务停了 / 重启后没起来？**
A：服务由 launchd 守护，一般会自动拉起。手动查：`launchctl list | grep mac-mini-monitor`；若没起，执行上文的 bootstrap 命令。

**Q：页面没变化 / 颜色不对？**
A：浏览器强刷 `Cmd+Shift+R`（服务端已加 `Cache-Control: no-store`，正常不会缓存）。

**Q：小屏显示不全或太大？**
A：小屏全屏后页面自适应 1280×720；字号、卡片数量都可在 `index.html` 里调整。

**Q：找不到 /Volumes/Ti600？**
A：Ti600 没挂载，检查雷电/USB4 连接线与扩展坞供电；服务本体在系统盘，不受影响。

---

## 目录与 Git

```text
/Volumes/Ti600/dotfile/mac-mini-monitor/          # 开发源（改这里）
├── server.py    # 数据服务（CPU/内存/温度/散热，HTTP :8080）
├── index.html   # 前端仪表盘（四卡、SVG 圆头环形、Dracula 渐变）
├── deploy.sh    # 同步到系统盘运行副本 + 重启服务
├── start.sh     # 手动启动脚本（备用，日常用 launchd）
├── com.persilee.mac-mini-monitor.plist  # launchd 配置副本
└── README.md    # 本说明

/Users/persilee/Doubao/apps/mac-mini-monitor/     # 运行副本（launchd 跑这里）
~/Library/LaunchAgents/com.persilee.mac-mini-monitor.plist   # 已注册的 launchd 配置
```

Git 说明：工作树在 Ti600，**git 元数据在系统盘** `/Users/persilee/Doubao/git/mac-mini-monitor.git`（Ti600 内 `.git` 只是指针文件，因为 Ti600 上删除文件会报 `EXDEV`，git 锁删不掉）。日常 `git add/commit/status` 照常使用即可。

提交习惯：每次改动后 `git add -A && git commit -m "说明" && ./deploy.sh`。
