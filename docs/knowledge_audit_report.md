# 知识点章节审查记录

核查日期：2026-10-17。范围：`ACP高频知识点总结.md` 的 12 章、124 个编号知识点及 3 个附录；同步更新前端 `data/knowledge.js`。

本次检查章节结构、概念一致性、公式算例、易错结论、代码阅读风险及产品版本边界。修正了已确认的问题；没有在真实云账号中运行教程代码，也不将项目题库认定为官方真题。课程中的实验分数、模型效果和成本数据不能作为其他环境的保证。本次没有逐题修改练习题库。

## 结构与学习体验

- 清除误插入前言的 10 份重复章节总结，接回被截断的“第 5 章……第 6 章……”学习路径。正文已有各章速记和自测，保留这些内容。
- 追溯到 `enhance_learning_doc.py`：章节内偏移被当作全文偏移，插入后还继续使用旧坐标。改为从后往前处理、使用绝对位置、遇到既有自测跳过、尊重附录边界；增加重复运行检查。
- 保持所有章标题、知识点数量与顺序，沿用掌握状态的存储键。修正少量知识点标题不改变其索引。
- 章节目录改为 12 色封面，常驻六领域占比图；正文使用相应章节色。导读和解析可展开，增加本章知识点跳转，避免长文只能连续滚动。

## 逐章结论与已完成修正

| 章节 | 审查发现与处理 |
|---|---|
| 1. 大模型基础（12 点） | 补充因果注意力掩码；区分可变长与无限长度、上下文学习与权重更新；纠正 Top-p=0.9 的候选累计算例；公式改为网页可直接阅读的形式；采样参数注明模型差异；将有歧义的参数自测改为明确的控制变量实验。流式展示不保证改善服务端 TTFT。 |
| 2. 提示工程（11 点） | CoT 可能有帮助，也可能传播中间错误；输出解释不能视作内部推理的完整记录。保留提示边界、结构约束与校验的教学内容，不将分隔符当作可靠安全边界。 |
| 3. RAG（10 点） | Top-K/阈值放宽不必然降低精确率；更新文档可增量更新索引，非每次重建全库。同步修正相关自测解析，避免口诀覆盖技术条件。 |
| 4. Agent（12 点） | MCP 不强制使用模型原生 Function Calling；动态发现仍需 Host 支持和权限配置。长期记忆跨会话保存，检索注入后依然受上下文预算限制。 |
| 5. 微调与训练（10 点） | 删除“微调不能学习新知识”的结论；区分黑盒样本蒸馏与广义软标签/特征蒸馏；修正“学生不可能超过教师”的绝对判断及对应自测。LoRA 图示是 ΔW=BA，说明省略的缩放项；0.4% 是指定层的例算，不是全模型常数；去掉固定“保留 97% 能力”的泛化保证。 |
| 6. 部署与推理（12 点） | FP16/BF16 不是数值无损；量化加速依硬件和算子而定。修正蒸馏交叉章节编号。保留 Prefill/Decode、KV Cache、PagedAttention 与连续批处理的分工。 |
| 7. 模型评估（9 点） | Context Precision 分子补乘相关性标记 v_k，增加 `[1,0,1] → 0.833` 反例；不能与 Lost in the Middle 等同。AnswerCorrectness 的 0.75/0.25 是可配置默认值，题干补版本/默认权重条件；不同指标不一定同时需要 LLM 与 Embedding。标注旧版 RAGAS 代码接口，避免混用新版本；指标组合不能唯一断定故障根因。 |
| 8. 安全与合规（10 点） | 备案、个人信息处理依据、数据出境及生成合成标识补适用条件；不再将界面一句提示等同全部标识义务。日志按必要性和期限留存并脱敏。区分基础 WAF 与已接入 AI 防护的 WAF；ACL 优先下推检索且覆盖缓存/重排/日志；裸 CTR 缺完整性保护，普通密文不能直接向量检索，保距加密有安全取舍。 |
| 9. API（11 点） | 流式示例处理无 choices/无正文帧；流式与 TTFT 区分。重试不再简单以 4xx 一刀切，补错误子码、预算、Retry-After 和幂等条件。采样可同时配置，但控制变量更便于调参归因。 |
| 10. 阿里云平台（9 点） | 百炼不只提供应用构建，也提供模型 API；API Key 不能无条件跨地域、计费方案和空间混用。保留示例北京兼容地址并链接当前 Base URL 总览；传统型号定位不等于当前绝对能力排名。 |
| 11. 多模态（10 点） | 文生图不限定为扩散一种架构；区分内容安全增强版与安全护栏。长音视频示例的异步模式不能泛化为所有实时接口。标识义务与第 8 章对齐。 |
| 12. 框架与工具（8 点） | 明确课程 LangChain 0.3 与 v1 的边界；旧功能有迁移，Runnable 接口不保证每个组件均具备原生流式/异步。LangGraph 可独立使用。索引可增量更新，安全章节交叉引用修正。 |
| 3 个附录 | 同步修正注意力、阈值、模型排名、平台凭据、质量与安全交叠等条目；参数题不应背成所有模型共用的常数。 |

