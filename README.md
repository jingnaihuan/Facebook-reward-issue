# 社群互动发奖中台

把「社群互动活动发奖」这条固定但繁琐的流程收进一个本地网页中台，一站式走完：

**抓 FB 留言 → 提取玩家 ID → 拉 Eastblue 玩家信息 → 按语言筛选 → 按发奖规则出名单 → 导出多 sheet xlsx**

替代原来「FB 抓取网页 + Excel VBA + 手工 Eastblue 下载 + 手工分 sheet」的多工具拼接。

## 启动方式

前置：本机需装有 **Python 3.9+**（Windows 安装时请勾选「Add python.exe to PATH」）。

- **Mac：双击 `启动.command`**
- **Windows：双击 `启动.bat`**（自动探测 `py` / `python`）

首次运行会自动安装依赖（`openpyxl`），服务就绪后**自动打开浏览器**访问中台页面（`http://localhost:8765`）。关闭该终端 / 命令行窗口即停止服务。

> 启动脚本默认只自动装 `openpyxl`。Eastblue 自动下载（步骤 3）用 Playwright **驱动系统已装的浏览器**
> （Windows 用自带的 **Microsoft Edge**，Mac 用 **Google Chrome**），**不下载内置 chromium 内核**，
> 因此不受公司网络挡 CDN 的影响。只要机器上有 Edge / Chrome 即可（Windows 10/11 均自带 Edge）。
> 首次用步骤 3 时若提示缺 playwright 包，再装一次：
> ```bash
> # Mac
> cd backend && pip3 install -r requirements.txt
> ```
> ```bat
> REM Windows
> cd backend && py -m pip install -r requirements.txt
> ```

手动启动：

```bash
# Mac
cd backend
pip3 install -r requirements.txt
python3 -m playwright install chromium
python3 server.py
```

```bat
REM Windows
cd backend
py -m pip install -r requirements.txt
py -m playwright install chromium
py server.py
```

然后浏览器打开 http://localhost:8765（脚本会自动打开）。

服务基于标准库 `http.server`，无框架依赖；端口固定 `8765`。导出时会弹出系统原生「另存为」对话框（Mac 用 osascript，Windows 用 tkinter）；若环境无对话框可用，自动落到工作区 `~/Documents/发奖中台工作区`。

## 打包成本地 App / Exe（分发给无 Python 环境的同事）

面向不装 Python 的同事，可打成 **Mac `.app` / Windows `.exe`**，双击即用（内含 Python 运行时 + Playwright driver，约 50–200MB）。

- **本机构建**（从仓库根目录运行）：
  - Mac：`bash packaging/build_mac.sh` → 产出 `dist/RewardHub-mac.zip`
  - Windows：`packaging\build_win.bat` → 产出 `dist\RewardHub-win.zip`
- **GitHub 自动构建**：推一个 `v*` tag（如 `git tag v1.0 && git push --tags`），`.github/workflows/build.yml` 会在 Mac + Windows runner 上各构建一份，附到 Release。也可在 Actions 页手动触发（workflow_dispatch）。

打包版与脚本版的差异（已在 `packaging/app_entry.py` / `backend/server.py` 处理）：

- **不靠"关终端"停服务**（`.app`/`.exe` 无终端窗口）。改为**看门狗**：前端每 4s 心跳 `/api/ping`，**关闭网页约 5 分钟后后台自动退出**，不残留进程；宽限取长以防后台标签被浏览器降频误杀，且 **Eastblue 下载进行中绝不退出**。
- **子脚本自我重入**：打包后无法 `python 脚本.py` 跑 Playwright，Eastblue 下载改由 `<exe> --run-script eastblue …` 重新调用自身分发。
- **依旧用系统浏览器**：不内置 Chromium，Mac 用 Chrome、Windows 用自带 Edge，不受公司网络挡 CDN 影响。
- **未做付费签名**：首次打开 Mac/Windows 会弹安全提示，随包附 `packaging/首次打开必读.txt` 指导一次性放行。
- **务必用 `localhost` 打开**（入口已默认）：FB 方式 A 登录只认应用域名 localhost，用 `127.0.0.1` 会被拦。

