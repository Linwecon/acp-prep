# 🎓 ACP 备考助手

> 阿里云大模型高级工程师认证（Alibaba Cloud ACP – Large Model）一站式备考平台：**知识学习 · 章节刷题 · 标准模考 · AI 答疑 · 跨设备同步**。
>
> 纯前端静态站点，零构建依赖，双击 `index.html` 或部署到任意静态托管即可使用。

---

## 目录

- [功能特性](#-功能特性)
- [快速开始](#-快速开始)
- [部署](#-部署)
- [可选配置](#-可选配置)
- [项目结构](#-项目结构)
- [技术栈](#-技术栈)
- [数据与构建](#-数据与构建)
- [贡献指南](#-贡献指南)
- [致谢](#-致谢)
- [许可证](#-许可证)
- [免责声明](#-免责声明)

---

## ✨ 功能特性

### 学习板块

- **知识宇宙**：12 章教材式知识点阅读，自研 Markdown 渲染器支持 5 种内置图表（流程图、条形图、环形图、注意力热力图、矩阵分解图）和教材级信息块（学习目标、现实场景、工作原理、考试重点、自测题等）。
- **学习进度**：逐知识点标记掌握状态，环形进度图实时展示章节完成度。
- **深度学习 / 考前速记双模式**：考前速记模式自动折叠深入讲解，只保留考试要点与常见误区。
- **官方实战教程文档**：阿里云 ACP 官方教程 Notebook（24 篇）按章节分类在线阅读，按原始顺序呈现讲解、代码、运行输出与图片，支持目录导航、代码高亮、一键复制、学习进度与 `.ipynb` 原文件下载。内容为**预先转换的静态网页**，浏览器不执行任何 Python。

### 刷题板块

- **章节练习**：12 章分章刷题，单选 / 多选，支持全部、未答、错题、收藏四种筛选。
- **模拟考试**：75 题标准卷（50 单选 × 1 分 + 25 多选 × 2 分 = 100 分，及格线 80），按官方大纲六大知识域比例（应用开发 17% / 提示词 15% / RAG 20% / 微调 16% / 多 Agent 及多模态 16% / 生产环境 16%）分层抽题，120 分钟计时，交卷后逐题回顾与薄弱章节分析。
- **错题本 / 收藏夹**：错题自动收集、重点题随时标记，支持一键重练。
- **全局搜索**：题干关键词实时检索并高亮跳转。
- **键盘操作**：`A`–`G` 选题、`Enter` 提交、方向键翻题，支持单题 / 列表双视图与随机顺序。

### 可选增强

- **AI 答疑**：答题后调用任意 OpenAI 兼容大模型（阿里云百炼、DeepSeek、智谱、硅基流动等）逐项讲解，SSE 流式输出，结果本地缓存，API Key 仅存本机。
- **题目助手（AI 追问）**：讲解之后点击「💬 继续追问」唤出一个**可拖动的浮动窗**（非模态、无背景遮罩与模糊，方便边看题目边追问），围绕该题无限追问，始终携带题干、选项、我的作答与已有讲解作为上下文，支持多轮连续问答、中途停止与重试；窗口位置会被记住，双击标题栏复位。追问按题目隔离存本机，可随时清空（不影响 AI 讲解缓存）。
- **跨设备同步**：邮箱注册登录后，进度、错题、收藏、成绩、续做位置通过 Supabase 实时同步，冲突按"计数取大、时间戳取新、收藏取并集"自动合并。

---

## 🚀 快速开始

### 方式一：直接打开

双击 `index.html` 即可在浏览器中使用。所有题库与知识点通过 `<script>` 标签加载，无需安装任何依赖。

### 方式二：本地服务器（推荐）

部分浏览器对 `file://` 协议下的 `fetch` / 本地存储有限制，建议启动一个静态服务器：

```bash
# Python 3（自带，无需安装）
python -m http.server 8080

# 或 Node.js
npx serve .
```

然后访问 <http://localhost:8080>。

---

## 📦 部署

本项目是纯静态站点，可部署到 GitHub Pages、Cloudflare Pages、Vercel、Netlify、Nginx 等任意静态托管平台。

### GitHub Pages

1. Fork 本仓库；
2. 在仓库 Settings → Pages 中选择 `main` 分支根目录作为 Source；
3. 等待 Actions 构建完成即可通过 `https://<your-name>.github.io/<repo>/` 访问。

仓库根目录提供了一个 Windows 一键推送脚本：

```powershell
.\一键更新.bat
```

### 其他平台

直接将整个目录上传到静态托管服务即可，无需构建步骤。

---

## 🔧 可选配置

以下功能**均为可选**，未配置时应用以纯本地模式完整运行（学习、刷题、模考均可用）。

### AI 答疑

在侧边栏「🤖 AI 设置」中填入任意 OpenAI 兼容服务的：

- **API Base URL**：例如 `https://dashscope.aliyuncs.com/compatible-mode/v1`（阿里云百炼）
- **API Key**：在对应服务商控制台申请
- **模型名**：例如 `qwen-plus`、`deepseek-chat`、`glm-4-flash` 等

API Key 仅保存在浏览器 `localStorage`（键名 `acp_ai_config`），浏览器直连服务商接口，不经过任何第三方服务器。

### 云端同步（Supabase）

1. 在 [Supabase](https://supabase.com) 创建项目；
2. 在 SQL Editor 中执行 [`supabase/schema.sql`](supabase/schema.sql)（建表 + 行级安全策略）；
3. Authentication → Providers → Email 开启；如需注册后自动登录，关闭 Confirm email；
4. Authentication → URL Configuration 添加站点地址；
5. 把 Project URL 与 `anon` public key 填入 [`config/supabase.js`](config/supabase.js)。

> **安全提示**：前端只能使用 `anon` public key，并依靠 RLS（Row Level Security）保证用户只能访问自己的数据。`service_role` 密钥严禁进入前端代码或仓库。

#### 免费版保活

保活脚本每 6 小时检查 Auth 服务，并通过只读 RPC 实际查询数据库。网络错误、HTTP 408/429/5xx 最多尝试 3 次，每次请求超时 15 秒；任一检查失败会让 GitHub Actions 任务失败。

**首次启用：**

1. 在 Supabase Dashboard → SQL Editor 执行 [supabase/keepalive_ping.sql](supabase/keepalive_ping.sql)，创建只返回 `pong` 的只读函数；这一步是必需的，可重复执行。
2. 确认 [config/supabase.js](config/supabase.js) 是当前项目的 URL 和公开密钥，无需管理员密钥。
3. 将保活相关文件推送到 GitHub 默认分支，在 Actions 中启用 **Supabase Keep-Alive**。
4. 点击 **Run workflow** 手动运行一次，确认 Auth 和数据库检查都通过。

自动运行时间为北京时间 **05:17、11:17、17:17、23:17**，由 GitHub 执行，不需要电脑开机；实际调度可能延迟。可在 GitHub 通知设置中开启 Actions 失败通知。公共仓库长期无活动时定时任务可能被停用，需检查 Actions 状态。

本地验证（Node.js 22）：

```bash
node .github/scripts/supabase-keepalive.mjs
node --test scripts/test_keepalive.mjs
```

- 数据库 HTTP 404：执行上面的 SQL，等待接口刷新后重试。
- HTTP 401/403：检查公开密钥和函数执行权限。
- 域名解析失败或超时：检查网络和项目状态；若已暂停，先在控制台 Resume。

脚本仅确认本次请求成功，不能确认平台暂停计时已重置，也不能保证免费项目永不暂停。平台的低活跃判断依据见 [Supabase 官方说明](https://supabase.com/docs/guides/platform/free-project-pausing)。

---

## 📁 项目结构

```
acp/
├── index.html               # 入口 HTML（学习 / 刷题二选一落地页）
├── admin.html               # 题库治理台（四类检查结果列表 / 过滤 / 预览 / 导出操作清单）
├── style.css                # 全局样式与教材设计系统
│
├── data/                    # 运行时加载的数据
│   ├── knowledge.js         # 知识点（window.KNOWLEDGE_MD，由脚本生成）
│   ├── notebooks.js         # 官方教程索引（章节分组 / 标题 / 简介 / 难度 / 时长）
│   ├── notebooks/           # 单篇教程正文（按需加载）+ src/ 原始 .ipynb 副本
│   ├── quiz_categorized.js  # 题库（完整版）
│   └── quiz_categorized.min.js
│
├── assets/notebooks/        # 教程代码单元的图片输出（由转换脚本导出）
│
├── js/                      # 前端模块（IIFE，挂载到 window.ACP）
│   ├── acp.js               # 全局常量（考试大纲、章节、状态）
│   ├── utils.js             # 工具函数
│   ├── store.js             # localStorage 存储层
│   ├── data.js              # 题库构建与统计
│   ├── study.js             # 知识点阅读器 + Markdown 渲染 + 教材组件
│   ├── notebook.js          # 官方实战教程文档（列表 / 详情 / 目录 / 高亮 / 进度）
│   ├── chapter.js           # 章节练习
│   ├── exam.js              # 模拟考试引擎（按大纲比例抽题）
│   ├── dashboard.js         # 学习总览
│   ├── search.js            # 全局搜索
│   ├── sidebar.js           # 侧边栏
│   ├── ai.js                # AI 答疑（OpenAI 兼容 + 流式）
│   ├── sync.js              # Supabase 登录与云同步
│   └── app.js               # 启动入口、主题、键盘事件
│
├── config/
│   ├── supabase.js          # Supabase 公开配置
│   └── verify_config.example.json
├── supabase/
│   ├── schema.sql           # 数据库表结构 + RLS 策略
│   └── keepalive_ping.sql   # 可选：保活用的只读 ping() 函数
│
├── .github/                 # CI：Supabase 免费版保活
│   ├── workflows/supabase-keepalive.yml
│   └── scripts/supabase-keepalive.mjs
│
├── scripts/                 # 数据处理与测试脚本（Python / Node）
│   ├── build_knowledge.py   # 把知识点 Markdown 打包为 knowledge.js
│   ├── quiz_curate.py       # 题库治理统一入口：章节匹配/低质/答案/补题/软删除/回滚
│   ├── curate_core.py       # 治理共享核心库：台账/软删除/答案历史/语义查重
│   ├── verify_answers.py    # 答案独立作答交叉验证（多模型）
│   ├── verify_disputed.py   # 争议题投票终裁与修正应用（带旧版本存档）
│   ├── classify_questions.py
│   ├── compress_bank.py
│   ├── test_curate.py       # 治理核心行为测试（unittest）
│   └── test_*.js            # 各模块冒烟测试
│
├── docs/                    # 知识点源文档与校验报告
│   └── ACP高频知识点总结.md
```

---

## 🛠 技术栈

| 层 | 技术 | 说明 |
|----|------|------|
| 前端 | 原生 HTML / CSS / JavaScript（ES6+） | 无框架、无打包工具，IIFE 模块化挂载到 `window.ACP` |
| 持久化 | `localStorage` | 进度、错题、收藏、成绩、AI 配置本地保存 |
| 图表 | 原生 SVG / CSS | 5 种内置图表，零第三方依赖 |
| 教程文档 | 预转换静态 Notebook | 构建期把 .ipynb 转为 JS 数据，浏览器只渲染不执行 Python |
| 认证 / 云同步 | Supabase Auth + PostgreSQL + RLS | 可选；邮箱登录，行级安全隔离用户数据 |
| AI 答疑 | OpenAI 兼容接口 | 浏览器直连，SSE 流式输出，多服务商可切换 |
| 数据脚本 | Python 3 | 题库合并、分类、压缩、答案多模型校验 |

---

## 📊 数据与构建

### 知识点

知识点源文档为 [`docs/ACP高频知识点总结.md`](docs/ACP高频知识点总结.md)，由 [`scripts/build_knowledge.py`](scripts/build_knowledge.py) 打包为 `data/knowledge.js`：

```bash
python scripts/build_knowledge.py
```

修改知识点后**必须重新运行此脚本**，否则前端加载的仍是旧版本。

### 官方实战教程文档

教程源为阿里云官方开源教程 `aliyun_acp_learning/大模型ACP认证教程/` 下的 24 个 `.ipynb`
（该仓库有独立 .git 与 Apache-2.0 许可证，**不纳入本仓库**，`.gitignore` 已忽略）。
由 [`scripts/build_notebooks.py`](scripts/build_notebooks.py) 预转换为静态网页数据：

```bash
python scripts/build_notebooks.py                 # 默认读取 aliyun_acp_learning/大模型ACP认证教程
python scripts/build_notebooks.py --src <目录>     # 指定其他教程目录
python scripts/test_notebooks.py                   # 校验产物（索引/正文/目录/图片/原文件）
node scripts/test_notebook_render.js               # 前端渲染冒烟测试
```

产物与行为：

- `data/notebooks.js`：教程索引（C1–C5 + 拓展实战分组，含标题、简介、难度、预计时长、单元数）；
- `data/notebooks/<id>.js`：单篇正文，**打开时才按需加载**，首屏不下载全部内容；
- `assets/notebooks/<id>/*.png`：代码单元的图片输出（base64 还原为文件）；
- `.ipynb` 源文件不随站点分发，列表页提供官方仓库链接：<https://github.com/AlibabaCloudDocs/aliyun_acp_learning>。

设计约束：**纯静态**——Notebook 在构建期完成转换，浏览器只做渲染，不执行任何 Python；
Markdown 复用 `js/study.js` 的 `ACP.mdToHtml`，与知识点教材风格、深浅主题一致；
详情页按 Notebook 原始顺序呈现「讲解 / 代码 / 运行输出 / 图片」，提供目录导航（桌面侧栏吸顶、
移动端横向滚动）、Python 代码高亮、一键复制、学习进度（记录阅读位置，读到底部自动标记学完）。
长代码与大表格在手机上横向滚动，不截断。难度与预计时长由构建脚本按代码量/篇幅启发式估算，
仅为列表筛选参考。

修改或新增教程后**必须重新运行转换脚本**；源目录缺失时会给出提示，已生成的数据不受影响。

### 题库

- 共 **1652 题**，覆盖 12 章；
- 题目按章节存放在 `data/quiz_categorized.js`；
- 压缩版 `quiz_categorized.min.js` 用于生产环境，体积更小。

### 题库维护（治理工具）

题库治理统一入口为 [`scripts/quiz_curate.py`](scripts/quiz_curate.py)（共享核心库 [`scripts/curate_core.py`](scripts/curate_core.py)），覆盖四类场景：**章节匹配检查、低质题筛选、答案检测、按章补题**。核心原则：**检查先生成报告，删除或修正必须通过明确操作应用**；删除一律软删除（数据保留、可恢复），答案修正自动保存旧版本（可回滚），所有批量操作记入台账（`data/curate/ledger.json`），重复执行幂等。

```bash
# 0. （一次性）从章节正文生成 12 章知识画像，供章节匹配使用
python scripts/quiz_curate.py profiles

# 1. 章节匹配：两种模式
#    a) 规则初筛 + LLM 复核候选（省调用）：
python scripts/quiz_curate.py chapter --llm --resume
#    b) 全量语义审核（跳过初筛逐题 LLM 审核；>200 题需 --yes 确认）：
python scripts/quiz_curate.py chapter --full --llm --chapters 11 --yes
#    五分类 own/cross/misplaced/beyond/unsure；证据要求逐字摘录章节原文，
#    程序回溯定位（exact=精确 / partial=分句命中 / missing=不可追溯需人工核实）。
#    输出 data/curate/chapter_audit.json + docs/chapter_audit_report.md
#        data/curate/move_chapter.json（移动清单）、remove_chapter.json（超纲清单）

# 2. 低质题：规则信号 + 文本相似度初筛（bigram Jaccard）→ 加 --llm 按维度评审
#    注意：bigram 相似只是文本初筛；是否语义重复以 LLM 评审为准
#    四分类 ok / fixable / remove / review；fatal_logic（严重逻辑错误）单独标记
python scripts/quiz_curate.py quality --llm --resume --min-score 3 --sim-threshold 0.6
#    输出 data/curate/quality_audit.json + docs/quality_audit_report.md + remove_quality.json

# 3. 答案检测：复用既有 verify 流水线（独立作答 → 6 模型投票 ≥3 票才修正）
python scripts/verify_answers.py --resume --workers 8   # 全库独立作答交叉验证（结果绑定题目内容指纹）
python scripts/verify_disputed.py --vote --report       # 争议题终裁（投票缓存绑定输入版本，题目变化即作废）
python scripts/verify_disputed.py --evidence            # 对 fix 项核对教材证据：逐段定位引用 + 逐选项核对，
                                                        #   "引用是否存在"与"是否支持结论"分开记录，证据绑定输入版本
python scripts/verify_disputed.py --apply               # 应用修正（统一守卫 curate_core.check_fix_entry：
                                                        #   指纹已绑定且匹配 + 答案格式合法 + 证据充分；
                                                        #   无指纹旧结果不得补绑，须重新验证；
                                                        #   旧答案存入 answer_history，可回滚；
                                                        #   仅投票放行需显式 --allow-vote-only，台账记为人工覆盖）
python scripts/quiz_curate.py answers                   # 生成处置报告：修正/失效/多解/证据不足四类
#    多解/条件不足 → data/curate/suspend_answers.json（人工确认后软删除，禁止强改答案）

# 4. 按章补题：缺口蓝图 → 七段检查链 → 人工审核 → 合入
python scripts/quiz_curate.py plan --target 100
#    合格口径 = 非软删除 + 答案已确认 + 低质非待修复/待复核 + 章节非待处理；
#    配额按该章现有题型/难度分布计算，画像考点覆盖 0 的优先补。
python scripts/quiz_curate.py generate --chapter 11
#    每题七段检查：format → sim_text 文本相似初筛（仅候选筛选，任何相似度都不直接判重）
#    → sem_dup 语义查重（逐项比较考点/关键条件/解题路径，LLM）
#    → chapter 章节归属 → quality 质量评审 → solve 隐藏答案独立解题
#    → evidence 教材证据核对（引用逐段定位 + 逐选项核对，"引用存在"与"支持结论"分开判定）。
#    逐题记录检查结果；草稿通过 ≠ 正式入库，合入需人工审核：
python scripts/merge_new_questions.py --drafts questions_auto_ch11.json

# 5. 执行操作（默认 dry-run，--apply 才生效，生效前自动备份）
python scripts/quiz_curate.py remove --from data/curate/remove_quality.json --apply   # 软删除
python scripts/quiz_curate.py restore --from data/curate/suspend_answers.json --apply # 恢复
python scripts/quiz_curate.py move   --from data/curate/move_chapter.json --apply     # 移章
python scripts/quiz_curate.py rollback --batch <batch_id> --apply                     # 回滚批次
python scripts/quiz_curate.py status                                                  # 统计与台账
```

**治理台界面**（[`admin.html`](admin.html)）有两种工作方式：

```bash
# 可执行模式（推荐）：本机管理服务，页面内可直接执行删除/恢复/移章/答案修正/回滚
python scripts/admin_server.py                 # 打开 http://127.0.0.1:8765/admin.html
python scripts/admin_server.py --bank <副本目录>  # 副本模式：所有操作指向题库副本（用于演练）
python scripts/admin_server.py --read-only     # 只读模式

# 只读模式：任意静态服务器（python -m http.server 8080）打开 admin.html，仅查看报告并导出操作清单
```

管理服务安全约束（不仅依赖 127.0.0.1 监听）：静态文件走 allowlist（`/config/` 等敏感路径 GET/HEAD 均不可达，编码与路径折叠被规范化拦截）；写接口需会话令牌（`GET /api/session` 仅对本机回环发放）并校验 Host/Origin；请求体 ≤1MB；JSON 字段与类型严格校验。答案修正统一走 `curate_core.check_fix_entry` 守卫，无验证通过的显式修正入口不存在；人工纠正走 `manual_fix`（页面/`POST /api/ops/manual_fix`），必须提供明确理由并记录为「人工覆盖」。管理服务的读库→校验→写库→记账→重建全程互斥，文件原子替换写入。端到端测试：`python scripts/test_admin_server.py`（在临时副本上验证全部 API 与安全防护，断言正式题库零改动）、`python scripts/test_admin_ops.py`（含并发不丢更新、回滚冲突检测）。

说明：LLM 相关子命令复用 `config/verify_config.json`（模板见 `config/verify_config.example.json`）；关键词/相似度**阈值未经人工标注样本校准**，报告仅供人工参考；删除**不重排 seq**，用户已保存的进度/错题记录（按 `章-seq` 索引）不受影响。

### 考试大纲

官方大纲六大知识域与抽题配额定义在 [`js/acp.js`](js/acp.js) 的 `ACP.EXAM_DOMAINS`，修改大纲比例会自动影响模拟考试抽题与知识宇宙环形图。

---

## 🤝 贡献指南

欢迎 Issue 和 Pull Request！

### 报告问题

提 Issue 时请尽量包含：

- 浏览器与操作系统版本；
- 问题描述与复现步骤；
- 控制台报错截图（如有）；
- 题目内容截图（如为题目本身的问题）。

### 贡献内容

1. Fork 本仓库并创建特性分支：`git checkout -b feature/your-feature`；
2. 知识点改动请编辑 `docs/ACP高频知识点总结.md`，然后运行 `python scripts/build_knowledge.py`；
   教程文档改动请更新 `aliyun_acp_learning/` 下的 Notebook，然后运行 `python scripts/build_notebooks.py`；
3. 题库改动请说明题目来源与答案依据；
4. 提交前请运行相关冒烟测试：`node scripts/test_*.js`；
5. 确保代码不包含任何 API Key、`.env`、`service_role` 等敏感信息；
6. 提交 PR，并清晰描述改动内容与动机。

### 代码风格

- 前端使用原生 JavaScript，不引入新的构建工具或框架；
- 缩进 4 空格，字符串优先使用单引号；
- 模块通过 `(function(ACP){ ... })(window.ACP)` IIFE 封装，通过 `ACP.xxx = ...` 显式导出；
- Python 脚本兼容 Python 3.9+。

---

## 🙏 致谢

- 知识点与部分教材内容参考了阿里云官方开源教程 [aliyun/aliyun_acp_learning](https://github.com/AlibabaCloudDocs/aliyun_acp_learning)（Apache License 2.0），该仓库作为写作参考置于本地目录 `aliyun_acp_learning/`，未包含在本仓库中；
- 题目来源于公开 ACP 备考资料，答案经多模型交叉校验与人工核对，仅供学习参考；
- 感谢所有提出反馈与修正的同学。

---

## 📄 许可证

本项目代码以 MIT License 发布（如需在仓库中正式附带协议文本，可在 GitHub 创建仓库时选择 MIT License 自动生成 LICENSE 文件）。

题库、知识点文本与截图**仅供个人学习交流使用**，不得用于商业用途；考试题目的相关版权归阿里云及原作者所有。

---

## ⚠️ 免责声明

- 本项目为社区学习项目，与阿里云官方无任何关联；
- 题目与解析不保证 100% 正确，正式考试请以阿里云官方文档与最新考试大纲为准；
- AI 答疑功能由第三方大模型提供，回答内容不代表本项目观点，关键知识点请交叉验证；
- 使用 Supabase 或任何云服务时，请自行评估数据安全与合规风险。


## 本轮实际题库治理结果（2026-10-02）

已审核原有 1656 题，执行移章 24 题、软删除 9 题、修正答案/题型 3 题，新增 386 道通过检查的新题；当前在用 2033 题。865 道原题保留待复核，不计入每章 100 道已确认题的目标。该目标剩余 176 题，当前配置模型返回 Arrearage，后续请求已停止。

实际报告：`docs/题库治理实际结果.md`；全库明细：`data/curate/governance/audit.json`；最终复核修订：`final_review.json`；状态与缺口：`completion_progress.json`。管理台默认显示“本轮全库结果”。

恢复模型接口后可断点续跑（已有结果缓存）：

```powershell
python scripts/complete_governance.py --start-round 11 --workers 8 --factor 4
python scripts/govern_bank.py report
```

变更台账保留旧答案与解析；新增题支持按批次回滚，回滚新增题采用软删除；题干/题型修复也可恢复。移章产生新题号，已有客户端按旧题号保存的学习记录尚未自动迁移。
