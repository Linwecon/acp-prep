# 🎓 ACP 刷题助手

> 阿里云大模型高级工程师认证（ACP）备考工具 — 纯前端单页应用，零构建依赖，开箱即用。

---

## ✨ 功能特性

| 模块 | 说明 |
|------|------|
| 🚪 **入口选择** | 打开即见"学习 / 刷题"二选一落地页，键盘 1/2 快速进入 |
| 📚 知识点阅读 | 高频考点文档内置阅读器：章节快速导航、滚动进度条、目录锚点跳转 |
| 📊 学习总览 | 环形进度图、章节掌握度排行、薄弱章节高亮 |
| 📝 模拟考试 | 75 题标准卷（50 单选 + 25 多选），按新版大纲考点比例抽题，120 分钟计时，自动评分 |
| 📖 章节练习 | 12 章分章刷题，支持全部/未答/错题/收藏四种筛选，难度递增；作答历史（选项+对错）持久保存，再次进入自动续做最后一道已答题 |
| ✗ 错题本 | 自动收集错题，按章节分组，支持一键重练 |
| ⭐ 收藏夹 | 标记重点题目，随时回顾 |
| 🔍 全局搜索 | 题干关键词实时搜索，高亮匹配 |
| 🤖 AI 答疑 | 答完题后一键调用大模型，按"考点定位 / 解题思路 / 逐项分析 / 记忆要点"讲透每道题（自带 DashScope API Key，浏览器直连） |
| ⌨️ 键盘操作 | A-G 选题、Enter 提交、方向键翻题 |
| 🌓 深色模式 | 明暗主题切换，自动持久化 |
| 💾 数据持久化 | localStorage 自动保存学习进度，支持旧版数据迁移 |

## 🚀 快速开始

```bash
# 方式一：直接打开
双击 index.html 即可在浏览器中使用

# 方式二：本地服务器（推荐，避免 file:// 限制）
# Python 3
python -m http.server 8080
# 然后访问 http://localhost:8080
```

## 📁 项目结构