## 五步流程

### 步骤 1 · 抓取留言
三选一：
- **直接抓取**：Facebook Graph API 浏览器端直连（见下文「FB App ID / Token」），可抓到顶层留言 + 回复，含点赞数、回复数、留言时间与顺序。
- **CSV 导入**：拖拽或选择本地 CSV 文件。
- **粘贴文本**：直接粘贴留言内容。

### 步骤 2 · 清洗提取 ID + 去重
- 正则 `(?:^|\D)(1\d{9})(?!\d)`：1 开头 10 位数字，前后不能是数字（避免误判 11 位号码），与原 VBA `GetID` 完全同款。
- 提不出合规 ID 的留言直接归入「无效」名单（原因：无有效ID）。
- **去重策略**（可存为预设）：
  - `earliest`（默认）：同一玩家只算最早一条留言，防刷楼。
  - `all`：全部保留，每条都参与后续排名/抽选。
  - `best_likes`：同一玩家保留点赞最高的一条（点赞相同取更早的）。

### 步骤 3 · 拉取 Eastblue 玩家信息
- 后端用 Playwright 打开 Eastblue 下载链接，等待浏览器自动触发下载、落盘 xlsx，再读取解析，按玩家 ID 匹配。
- 匹配不到的 ID 归入「无效」名单（原因：Eastblue无记录）。
- 可配置项（可存为预设）：`game_id`、`game_langs`、`except_internal`、`search_num`、`last_act_time`、`server_ids` 等。

### 步骤 4 · 语言筛选
- 勾选本次活动面向的目标语言（如只面向 `en`）。
- 命中的进入下一步；未命中的归入「无效」名单（原因：语言不符）。
- 目标语言可存为预设。

### 步骤 5 · 发奖规则 + 导出
- 可叠加多个奖项，每个奖项选择规则：
  - **前 N 楼**（`top_floors`）：按留言顺序最早的 N 个。
  - **点赞最高**（`top_likes`）：点赞数降序取前 N，同分按留言顺序早的优先。
  - **回复最高**（`top_replies`）：回复数降序取前 N，同分按留言顺序早的优先。
  - **随机抽取**（`random_pick`）：用随机种子抽 N 个，同一种子结果可复现。
- 多个奖项**按配置顺序依次结算**，已中奖的玩家从后续奖项的候选池中剔除，不会重复中奖。
- 未中任何特殊奖、但通过语言筛选的玩家进入「参与奖」。
- 点击导出，生成一份多 sheet 的 xlsx。

## 关键设计：发奖规则的作用范围

**发奖规则只作用于「语言筛选后」的最终名单**（漏斗顺序：提取 ID → 去重 → 匹配 Eastblue → 语言筛选 → 发奖规则 → 导出）。

举例：一个帖子下有 de 和 en 玩家留言，但活动只面向 en。「前 100 楼」= 筛掉 de 之后、en 玩家里的前 100 楼；「随机抽 5 名」也只在这批 en 玩家里抽。非目标语言的玩家在进入规则引擎之前就已经被剔除到「无效」名单。

## 输出布局

一份 xlsx，多个 sheet：
- **每个特殊奖一个 sheet**（sheet 名 = 奖项名称），列：留言顺序、留言时间、玩家ID、语言、别墅等级、角色名称、角色等级、角色创建时间、服务器、历史充值总额、最后登录时间。
- **参与奖 sheet**：通过语言筛选、但未中任何特殊奖的玩家，列结构同上。
- **无效 sheet**：无 ID / Eastblue 无记录 / 语言不符 / 重复留言等，列：玩家ID、留言内容、原因。

## 配置预设

