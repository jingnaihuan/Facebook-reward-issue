# 社群互动发奖中台 — Windows/Mac 双版本改造 设计文档

日期：2026-07-06
作者：石上 / Claude

## 目标

在现有 Mac 版基础上，让「社群互动发奖中台」**同时适配 Mac 与 Windows**，以「一键启动脚本」形态交付给（非技术）运营同事使用，并进行多维全方位测试。

交付形态：**一键启动脚本**（用户自备 Python 3.9+）。不打包成 .app/.exe，不做安装包。
工作方式：**在原项目 `Projects/社群互动发奖中台` 上直接改**，git 管理历史。

## 约束 / 原则

- 核心业务模块（`extract_id` / `dedup` / `language_filter` / `rule_engine` / `export` / `eastblue_parse` / `config_store`）**不改业务逻辑**，只动「启动 + 系统交互 + 编码」这一层。
- 所有平台判断抽成**可在 Mac 上单测**的纯函数，用 monkeypatch 模拟 Windows。
- 现有 36 项测试改造后必须**仍全部通过**。

## 一、发现的真实跨平台缺陷（不只是缺 .bat）

1. **子进程编码 Bug**（`server.py` `_run_eastblue`，约第 40 行）
   `subprocess.Popen(..., text=True)` 未指定 `encoding`。Mac 默认 UTF-8 正常；
   中文版 Windows 默认 cp936/GBK，子进程 `emit()` 输出的含中文进度 JSON 会乱码 / `json.loads` 失败，
   导致步骤 3「拉取 Eastblue」进度解析出错。
   → 修复：显式 `encoding="utf-8", errors="replace"`。

2. **保存对话框仅 Mac**（`server.py` `_choose_save_path`）
   使用 macOS `osascript`；非 Mac 静默回退到工作区，Windows 用户无法自选保存位置。
   → 改：Windows 用 `tkinter`（Python 自带）原生「另存为」对话框，能识别「取消」；tk 缺失再回退工作区。

3. **启动脚本仅 Mac**（`启动.command`）
   `python3` / `pip3` / `curl` / `open` / `trap`+`kill` 均为 *nix/mac 习惯。
   → 新增 `启动.bat`（Windows）：探测 `py` / `python`，装依赖，起服务，开浏览器。

4. **开浏览器方式分歧**（脚本里 `open` vs Windows `start`）
   → 统一改为由 `server.py` 用 Python 标准库 `webbrowser` 打开，减少脚本平台分歧。
   保留用 `localhost`（而非 `127.0.0.1`）打开，兼容 FB 方式 A 登录。

## 二、改造清单

| # | 位置 | 现状 | 改造 |
|---|------|------|------|
| A | 新增 `启动.bat` | 无 | Windows 一键启动 |
| B | `server.py` 子进程 | `text=True` | `encoding="utf-8", errors="replace"` |
| C | `server.py` 启动 | 脚本 `open` 开浏览器 | 服务就绪后 `webbrowser.open("http://localhost:8765")`（可用环境变量关闭，供测试） |
| D | `server.py` `_choose_save_path` | Mac osascript / 静默回退 | 抽出 `platform_io.choose_save_path()`：Mac=osascript，Win=tkinter，其他/失败=回退工作区 |
| E | 新增 `backend/reward_hub/platform_util.py` | 无 | `detect_python_cmd()`、`is_windows()` 等可测纯函数（供文档/脚本参考与单测） |
| F | `README.md` | 仅 Mac | 补 Windows 启动、依赖、已知限制 |
| G | `.claude/launch.json` | `python3` | 保持（仅本机开发预览用，Mac 环境）；不影响交付 |

`启动.command`（Mac）保留并同步「开浏览器交给 server」的调整（脚本不再自己 `open`）。

## 三、多维全方位测试

1. **回归**：现有 36 项单测改造后重跑，须全绿（`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest`）。
2. **新增跨平台逻辑单测**（Mac 上即可跑，用 monkeypatch 模拟 Windows）：
   - `detect_python_cmd`：`py` 存在 / 只有 `python` / 都没有 的分支。
   - `choose_save_path`：Mac(osascript ok/cancel)、Windows(tkinter ok/cancel)、回退（无 tk / 无 osascript）三平台分支。
   - subprocess 输出 UTF-8 含中文的解码正确性（构造含中文的 emit 行，验证服务侧解析不乱码）。
   - 路径构造 `app_data_dir` / `work_dir` 在模拟 Windows HOME 下的形态。
3. **静态检查**：
   - 全部 `.py` 过 `python3 -m py_compile`。
   - `启动.bat` 语法逐行审查（`py`/`python` 探测、错误提示、编码 `chcp 65001`）。
   - grep 全仓排查残留 Mac-only 硬编码（`osascript` / `\bopen \b` / `python3` 硬编码在运行期路径）。
4. **本机端到端（Mac）**：真起服务，用浏览器走完五步（CSV 导入 + mock 玩家数据 → 语言筛选 → 发奖规则 → 导出 xlsx），验证 xlsx 各 sheet 内容正确。
5. **Windows 真机（如实说明限制）**：
   - 已连接的是 Windows 的**浏览器**，非命令行；它**够不到 Mac 本机 `localhost:8765`**，且无法在 Windows 执行 `.bat`/起 Python。
   - 因此 Windows 侧由「静态 + 逻辑单测」保证正确性；**双击 `.bat` 的真实验证需在 Windows 机器上人工执行**。
   - 交付 `Windows验收清单.md`，列出可照做的逐步验收项。

## 四、交付物

- `启动.bat`（Windows）+ 同步后的 `启动.command`（Mac）
- 改造后的 `server.py` + 新增 `backend/reward_hub/platform_util.py`（保存对话框 / python 探测 / 平台判断）
- 更新的 `README.md`（双平台说明 + Windows 已知限制）
- `Windows验收清单.md`
- 测试报告（本文档末尾或单独文件记录各维度结果）

## 五、不做（YAGNI）

- 不打包 .app / .exe / 安装包（用户已选一键脚本）。
- 不改动核心业务算法与 xlsx 输出布局。
- 不在 Windows 上做无法完成的自动化（无 shell 访问权）。
