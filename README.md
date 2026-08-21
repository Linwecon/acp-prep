# 🎓 ACP 刷题助手

阿里云大模型高级工程师认证（ACP）备考工具：学习 + 刷题 + 模拟考试。纯前端静态站点，零构建依赖，GitHub Pages 部署，可选 Supabase 登录与云端同步。

## 功能

- **学习**：高频考点阅读器（Markdown 渲染、章节导航、图表/动画）
- **刷题**：12 章 1548 题，单选/多选，全部/未答/错题/收藏筛选，作答历史续做
- **模拟考试**：75 题（50 单选 × 1 + 25 多选 × 2 = 100 分），按官方大纲知识域比例抽题，120 分钟计时，及格线 80 分
- **错题本 / 收藏夹 / 全局搜索 / 深色模式 / 键盘操作**
- **AI 答疑**：答题后调用大模型逐项讲解（OpenAI 兼容接口，多服务商可选，流式输出，结果缓存）
- **登录与云同步**：邮箱密码登录（Supabase Auth），进度/错题/收藏/成绩跨设备同步；未登录时走 localStorage

## 运行

```bash
python -m http.server 8080   # 访问 http://localhost:8080，或直接打开 index.html
```

## 结构

```
acp/
├── index.html  style.css         # 入口 + 样式
├── data/                         # 题库与知识点（运行时加载）
├── js/                           # 无框架模块（IIFE，挂 window.ACP 命名空间）
│   ├── acp.js utils.js store.js data.js
│   ├── sidebar.js dashboard.js chapter.js study.js exam.js search.js
│   ├── ai.js                     # AI 答疑
│   ├── sync.js                   # Supabase 登录 + 云同步
│   └── app.js                    # 启动
├── config/supabase.js            # Supabase 公开 anon key
├── supabase/schema.sql           # 建表 + RLS
├── scripts/                      # 数据与测试脚本（Python + Node）
└── docs/                         # 知识点文档
```

前端为原生 JS，按 `<script defer>` 依赖顺序加载，模块用 IIFE 隔离，状态收口于 `ACP.state`。

## 数据与同步

- 进度存 `localStorage`（`acp_v2_store`），登录后同步 Supabase。
- 表：`user_progress`（进度/错题/章节完成）、`favorites`（收藏）、`exam_records`（成绩）、`user_meta`（续做位置）。
- 合并策略：进度 `done`/`wrong` 取大值、`correct`/`answer` 取时间戳较新者；收藏取并集。
- 登录后「拉取 → 合并 → 回推」，之后每次变更实时推送；RLS 限制用户只能读写 `auth.uid() = user_id` 的行。

## AI 答疑（可选）

侧边栏「🤖 AI 设置」填自己的 API Key，内置阿里云百炼（推荐）/硅基流动/DeepSeek/智谱/Kimi/百川/自定义，也可手动输入任意 OpenAI 兼容地址与模型名。Key 仅存本地 `localStorage`。

## Supabase 配置

1. 执行 `supabase/schema.sql`。
2. Authentication → Providers → Email 开启；如需注册即登录，关闭 Confirm email。
3. URL Configuration 里把站点地址加入 Site URL / Redirect URLs。
4. 把 Project URL + anon public key 填入 `config/supabase.js`。
5. 部署。

只用公开 anon key，禁止 service_role 进入前端。

## 测试

```bash
node scripts/test_*.js          # 前端逻辑冒烟测试
python scripts/build_knowledge.py   # 重新生成知识点数据
```

## 许可

仅供学习交流使用。