```
acp/
├── index.html               # 入口 HTML（含学习/刷题二选一落地页）
├── style.css                # 全局样式（Notion/Linear 风格）
│
├── data/                    # 题库与知识点数据
│   ├── quiz_categorized.js  # 分类后的题目（运行时加载）
│   ├── quiz_categorized.json
│   ├── quiz_data.json
│   └── knowledge.js         # 知识点文档（由脚本生成，运行时加载）
│
├── js/                      # 前端脚本（按职责分模块）
│   ├── acp.js               # 全局命名空间 + 共享状态
│   ├── utils.js             # 工具函数（esc, toast, analysisHTML 等）
│   ├── store.js             # localStorage 存储层
│   ├── data.js              # 题库构建与统计
│   ├── sidebar.js           # 侧边栏渲染
│   ├── dashboard.js         # 学习总览视图
│   ├── chapter.js           # 章节练习（单题/列表模式）
│   ├── study.js             # 知识点阅读器（Markdown 渲染 + 章节导航）
│   ├── exam.js              # 模拟考试
│   ├── search.js            # 全局搜索
│   ├── ai.js                # AI 答疑（DashScope 直连 + Key 配置）
│   └── app.js               # 落地页/主题/键盘/启动
│
├── scripts/                 # Python / Node 工具脚本
│   ├── build_knowledge.py     # 生成 data/knowledge.js（知识点打包）
│   ├── test_study_renderer.js # 知识点渲染器冒烟测试
│   ├── classify_questions.py  # 题目分类处理
│   ├── scan_quiz_issues.py    # 题库扫描
│   ├── analyze_outline_coverage.py  # 题库 vs 官方大纲覆盖率分析
│   ├── verify_answers.py      # 题库答案多模型交叉校验（需 API Key）
│   └── test_exam_domains.js   # 模拟考试抽题配额测试
│
└── docs/                    # 参考文档
    ├── ACP高频知识点总结.md  # 1459 道真题提炼的高频考点
    └── 官网真实模拟题.md     # 模拟题整理版
```

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────┐
│                   index.html                     │
│  ┌─────────┐  ┌──────────┐  ┌────────────────┐  │
│  │  style   │  │  题库 JS  │  │  前端脚本模块   │  │
│  │  .css    │  │  data/   │  │  js/*.js       │  │
│  └─────────┘  └──────────┘  └────────────────┘  │
└─────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│           window.ACP 命名空间                    │
│                                                  │
│  ┌────────┐  ┌────────┐  ┌────────────────┐     │
│  │ acp.js  │  │ utils  │  │    store.js    │     │
│  │ 状态    │  │ 工具   │  │  localStorage │     │
│  └────────┘  └────────┘  └────────────────┘     │
│                                                  │
│  ┌────────┐  ┌────────┐  ┌────────────────┐     │
│  │ data   │  │sidebar │  │   dashboard   │     │
│  │ 数据层  │  │ 侧边栏 │  │   学习总览     │     │
│  └────────┘  └────────┘  └────────────────┘     │
│                                                  │
│  ┌────────┐  ┌────────┐  ┌────────────────┐     │
│  │chapter │  │  exam  │  │    search.js   │     │
│  │ 章节   │  │ 考试   │  │     搜索       │     │
│  └────────┘  └────────┘  └────────────────┘     │
│                                                  │
│  ┌──────────────────────────────────────┐       │
│  │           app.js (启动入口)            │       │
│  └──────────────────────────────────────┘       │
└─────────────────────────────────────────────────┘
```

## 🔑 核心设计

| 设计项 | 说明 |
|--------|------|
| **命名空间** | 所有函数挂载到 `window.ACP.*`，消除全局变量污染 |
| **状态聚合** | 可变状态（ui/store/exam/session 等）统一收口到 `ACP.state` |
| **IIFE 隔离** | 每个模块用 `(function(ACP){...})(window.ACP)` 封装，私有变量不泄露 |
| **无构建依赖** | 纯 `<script>` 标签按依赖顺序加载，双击 HTML 即可运行 |

### 加载顺序

```
题库数据 → 命名空间 → 工具 → 存储 → 数据 → 视图 → 搜索 → 启动
```

## 📖 模块职责

| 文件 | 公开 API | 职责 |
|------|----------|------|
| `acp.js` | — | 定义 `ACP.EXAM_*`、`ACP.state`、题库索引容器 |
| `utils.js` | `esc`, `toast`, `analysisHTML`, `shuffle`, `normAnsArr`, `chapterName`... | 通用工具 |
| `store.js` | `loadStore`, `saveStore`, `markResult`, `toggleFav`... | 进度/错题/收藏的持久化 |
| `data.js` | `buildBank`, `chStats`, `globalStats` | 题库构建与统计 |
| `sidebar.js` | `renderSidebar`, `openChapter`, `toggleSidebar` | 侧边栏渲染与导航 |
| `dashboard.js` | `renderDashboard`, `resumeLast` | 学习总览视图 |
| `study.js` | `renderStudy`, `studyJump`, `mdToHtml` | 知识点阅读器（Markdown 渲染、章节跳转、滚动进度） |
| `chapter.js` | `render`, `go`, `judge`, `navQ`, `onFav`, `renderGroup`... | 章节练习核心（单题+列表+错题/收藏视图） |
| `exam.js` | `renderExam`, `startExam`, `submitExam`, `isExamCorrect` | 模拟考试引擎 |
| `search.js` | `closeSearch`, `jumpToQuestion` | 题干搜索与跳转 |
| `ai.js` | `aiAsk`, `openAISettings`, `testAIConnection` | AI 答疑（DashScope 调用、Key 配置、讲解渲染） |
| `app.js` | `boot`, `toggleTheme`, `resetAllData` | 启动、主题、键盘事件 |

## 🎯 键盘快捷键

| 场景 | 快捷键 |
|------|--------|
| 章节练习 | `A`-`G` 选题 · `Enter` 提交 · `←/→` 翻题 |
| 模拟考试 | `←/→` 翻题 |
| 搜索框 | `Enter` 跳转到首条结果 · `Esc` 关闭 |

## 📝 数据说明

- 题库共 **1548** 题，覆盖 **12** 个章节
- 模拟考试：单选 50 题 × 1 分 + 多选 25 题 × 2 分 = 100 分
- 抽题遵循新版官方大纲的**知识域比例**：大模型应用开发 17% / 提示词工程 15% / 检索增强 20% / 微调 16% / 多Agent与多模态 16% / 生产实践 16%，单选与多选分别按域配额（最大余数法）分层抽取
- 模拟考试入口页内置**新版考试大纲**面板：六大知识域 → 主要内容 → 知识点逐层展开，并可一键直达对应章节刷题
- 及格线：80 分
- 学习数据存储在浏览器 `localStorage`，键名 `acp_v2_store`
- 已支持从旧版（`acp_chapter_progress`、`acp_quiz_progress_glass`）自动迁移
- 知识点内容来自 `docs/ACP高频知识点总结.md`，修改文档后运行
  `python scripts/build_knowledge.py` 重新生成 `data/knowledge.js`
  （或运行 `node scripts/test_study_renderer.js` 做渲染冒烟测试）
- 打开 `index.html#study` 或 `#quiz` 可跳过落地页直达对应模式
- 题库质量工具（自购题库无官方答案，建议定期校验）：
  - `python scripts/analyze_outline_coverage.py` — 题库 vs 官方大纲覆盖率分析（无需 Key）
  - `python scripts/verify_answers.py --limit 100` — 多模型交叉校验答案，
    先复制 `config/verify_config.example.json` 为 `verify_config.json` 填入 API Key
    （DashScope 兼容接口），结果输出到 `docs/answer_verify_report.md`

## 🤖 AI 答疑（可选，需自带 Key）

答完题后，解析框下方会出现 **"AI 答疑"** 按钮，点击后调用大模型按
"考点定位 / 解题思路 / 选项逐项分析 / 记忆要点" 四段结构讲透当前题目。

- **零后端直连**：浏览器直接请求阿里云百炼（DashScope）的 OpenAI 兼容接口
  `https://dashscope.aliyuncs.com/compatible-mode/v1`，该接口已开启 CORS。
- **Key 仅存本机**：在侧边栏 "🤖 AI 设置" 里填入你自己的 API Key，保存在
  `localStorage`（键名 `acp_ai_config`），不上传任何服务器，可随时清空。
- **默认模型** `qwen-plus`，也支持 `qwen-turbo` / `qwen-max` / `deepseek-v3.2`
  等任意你已开通的模型（可手动输入模型名）。
- **获取 Key**：阿里云百炼控制台开通服务后创建 API Key，见
  <https://help.aliyun.com/zh/model-studio/get-api-key>。
- 相关脚本：`node scripts/test_ai.js`（AI 模块逻辑冒烟测试）。

## 📄 参考文档

- [高频知识点总结](docs/ACP高频知识点总结.md) — 基于 1459 道真题提炼
- [真实模拟题](docs/官网真实模拟题.md) — 模拟题整理版

## 📜 许可

仅供学习交流使用。