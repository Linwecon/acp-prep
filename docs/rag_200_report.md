# RAG 200 题精编记录

日期：2026-10-17。当前有效题数：RAG **200**，全站 **1787**。本轮从 356 题再移出 156 题；加上第一轮，RAG 从 446 题累计减少 246 题。

## 保留范围

按 10 类主题各保留 20 题，避免只机械按题号截取。主题归类用于本次选题检查，网站仍以 RAG 章节统一练习。

| 主题 | 题数 |
|---|---|
| RAG 原理与链路 | 20 |
| 文档解析与结构保留 | 20 |
| 文本切片策略 | 20 |
| Embedding 与向量存储 | 20 |
| 查询理解与改写 | 20 |
| 多轮对话与句子窗口 | 20 |
| 召回过滤与重排序 | 20 |
| 高级检索与上下文组装 | 20 |
| RAG 评估与问题定位 | 20 |
| 可靠性权限与应用场景 | 20 |

保留题为 **121 单选、79 多选**，200 题均有解析。既有难度标签分布为入门 77、进阶 104、挑战 19，标签沿用原库，未进行实测难度标定。

## 改题内容

本轮修改或补充了 **131 题**，其中 **94 题**涉及题干、选项、答案或题型变化，另 37 题仅完善解析。主要处理：

- 把孤立的型号、函数名与产品标签记忆题，改成有条件的迁移、恢复、权限和成本场景。
- 修正“关系型数据库不能向量检索”“新 Embedding 必然更好”“Top-K 必定返回 K 条”“保存历史就等于使用历史”等错误或绝对判断。
- 多轮查询区分已有上下文可补全、信息不足需澄清、话题切换和同名实体消歧。
- 句子窗口与父子合并补充重叠去重、来源、权限、合并条件和 Token 预算。
- 评测题区分相似度、召回、排序和忠实度；新增有明确口径的数值题，避免把每个指标都说成必须依赖相同模型。
- 修改曾把问题唯一归因于换模型、提高阈值或上传扫描的题，强调先根据已知条件定位证据丢失环节。
- 给所有缺失解析的保留题补充说明；多选题均包含未选项，避免整题所有选项都勾选。

示例：`3-0537` 检查相关性 `[1,0,1]` 的加权平均精度，答案约 `0.833`；`3-1117` 在多位同名员工且无上下文时先澄清；`3-1456` 检查解析、向量化、生成与日志的完整数据边界。

## 历史记录与恢复

其他 11 章的题目数据按修改前哈希逐章核对，保持一致。保留题沿用原题号；旧作答次数、错题与收藏不清空。题干/选项/答案变化的题带修订时间，早于修订时间的作答快照不会在新版题上直接回显判对错，页面会提示重新作答。历史统计仍保留原作答含义，不自动重新计算过去成绩。

- [200 题保留清单及分组](../data/curate/rag_200_selection.json)
- [131 题的最终修改内容](../data/curate/rag_200_rewrites.json)
- [移出题与修订前原文](../data/curate/rag_200_archive.json)
- 治理台账批次：`rag-200-20261017`（移出），`rag-200-rewrite-20261017`（改题）。

## 核查依据与验证

对实现相关边界参考：[RAGAS 排序指标](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/)、[忠实度](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)、[事实覆盖](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/)、[经典 AnswerCorrectness](https://docs.ragas.io/en/v0.3.9/concepts/metrics/available_metrics/answer_correctness/)、[LlamaIndex 自动合并](https://developers.llamaindex.ai/python/framework/integrations/retrievers/auto_merging_retriever/)、[文件加载](https://developers.llamaindex.ai/python/framework/module_guides/loading/simpledirectoryreader/)、[GraphRAG 索引结构](https://microsoft.github.io/graphrag/index/overview/)、[阿里云检索与排序](https://help.aliyun.com/zh/tablestore/table-store-service/knowledge-storage-retrieval)。这些资料用于技术边界核对，不将社区题目视为官方考试真题。

验证包括：200 个唯一有效题号、200 份非空解析、答案选项与题型合法、移出题不进入运行时、完整版/压缩版一致、模考 230 次抽题符合 75 题及知识域配额、章节导航与记录迁移回归。浏览器逐题检查全部 200 题在 320/390/1440px 无横向溢出，并验证修订提示、旧快照隔离和重新作答判分。Python 80 项测试通过。