## 主要核查依据

- [ACP 大纲变更公告](https://help.aliyun.com/zh/document_detail/2986614.html)：六领域占比为 17/15/20/16/16/16%，学习章节与知识域并非一一对应。
- [百炼介绍](https://help.aliyun.com/zh/model-studio/what-is-model-studio)、[Base URL 总览](https://help.aliyun.com/zh/model-studio/base-url)：平台定位、调用地址与凭据边界。
- [MCP 架构](https://modelcontextprotocol.io/docs/learn/architecture)：Host/Client/Server 及协议与模型调用的分工。
- [LoRA 论文](https://arxiv.org/abs/2106.09685)、[知识蒸馏论文](https://arxiv.org/abs/1503.02531)：参数高效适配、合并和教师监督。
- [RAGAS Context Precision](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/)、[Answer Correctness](https://docs.ragas.io/en/v0.3.9/concepts/metrics/available_metrics/answer_correctness/)、[版本迁移说明](https://docs.ragas.io/en/v0.4.3/howtos/migrations/migrate_from_v03_to_v04/)：公式与代码版本边界。
- [AI 安全护栏与内容安全](https://help.aliyun.com/zh/document_detail/2573826.html)、[WAF AI 应用防护](https://help.aliyun.com/zh/waf/web-application-firewall-3-0/ai-application-protection/)：不同防护产品及配置的能力边界。
- [生成式 AI 暂行办法](https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm)、[标识办法答问](https://www.cac.gov.cn/2025-03/14/c_1743654685896173.htm)、[数据跨境规定答问](https://www.cac.gov.cn/2024-03/22/c_1712776611649184.htm)、[个人信息保护法公报](https://wb.flk.npc.gov.cn/flfg/PDF/f67af9f12e1b4c83a998cf5a876ce0e4.pdf)：相应条目的适用条件。
- [DCPE 实现与安全取舍](https://ironcorelabs.com/docs/cloaked-ai/how-it-works/)、[LangChain v1 迁移](https://docs.langchain.com/oss/python/migrate/langchain-v1)：向量保护和框架迁移边界。

## 验证与后续边界

内容结构回归检查覆盖：12 章顺序、124 个知识点编号、每章自测、前言完整性、关键公式与增强脚本的章节边界和幂等性。生成后的 Markdown 还经过现有渲染检查，检查锚点与表格结构；界面用 Edge/Playwright 检查桌面、手机、明暗主题与学习交互。

这份记录不能证明所有课程代码在当前云服务与依赖组合中可直接运行。旧版 RAGAS/LangChain 示例保留作课程理解，真正实操需固定依赖并按对应官方文档迁移；云账号收费、权限和线上模型效果未做实测。练习题库若引用了旧口诀，仍需要单独做题目与解析一致性审查。