除**发奖规则**（每次活动奖项设置通常不同，不做预设）外，以下配置可存为**命名预设**并设为默认，下次打开自动带入：
- 去重策略
- Eastblue 配置（`game_id`、`game_langs`、`except_internal`、`search_num`、`last_act_time`、`server_ids` 等）
- 目标语言

预设存储在 `~/.reward_hub_app/presets.json`，与项目代码分离，不会被提交到仓库。

## Eastblue 首次使用说明

- 首次点击「拉取 Eastblue 玩家信息」会自动弹出一个浏览器窗口尝试下载。
- 如果停在 **SSO 登录页**，需要人工登录一次；登录态会持久化在 `~/.reward_hub_app/eastblue_profile`，之后无需再登。
- Eastblue 导出表格的表头以实测为准。如果表头文字与代码中的 `backend/reward_hub/eastblue_parse.py` 里的 `_HEADER_MAP` 对不上（比如列名换了），需要据实调整该映射表，否则对应字段会读不到。

## FB App ID / Access Token 填写说明

抓取留言时二选一：

- **方式 A：填 App ID**，用 Facebook 登录授权。要求：
  - Facebook App 后台需要把中台运行的域名（如 `localhost`）加入「允许的 JS SDK 网域」。
  - 登录账号需要拥有该 App 的角色权限，并且是目标粉专的管理员。
- **方式 B：直接粘贴 Access Token**（User Token 或 Page Access Token），无需 App ID，更简单，适合临时抓取。

抓取直连 `graph.facebook.com`，Token 只保留在浏览器本机内存中，不落盘、不经过后端。

## 依赖

- Python 3.9+
- `openpyxl`（xlsx 读写）
- `playwright`（Eastblue 自动下载，需额外 `python3 -m playwright install chromium`）
- `pytest`（跑测试用）

见 `backend/requirements.txt`。

## 测试

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest
```

> 本机全局 Anaconda 环境的 pytest 有插件冲突（jinja2/dash），必须加 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 前缀，不要试图"修好"这个环境。

覆盖模块：`extract_id`（ID 提取）、`dedup`（去重）、`language_filter`（语言筛选）、`rule_engine`（发奖规则）、`export`（xlsx 导出）、`config_store`（预设持久化）、`eastblue_parse`（Eastblue 表格解析）。

还包含一个**端到端回归测试**（`test_e2e_regression.py`）：用真实历史活动的 xlsm 数据跑一遍「提取 ID → 去重 → 匹配 → 语言筛选 → 发奖规则」全链路，比对「先锋奖」中奖名单与人工结算结果**完全一致**。

当前共 **36 项测试，全部通过**。

## 已知待实测项

- **FB 真机抓取**：需要真实 App ID / Token 与粉专权限，本地无凭证未做真实抓取验证（逻辑与选择器沿用已验证可行的 `Facebook留言抓取` 工具）。
- **Eastblue 真实下载**：需要真实登录会话，且首次使用后应核对实际导出表头是否与 `_HEADER_MAP` 一致，如不一致需调整映射。
- **Windows 适配**：已完成代码层改造与跨平台逻辑测试（`启动.bat`、UTF-8 子进程编码修复、tkinter 保存对话框、`webbrowser` 统一开浏览器）。开发机为 Mac，Windows 侧的**双击真实运行**（`.bat` 启动、依赖安装、原生对话框弹出）需在 Windows 机器上按 [`Windows验收清单.md`](Windows验收清单.md) 人工验收一次。
- **打包版（.app / .exe）**：Mac `.app` 已在本机真机构建并端到端验证（server 启动、前端页面、心跳、`--run-script eastblue` 分发、看门狗自动退出、`/api/shutdown`）。**Windows `.exe`** 由 GitHub Actions 构建，其双击运行（SmartScreen 放行、Eastblue 子进程分发、tkinter 另存为）需在 Windows 机器上人工验收一次。
