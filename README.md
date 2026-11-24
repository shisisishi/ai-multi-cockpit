# AI Multi Cockpit

[English](README.en.md) | **简体中文**

Windows 原生 **AI 编码工具多账号并发 + Cockpit 风格额度总览桌面面板**，同时覆盖 **Google Antigravity** 与 **OpenAI Codex（桌面版 & CLI）**。

> 配合 [antigravity-multi-windows](https://github.com/shisisishi/antigravity-multi-windows) 使用可获得完整的 Antigravity 多账号自动同步体验；单账号环境同样开箱即用。

---

## 核心特性

### 1. Cockpit 风格独立桌面应用面板（零依赖）
- **无地址栏桌面窗口**：基于 Python 3 标准库本地服务（仅监听 `127.0.0.1`）+ Edge/Chrome `--app` 独立应用外壳启动，外观简洁如原生工具，双击桌面快捷方式即可打开。
- **实时多账号额度总览**：
  - **Antigravity**：通过官方插件 Sidecar（`ai-multi-cockpit-bridge`）上报每个账号的套餐等级（如 `Google AI Pro` / `Cloud PAYG`）、各模型池（Gemini / Claude & GPT 等）的 **5 小时额度** 与 **每周额度** 剩余百分比及精确重置倒计时。
  - **OpenAI Codex**：通过官方 `codex app-server` JSON-RPC 协议并发拉取每个配置的套餐（`Plus` / `Pro` / `Team` / `Free`）、**5 小时额度**、**每周额度**、重置倒计时、扩展模型池与 Credits 余额。
- **运行状态与预警**：实时展示各账号运行状态、进程数、项目/对话/会话计数、Antigravity 同步池状态、以及 `<= 20%` 低额度预警。
- **隐私保护与自定义**：一键开启**隐私模糊模式**（截图/录屏时隐藏账号名与脱敏邮箱）、中英文切换、暗/亮色主题切换、账号别名与备忘编辑。

### 2. OpenAI Codex 并发多开（免 UAC，无需新建系统用户）
- **真正同时多开 Codex Desktop & CLI**：利用官方 `CODEX_HOME` 环境变量与 Chromium `--user-data-dir` 双重隔离，多个 Codex 桌面窗口与终端 CLI 可**同时并排运行**，互不串号、互不锁死。
- **共享配置按需同步**：创建独立配置时自动从默认 `~/.codex` 复制/同步非敏感的 `config.toml`、`skills/` 和 `AGENTS.md`，同时保持 `auth.json` 与状态库完全独立。
- **独立代理 & 桌面快捷方式**：支持为每个 Codex 配置设置专属代理，并一键生成无黑窗桌面快捷方式。

### 3. 安全与合规设计
- **零凭据窃取 / 零绕过**：不读取或解析 `auth.json` 令牌，不读取 Windows 凭据管理器，不绕过 OAuth 登录流程；所有登录与额度查询均走官方路径（`codex login`、`codex app-server`、Antigravity 官方插件 Sidecar）。
- **本地安全防护**：后端仅绑定 `127.0.0.1`，强制校验 `Host` 头及每会话随机 `X-Cockpit-Token` CSRF 令牌，防止外部网页跨域调用本地接口。

---

## 目录结构

```text
ai-multi-cockpit/
├─ Launch-Cockpit.cmd / .vbs / .ps1     # 独立桌面应用模式启动器（无黑窗）
├─ Install-DesktopShortcut.ps1          # 创建桌面快捷方式（免 UAC）
├─ cockpit/
│  ├─ server.py                         # 零依赖 Python 3 本地后端与额度采集器
│  └─ web/                              # Cockpit 风格前端（index.html / styles.css / app.js）
├─ codex/
│  ├─ Codex-Multi.ps1                   # Codex Desktop & CLI 多账号管理器
│  ├─ SilentLaunchCodex.vbs             # 桌面快捷方式静默启动脚本
│  └─ Open-CodexManager.cmd             # 命令行交互菜单
├─ plugins/
│  └─ ai-multi-cockpit-bridge/          # Antigravity 官方 Sidecar 额度桥接插件
└─ scripts/
   └─ Install-AgyBridge.ps1             # 一键部署桥接插件至主账号及所有多开子账号
```

---

## 环境要求

- Windows 10 / 11（内置 Windows PowerShell 5.1）
- Python 3.10+（仅使用标准库，无需 `pip install`）
- Node.js 18+（仅用于 Antigravity 额度桥接 Sidecar 插件）
- Microsoft Edge 或 Google Chrome（用于 `--app` 无地址栏桌面窗口模式）
- 已安装 **OpenAI Codex**（MSIX 桌面版和/或 CLI）和/或 **Google Antigravity 2.0**

---

## 快速开始

### 1. 获取并解压
克隆本仓库或从 [Releases](../../releases) 下载最新 ZIP 并解压到任意固定目录（例如 `D:\Tools\ai-multi-cockpit`）。

### 2. 创建桌面快捷方式 & 部署 Antigravity 额度桥接插件
在解压目录中打开 PowerShell 运行：

```powershell
# 1. 创建桌面快捷方式 "AI Multi Cockpit"（免 UAC）
powershell -ExecutionPolicy Bypass -File .\Install-DesktopShortcut.ps1

# 2. 部署 Antigravity 官方额度桥接插件（自动覆盖主账号与已配置的 AntigravityMulti 子账号）
powershell -ExecutionPolicy Bypass -File .\scripts\Install-AgyBridge.ps1
```

### 3. 启动 Cockpit 桌面面板
直接双击桌面的 **AI Multi Cockpit** 快捷方式（或双击仓库根目录的 `Launch-Cockpit.cmd`）。

---

## Codex 多开常用命令

除了在 Cockpit 面板里直接点击 **＋ 新增 Codex 账号** 外，也可以通过 PowerShell 或 `codex\Open-CodexManager.cmd` 操作：

```powershell
# 查看所有 Codex 配置
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action List

# 创建新的独立配置（自动复制 config.toml / skills / AGENTS.md）
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action Create -Name acc2 -Label "Codex 账号2"

# 打开官方登录终端（codex login）
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action Login -Name acc2

# 并排启动第二个 Codex 桌面版窗口
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action LaunchDesktop -Name acc2

# 并排启动第二个 Codex CLI 终端
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action LaunchCli -Name acc2

# 创建独立桌面快捷方式
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action CreateShortcut -Name acc2

# 将默认 ~/.codex 的 skills/配置同步到所有独立配置
powershell -ExecutionPolicy Bypass -File .\codex\Codex-Multi.ps1 -Action SyncShared -Name all
```

独立配置默认存储在 `%LOCALAPPDATA%\AIMultiCockpit\codex-profiles\<配置名>\` 下，删除独立配置不会影响默认的 `%USERPROFILE%\.codex`。

---

## 常见问题

1. **Antigravity 卡片提示“尚无额度快照”？**
   点击页面右上角或 Antigravity 区的 **安装/同步额度桥接插件**，确保对应 Antigravity 账号已打开并登录；插件会每 30 秒自动写入脱敏额度快照。
2. **如何与 `antigravity-multi-windows` 配合使用？**
   若本机已安装 [antigravity-multi-windows](https://github.com/shisisishi/antigravity-multi-windows)（位于 `C:\ProgramData\AntigravityMulti`），AI Multi Cockpit 会自动发现主账号与全部隔离账号（`AgyAcc2..N`）、实时同步池状态，并支持在面板中一键启动账号与触发增量同步。
3. **关闭桌面窗口后后台服务占资源吗？**
   后台 Python 进程仅在本地休眠等待请求，空闲内存极低（约 20 MB）；如需手动停止，可向本地 `/api/shutdown` 发送请求或结束 `pythonw.exe` 进程。

---

## 开源协议

[MIT License](LICENSE)
