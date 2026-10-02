# 答案检测处置报告

> 生成时间：2026-10-02T16:06:08 · 来源：data/verify_final.json（6 模型投票）

| 分类 | 数量 | 处置 |
|---|---:|---|
| 答案错误（可修正） | 89 | --evidence 核对教材证据后 --apply（保存旧版本可回滚） |
| 结果失效（内容已变） | 0 | 重跑校验，禁止使用旧结论 |
| 多解/条件不足 | 34 | 修复题干或暂停使用，禁止强行改答案 |
| 证据不足 | 22 | 人工复核，不修正 |
| 维持原答案 | 73 | 无需处理 |

## 待修正清单

证据状态：external=教材证据核对通过（可 apply）；vote_only=仅模型投票（apply 拒绝）；rejected=证据核对不通过（拒绝）。

| 题号 | 题库答案 | 终裁答案 | 证据状态 | 票型 | 题干 |
|---|---|---|---|---|---|
| 1-1394 | B | D | rejected | qwen-plus:D / deepseek-v3.2:B / qwen3.7-max:D | 在开发智能系统中，为了防止由于存储工作日志、历史检索数据等导致的大模型上下文过载问题，哪种方法能有效缓解这一压力并保持对话的连贯性？ |
| 1-0411 | C | B | rejected | qwen-plus:B / deepseek-v3.2:B / qwen3.7-max:B | 在使用大语言模型进行文档审阅时，不建议一次输出全部结果，最可能的原因是什么？ |
| 1-1417 | C | B | rejected | qwen-plus:B / deepseek-v3.2:D / qwen3.7-max:B | 在通过大语言模型做文档审阅时，不建议一次返回所有结果，最可能的原因是什么？ |
| 1-0111 | D | C | vote_only | qwen-plus:C / deepseek-v3.2:C / qwen3.7-max:C | 在大模型的问答工作流程中，哪个阶段会循环生成候选Token直到输出结束标记？ |
| 1-0403 | E | C | vote_only | qwen-plus:C / deepseek-v3.2:C / qwen3.7-max:C | 以下哪个用户查询语句不适合用于指导大语言模型生成简洁摘要？ |
| 1-0536 | A,B | A,B,D | vote_only | qwen-plus:A,B,D / deepseek-v3.2:A,B,D / qwen3.7-max:A,B,D | 在私有知识问答场景中，直接传入私域相关的参考信息可能导致哪些问题？ |
| 1-0521 | A,B,C,D | C | vote_only | qwen-plus:C / deepseek-v3.2:C,D / qwen3.7-max:C | 在大模型的问答工作流程中，以下哪些阶段涉及Tone的处理？ |
| 1-0442 | B | A | vote_only | qwen-plus:A / deepseek-v3.2:B / qwen3.7-max:A | 在调用大语言模型对话的API过程中，以下哪个代码片段展示了正确的用户(user)提问方式? |
| 1-0729 | A,B,D,E | A,D,E | vote_only | qwen-plus:A,B,D / deepseek-v3.2:A,D,E / qwen3.7-max:A,D,E | 某电商平台计划使用大模型优化商品推荐系统，希望实现以下目标：个性化推荐、推荐理由生成、多轮对话交互。以下哪些技术方案是合适的？ |
| 2-0815 | D | A | vote_only | qwen-plus:A / deepseek-v3.2:A / qwen3.7-max:A | 某智能助手在处理用户查询时，经常给出过于冗长的回答。以下哪种方法能有效控制回答长度？ |
| 2-0423 | D | C | vote_only | qwen-plus:C / deepseek-v3.2:C / qwen3.7-max:C | 在构建大语言模型提示词过程中，以下哪个分隔符形式不常用于提示词? |
| 2-0474 | A,B | A,B,D | vote_only | qwen-plus:A,B,C,D / deepseek-v3.2:A,B,D / qwen3.7-max:A,B,D | 在自定义提示词模板中，以下哪些是预设的部分信息？ |
| 2-1243 | B,C,D | B,C | vote_only | qwen-plus:B,C / deepseek-v3.2:B,C / qwen3.7-max:B,C | 关于思维链（CoT）提示的设计，下列哪些做法是推荐的？ |
| 2-1437 | D | C | vote_only | qwen-plus:C / deepseek-v3.2:D / qwen3.7-max:D | ask_llm_route 函数在问题类型无法识别时会返回什么？ |
| 2-1025 | B,D,E | D | vote_only | qwen-plus:D / deepseek-v3.2:D / qwen3.7-max:D | 在使用大语言模型时，什么是"样例"的作用？ |
| 2-1448 | B,D,E | D | vote_only | qwen-plus:D / deepseek-v3.2:D / qwen3.7-max:D | 在使用大语言模型时，什么是“样例” 的作用？ |
| 2-0548 | A,B,C,D | A,B,C | vote_only | qwen-plus:A,B,C / deepseek-v3.2:A,B,C / qwen3.7-max:A,B,C | 在提示词框架中，以下哪些要素是必要的? |
| 2-1166 | A,B | B | vote_only | qwen-plus:B / deepseek-v3.2:B / qwen3.7-max:A,B | 以下选项中属于使用分隔符的主要目的有哪些? |
| 2-0630 | A,B,C | A,B | vote_only | qwen-plus:A,B / deepseek-v3.2:A,B / qwen3.7-max:A,B | 在生成插图提示词时，哪些因素有助于提升提示词的可执行性？ |
| 2-0621 | A,B,C,D | A,C,D | vote_only | qwen-plus:A,C,D / deepseek-v3.2:A,C,D / qwen3.7-max:A,C | 在使用思维链（CoT）提示设计LLM提示词时，以下哪些做法是推荐或必要的？ |
| 2-1170 | A,B,C | A,B,C,E | vote_only | qwen-plus:A,B,C,E / deepseek-v3.2:A,B,C,E / qwen3.7-max:A,B,C | abstract_generator 提示词模板包含哪些关键组成部分？ |
| 2-1467 | A,B | A,B,D | vote_only | qwen-plus:A,B,D / deepseek-v3.2:A,B,D / qwen3.7-max:A,B,D |  |
| 2-0606 | A,B,C,E,F | A,B,C,F | vote_only | qwen-plus:A,B,C,F / deepseek-v3.2:A,B,C,F / qwen3.7-max:A,B,C,F | 关于LLM少样本提示（Few-Shot Prompting）中的示例选择，以下哪些说法是正确的？ |
| 2-0830 | B,D | A,B,D | vote_only | qwen-plus:A,B,D / deepseek-v3.2:A,B,D / qwen3.7-max:A,B,D | 通过 LlamaIndex 创建 RAG 应用，在修改默认 prompt 时，包含以下哪些步骤？ |
| 3-1081 | D | B | vote_only | qwen-plus:B / deepseek-v3.2:B / qwen3.7-max:B | 在文档审阅中，为什么不建议一次输出所有的结果？ |
| 3-0248 | A | B | vote_only | qwen-plus:B / deepseek-v3.2:A / qwen3.7-max:B | 在构建 RAG 应用时，以下哪种向量存储方案适合小规模应用？ |
| 3-0145 | B | C | vote_only | qwen-plus:C / deepseek-v3.2:A / qwen3.7-max:B | 在创建索引时，VectorStoreIndex.from_documents方法包含哪些步骤？ |
| 3-0466 | A,B | A | vote_only | qwen-plus:A / deepseek-v3.2:A,B / qwen3.7-max:A | 在检索召回阶段，以下哪些方法用于在检索后减少无关信息？ |
| 3-0489 | A,B,C | B,C | vote_only | qwen-plus:B,C / deepseek-v3.2:B,C / qwen3.7-max:B,C | 哪些操作有助于提高检索的准确性？ |
| 3-0260 | A | C | vote_only | qwen-plus:C / deepseek-v3.2:C / qwen3.7-max:C | 以下哪种问题不需要经过 RAG 链路？ |
| 3-0506 | A,B,C,D | A,B,C | vote_only | qwen-plus:A,B,C / deepseek-v3.2:A,B / qwen3.7-max:A,B | 在检索召回阶段，以下哪些方法用于在检索前还原用户真实意图? |
| 3-0539 | A,B,C | A,B | vote_only | qwen-plus:A,B / deepseek-v3.2:A,B / qwen3.7-max:A,B | 在问题改写中，以下哪些方法通过大模型生成更完整的问题？ |
| 3-0514 | A,B,C,D | A,B,C | vote_only | qwen-plus:A,B,C / deepseek-v3.2:A,B,C / qwen3.7-max:A,B,C | 在构建 RAG 应用时，哪些高级 RAG 课题值得探索？ |
| 3-0623 | A,B,C,D | A,C,D | vote_only | qwen-plus:A,C,D / deepseek-v3.2:A,C,D / qwen3.7-max:A,C,D | 为了提升知识索引的性能，可以采用以下哪些技术手段？ |
| 3-1383 | A,B,C | A,C | vote_only | qwen-plus:A,C / deepseek-v3.2:A,B / qwen3.7-max:A,C | 在构建 RAG 应用时，以下哪些是内存向量存储的优点？ |
| 3-0863 | A,B,C,D,E | A,B,C,D | vote_only | qwen-plus:A,B,C,D / deepseek-v3.2:A,B,C,D / qwen3.7-max:A,B,C,D | 以下哪些属于大模型应用开发中的常见架构模式？（） |
| 3-1152 | C | B | vote_only | qwen-plus:B / deepseek-v3.2:B / qwen3.7-max:B | 你维护了一个开发者社区的大模型问答助手，但你发现有人通过上传一些恶意的文章，诱导大模型生成恶意代码。从长期防护角度，最根本的解决措施是？ |
| 3-1102 | B,C,D | A,B,D | vote_only | qwen-plus:A,B,D / deepseek-v3.2:A,B,D / qwen3.7-max:A,B,D | 某教育问答系统上线后，你通过监控日志发现模型有时会返回个人隐私信息，为防止此类敏感信息泄露，可以采取以下哪三项措施？ |
| 3-0726 | A,B,C,D | A,B,C | vote_only | qwen-plus:A,B,C / deepseek-v3.2:A,B,C / qwen3.7-max:A,B,C,D | 开发者在优化 RAG 应用时，发现 '检索到的文本段与用户问题相关性低'（精度低）。以下哪些措施可有效提升检索精度？ |
| 3-0988 | A,B,C,D,E | A,B,C,D | vote_only | qwen-plus:A,B,C,D / deepseek-v3.2:A,B,C,D / qwen3.7-max:A,B,C,D | 在优化RAG系统时，以下哪些方法可以提升检索质量？ |
| 3-1169 | C,D,E,F | A,C,D,E,F | vote_only | qwen-plus:A,C,D,E,F / deepseek-v3.2:A,C,D,E,F / qwen3.7-max:A,C,D,E,F | 优化 RAG 应用时，需要考虑哪些因素？ |
| 3-0747 | A,B,D | A,D | vote_only | qwen-plus:A,D / deepseek-v3.2:A,D / qwen3.7-max:A,D | 某公司使用大模型生成技术文档，需要确保术语的一致性和准确性。以下哪些方法组合最有效？ |
| 3-1131 | B | A | vote_only | qwen-plus:A / deepseek-v3.2:A / qwen3.7-max:A | 你开发了一个专用于医疗场景问答的 RAG 应用，许多用户都反馈关于疾病症的回答总是得不到正确答案，你应该首先检查哪一环节？ |
| 3-0856 | A,B,C,D,E | A,B,C,E | vote_only | qwen-plus:A,B,C,E / deepseek-v3.2:A,B,C,D,E / qwen3.7-max:A,B,C,E | 以下哪些技术可以用于提升RAG系统中检索器的性能？（） |
| 3-1272 | A,B,C,D | A,C | vote_only | qwen-plus:A,C / deepseek-v3.2:A,C / qwen3.7-max:A,B,C | 使用基于 Markdown 的工具 Marp 创建演示文稿时，以下哪些做法是推荐的？ |
| 3-1466 | A,B,C | A,B,C,D | vote_only | qwen-plus:A,B,C,D / deepseek-v3.2:A,B,C,D / qwen3.7-max:A,B,C,D | 以下哪些方法可能提升Context Recall？ |
| 3-1392 | A,F | A | vote_only | qwen-plus:A,C,E,F / deepseek-v3.2:A,C,D,E,F / qwen3.7-max:A | 在开发大语言模型RAG应用过程中，以下哪些描述符合"基于语义的文档切片"的理念？ |
| 3-1398 | A,B,C,D | A,B,C | vote_only | qwen-plus:- / deepseek-v3.2:A,B,C / qwen3.7-max:A,B,C | 在切片向量化与存储阶段，以下哪些是 Compare_embedding_models 函数的参数？ |
| 3-0638 | A,B,C | A,C | vote_only | qwen-plus:A,C / deepseek-v3.2:A,C / qwen3.7-max:A,B,C | 通过Llamaindex创建RAG应用时，编写了如下代码，关于这段代码作用的描述正确的有哪些？ def get_documents(path): documents = SimpleDirectoryReader(path).load_da |
| 3-0783 | A,B,C,D | A,B,C | vote_only | qwen-plus:A,B,C / deepseek-v3.2:A,B,C / qwen3.7-max:A,B,C,D | 某企业计划基于阿里云大模型开发内部培训助手，要求实现“上传培训课程→模型生成练习题 + 解答思路”的功能。以下哪些组合是必要的？ |
| 3-1466b | A,B,C,E | B,C | vote_only | qwen-plus:B,C / deepseek-v3.2:B,C / qwen3.7-max:B,C |  |
| 4-0386 | D | B | vote_only | qwen-plus:B / deepseek-v3.2:D / qwen3.7-max:B | 在斯坦福小镇多智能体社区研究项目中，智能体间的主要互动模式是什么？ |
| 3-1204 | A,B,C | B,C | vote_only | qwen-plus:A,B / deepseek-v3.2:B,C / qwen3.7-max:A,B,C | 通过 Llamaindex 创建 RAG 应用，这段代码有哪些问题？python query_engine = index.as_query_engine( similarity_top_k=3, streaming=True, node_ |
| 5-0515 | A,B | A,B,C | vote_only | qwen-plus:A,B,C / deepseek-v3.2:A,B,C / qwen3.7-max:A,B,C | 在意图识别中，以下哪些方法可以帮助大模型进行意图识别？ |
| 4-1220 | D | B | vote_only | qwen-plus:B / deepseek-v3.2:B / qwen3.7-max:B | 当用户请求"帮我请明天的假"时，系统需要调用哪些Agent? |
| 4-1338 | B,C,D | B,C | vote_only | qwen-plus:B,C / deepseek-v3.2:B,C / qwen3.7-max:B,C,D | 以下哪些是Multi-Agent系统的核心组件？ |
| 4-1395 | D | C | vote_only | qwen-plus:C / deepseek-v3.2:D / qwen3.7-max:D | 在开发智能体系统中，智能体的工作日志、历史检索数据等等，会占用大量的大模型上下文，影响智能体做规划的性能。无法通过哪些手段来缓解这方面的压力？ |
| 5-1336 | A,B,D | A,B,C,D | vote_only | qwen-plus:A,B,C,D / deepseek-v3.2:A,C,D / qwen3.7-max:A,B,C,D | 以下哪些是训练失败的可能原因? |
| 5-0639 | A,E | A,C,E | vote_only | qwen-plus:A,C,E / deepseek-v3.2:A,C,E / qwen3.7-max:A,E | 以下关于大语言模型预训练与微调关系的描述，哪些是正确的？ |
| 5-0641 | A,B,C,D,E,F | A,C,D,E,F | vote_only | qwen-plus:A,C,D,E,F / deepseek-v3.2:A,C,D,E,F / qwen3.7-max:A,C,D,E,F | 大语言模型微调通常可能涉及哪些步骤？ |
| 5-1264 | B,D | B | vote_only | qwen-plus:B / deepseek-v3.2:B / qwen3.7-max:B | 若训练过程中 loss 持续增加，可能的解决方案是? |
| 5-0670 | A,C,D | A,C,D,E,F | vote_only | qwen-plus:C,D,E,F / deepseek-v3.2:C,D / qwen3.7-max:A,C,D,E,F | 大语言模型微调相比预训练的优势有哪些? |
| 5-0777 | B,C,D | A,B,D | vote_only | qwen-plus:A,B,D / deepseek-v3.2:A,B,D / qwen3.7-max:A,B,D | 某内容创作平台使用大模型生成文章，需要避免版权侵权和内容重复问题。以下哪些方法是有效的？ |
| 5-0644 | B,C,E | B,D,E | vote_only | qwen-plus:B,D,E / deepseek-v3.2:B,D,E / qwen3.7-max:B,D,E | 在微调模型并使用模型检查点 (checkpointing) 时，哪些策略可以帮助和保存最佳模型？ |
| 6-1274 | B | A | vote_only | qwen-plus:A / deepseek-v3.2:A / qwen3.7-max:A | 使用vLLM启动模型服务的正确命令是? |
| 6-1357 | A,B,C | A,C | vote_only | qwen-plus:A,C / deepseek-v3.2:A,C / qwen3.7-max:A,C |  |
| 6-0715 | A,B,C,D | A,B,D | vote_only | qwen-plus:A,B,D / deepseek-v3.2:A,B,D / qwen3.7-max:A,B,D | 开发者在部署大模型应用时，需监控应用的运行状态。以下哪些指标属于核心监控指标? |
| 6-0716 | A,B,C | A,B | vote_only | qwen-plus:A,B / deepseek-v3.2:A,B / qwen3.7-max:A,B,C | 开发者在部署开源大模型时，遇到“GPU 显存不足”的问题。以下哪些解决方案有效？ |
| 7-1294 | B | D | vote_only | qwen-plus:D / deepseek-v3.2:D / qwen3.7-max:D | 在 Ragas 的常见指标中，哪一个不依赖检索覆盖而更关注生成答案本身的表现？ |
| 6-0967 | A,B,C,D,E | A,B,C,D | vote_only | qwen-plus:A,B,C,D / deepseek-v3.2:A,B,C,D / qwen3.7-max:A,B,C,D,E | 在生产环境部署大模型应用时，以下哪些监控指标是关键重要的？ |
| 7-1367 | C | B | vote_only | qwen-plus:B / deepseek-v3.2:B / qwen3.7-max:C | 在 Ragas 中, answer Correctness 指标的主要作用是什么? |
| 8-1372 | A,B,C,D | A,C,D | vote_only | qwen-plus:A,C,D / deepseek-v3.2:A,C / qwen3.7-max:A,C,D | 在大模型的内容安全治理中，哪些措施可用于降低违规输出风险？ |
| 7-0650 | A,B,D | A,B | vote_only | qwen-plus:A,B / deepseek-v3.2:A,B / qwen3.7-max:A,B | 在使用 Ragas 评估 RAG 应用时，answer_correctness 通常由哪些指标共同构成？ |
| 8-0625 | A,B,D,E | A,B,E | vote_only | qwen-plus:B,E / deepseek-v3.2:B,E / qwen3.7-max:A,B,E | 在大模型的内容安全治理中，哪些机制可用于阻断非法或不当生成？ |
| 8-0583 | A,B,C,E | A,C,E | vote_only | qwen-plus:A,C,E / deepseek-v3.2:A,C,E / qwen3.7-max:A,C,E | 为了减少提示攻击的风险，个人用户在使用大语言模型时应采取哪些措施? |
| 8-0600 | A,B,C,D | A,C,D | vote_only | qwen-plus:A,C / deepseek-v3.2:A,C,D / qwen3.7-max:A,B,C | 在个人信息治理的过程中，哪些措施可以有效保护用户的隐私？ |
| 9-0225 | B | A | vote_only | qwen-plus:A / deepseek-v3.2:A / qwen3.7-max:B | 在需要生成新闻初稿和代码的场景中，建议如何设置top_p参数？ |
| 9-0530 | A,B,C | A,C | vote_only | qwen-plus:A / deepseek-v3.2:A,C / qwen3.7-max:A,C | 哪些操作有助于生成更具创造性的文本？ |
| 8-1168 | A,D,E | A,C,D,E | vote_only | qwen-plus:A,C,D,E / deepseek-v3.2:A,C,D,E / qwen3.7-max:C,D,E | 以下哪些代码片段可以有效地对用户输入进行清洗和预处理，以提高大模型应用的安全性？ |
| 8-1418 | B,C | A,B | vote_only | qwen-plus:A,B / deepseek-v3.2:A,B / qwen3.7-max:A,B | 在通过API开发RAG应用时，一般会将APL_KEY配置环境变量，以下选项中关于其原因的解释正确的有哪些? |
| 10-1337 | A,C,D | A,C | vote_only | qwen-plus:A,C / deepseek-v3.2:A,C / qwen3.7-max:A,C | 以下哪些是优化 Qwen-Turbo 输出质量的有效方法？ |
| 9-0555 | A,B,C | A,B,D | vote_only | qwen-plus:A,B,D / deepseek-v3.2:A,B / qwen3.7-max:A,B,C | 在创建提问引擎时，以下哪些参数可以设置？ |
| 10-1314 | B | C | vote_only | qwen-plus:C / deepseek-v3.2:B / qwen3.7-max:C | 以下哪个代码片段正确设置了百炼大语言模型的API key? |
| 10-1210 | A,B,D | A,D | vote_only | qwen-plus:A,D / deepseek-v3.2:A,D / qwen3.7-max:A,D |  |
| 10-1460 | A,B,C,D,E | A,B,C,D | vote_only | qwen-plus:A,B,C,D / deepseek-v3.2:A,B,C,D / qwen3.7-max:A,B,C,D,E | 以下哪些属于阿里云大模型生态的核心产品 / 服务？（多选，5 个选项） |
| 10-0782 | A,B,C,D | A,C,D | vote_only | qwen-plus:A,C,D / deepseek-v3.2:A,C,D / qwen3.7-max:A,B,C,D | 某企业计划构建大模型应用开发平台，支持“模型训练、部署、监控”全流程。以下哪些阿里云产品可作为核心组件？ |
| 11-0643 | A,B,C,D | A,B,D | vote_only | qwen-plus:A,B,D / deepseek-v3.2:B,D / qwen3.7-max:A,B,D | 在使用 CosyVoice 进行语音合成时，哪些做法有助于保证音频质量和自然度？ |
| 11-0740 | A,B,C,D | A,B,C | vote_only | qwen-plus:A,B,C / deepseek-v3.2:A,B,C / qwen3.7-max:A,B,C | 某公司开发大模型智能办公助手，要求实现“会议录音转文字→生成会议纪要→提取待办事项”的功能。以下哪些技术组合可支撑该需求？（多选，5个选项，2-5个正确） |
| 11-0784 | A,B,C,D | A,B,C | vote_only | qwen-plus:A,B,C / deepseek-v3.2:A,B,C / qwen3.7-max:A,B,C | 某企业开发大模型多模态应用，要求‘用户上传产品图片→模型识别产品特征→生成推广文案’。以下哪些技术组件需集成? |

## 多解 / 条件不足（建议暂停使用）

| 题号 | 题库答案 | 票型 | 题干 |
|---|---|---|---|
| 1-1310 | A,B,C | qwen-plus:A,B / deepseek-v3.2:A,B / qwen3.7-max:A,B,C | 以下关于分词化的描述，哪些是正确的？ |
| 1-1113 | B | qwen-plus:D / deepseek-v3.2:D / qwen3.7-max:B | 一口 10 米的井，蜗牛从井底向上爬，每个白天向上爬 3 米，每晚滑下 2 米。请问蜗牛需要多少天能爬出这口井？ |
| 1-1343 | A,B,C,D,E,F | qwen-plus:A,D,F / deepseek-v3.2:A,C,D,F / qwen3.7-max:A,C,D,F | 以下哪些user_query的设计能够有效引导大语言模型进行英文到中文的翻译? |
| 1-1172 | A,E | qwen-plus:A,B,E / deepseek-v3.2:A,B,E / qwen3.7-max:A,B,D,E | 哪些代码段涉及文本序列化和标准化？ |
| 1-1379 | B,C,D | qwen-plus:- / deepseek-v3.2:B,C / qwen3.7-max:B,C | 在调用大语言模型对话的APl过程中，关于abstract_generator(document) 函数，以下说法正确的有哪些? |
| 1-0632 | A,B,C | qwen-plus:- / deepseek-v3.2:A,B,C / qwen3.7-max:A,B | 在调用大语言模型对话的API过程中，关于abstract_generator (document)函数，以下说法正确的有哪些? |
| 2-1453 | A,C | qwen-plus:B,C / deepseek-v3.2:B,C / qwen3.7-max:A,C | 在使用推理大模型时，不推荐使用思维链提示的原因有？ |
| 2-0677 | B,C,D | qwen-plus:A,D / deepseek-v3.2:A,C,D / qwen3.7-max:A,B,C,D | 当发现大模型生成的内容存在事实性错误时，以下哪些方法可以有效改善这一问题？（） |
| 3-0491 | A,B,C | qwen-plus:A,B / deepseek-v3.2:A,B / qwen3.7-max:A,B,C | 在问题改写中，以下哪些方法用于在检索前还原用户真实意图？ |
| 3-0553 | A,B,C | qwen-plus:B,C / deepseek-v3.2:A,B / qwen3.7-max:B,C | 重排序过程中的关键步骤有哪些？ |
| 3-0502 | A,D | qwen-plus:A,C,D / deepseek-v3.2:A,C,D / qwen3.7-max:A,D | 在构建 RAG 应用时，以下哪些是云服务向量存储的适用场景？ |
| 3-1331 | B,C,D | qwen-plus:B,D / deepseek-v3.2:B,D / qwen3.7-max:B,C,D | 以下哪些是检索后处理的方法? |
| 3-1140 | D | qwen-plus:C / deepseek-v3.2:C / qwen3.7-max:D | 某律所希望开发一个基于 RAG 的合同审阅系统，已通过 POC（Proof of Concept，是对客户具体应用的验证性测试）验证了系统对于一些常见问题的准确性和效率。下一步应该优先做什么？ |
| 3-1293 | A,B,D | qwen-plus:A,B,C,D / deepseek-v3.2:A,B,D / qwen3.7-max:A,B,D | 文档解析阶段可能遇到的问题包括哪些? |
| 3-0589 | A,B,C | qwen-plus:B,C / deepseek-v3.2:B,C / qwen3.7-max:A,B,C | 下列哪些方法是用于提高大模型在RAG框架中对问题理解的能力？ |
| 3-0513 | A,B,C | qwen-plus:- / deepseek-v3.2:A,B,C / qwen3.7-max:A,B,C | 在切片向量化与存储阶段，以下哪些是 compare_em beddings 函数的参数？ |
| 3-0728 | A,B,D | qwen-plus:A / deepseek-v3.2:A,B,D / qwen3.7-max:A,B | 某电商平台计划开发大模型智能客服系统，需实现“用户咨询商品售后政策”->“模型精准回答”+“推荐相关售后流程文档”的功能。以下哪些技术方案可支撑该需求？ |
| 3-1026 | A,B,C,E | qwen-plus:B,C / deepseek-v3.2:A,B,C / qwen3.7-max:B,C | 用户上传了一个包含复杂表格的 Markdown 文档，使用默认的 RAG 流程进行问答。用户提问关于表格含义的问题时，大模型经常给出错误或不相关的答案。请问以下哪些方案可以尝试解决这个问题？ |
| 4-1325 | A,B,C,D | qwen-plus:A,B,C / deepseek-v3.2:B,C / qwen3.7-max:A,B,C,D | 以下哪些技术可与Multi-Agent系统结合？ |
| 5-0480 | A,B,C | qwen-plus:A,C / deepseek-v3.2:A,C / qwen3.7-max:A,B,C | 以下哪些方法可以让大模型能够回答私域知识问题？ |
| 5-1307 | C,F | qwen-plus:B,C,F / deepseek-v3.2:C,F / qwen3.7-max:C,F | 以下关于大语言模型预训练与微调分工关系的说法，哪些是正确的？ |
| 5-0930 | A,B,C,D,E | qwen-plus:A,B,D,E / deepseek-v3.2:A,B,D,E / qwen3.7-max:A,B,C,D,E | 在进行大模型微调时，以下哪些说法是正确的？（） |
| 5-1067 | A,B,C | qwen-plus:A,B / deepseek-v3.2:A,B / qwen3.7-max:B,C | 微调 qwen2.5 - 1.5b 模型过程中发现模型开始欠拟合，可采取的优化措施包括？ |
| 6-0878 | A,B,C | qwen-plus:A,C / deepseek-v3.2:A,B,C / qwen3.7-max:A,C | 在大模型部署优化中，以下哪些技术能降低模型的显存占用？ |
| 6-1364 | A,B,C | qwen-plus:A,C / deepseek-v3.2:A,B,C / qwen3.7-max:A,B,C | 在大模型部署优化中，以下哪些技术能降低模型的显存占用？（多选，4 个选项） |
| 7-1465 | A,B | qwen-plus:B / deepseek-v3.2:B / qwen3.7-max:A,B | 在RAGAS评测体系中，以下哪些属于召回阶段的评估指标？ |
| 8-1287 | A,B,C,D | qwen-plus:B,C / deepseek-v3.2:B,C / qwen3.7-max:A,B,C,D | 以下哪些代码片段可以用于检测用户输入中是否包含敏感词？ |
| 9-0995 | A,C,D,F | qwen-plus:A,D,F / deepseek-v3.2:A,C,D,F / qwen3.7-max:C,D,E,F | Assistant API 中 Message 类包含了各类关于消息的函数，以下哪些选项属于 Message 类中的函数？ |
| 10-0596 | A,C | qwen-plus:A,C,D / deepseek-v3.2:A,B,C,D / qwen3.7-max:A,B,C,D | 以下选项中，百炼平台目前支持导入的数据格式有哪些? |
| 10-0861 | A,B,C,D,E | qwen-plus:A,B,C / deepseek-v3.2:A,B,C,D / qwen3.7-max:A,B,C,D,E | 以下哪些属于阿里云大模型生态的核心产品 / 服务? |
| 10-1199 | B,C,D,F | qwen-plus:B,C,F / deepseek-v3.2:B,C,D,F / qwen3.7-max:A,F | APIAssistantAgent 的 query 函数里，哪些步骤与大语言模型交互？ def query(self, query: str): """ query: string, the query string to the assi |
| 11-1032 | A,B,D,F | qwen-plus:A,B,F / deepseek-v3.2:B,D,F / qwen3.7-max:A,B,D,F | 以下哪些 Python 库可以用于处理视频或图像？ |
| 11-1413 | A,B,E | qwen-plus:A,B,D,E / deepseek-v3.2:A,E / qwen3.7-max:A,B,E | 在使用 CosyVoice 合成语音时，哪些方式有助于提升最终音频的自然度与质量？ |
| 11-1100 | A,B,C | qwen-plus:A,C / deepseek-v3.2:B,C / qwen3.7-max:A,B,C | 你负责的短视频平台在接入多模态技术后出现故障。1: 用户输入“生成夏日海滩 vlog 背景”时，系统返回静态图片而非视频 2: 视频自动剪辑功能无法识别冲浪板等特定物体 3: 添加的 AI 解说语音与动画动作不同步需要重点检查的技术环节是? |

## 证据不足（人工复核）

| 题号 | 题库答案 | 题干 |
|---|---|---|
| 1-0576 | A,C | 在大模型推理阶段，以下哪些因素会影响模型选择一个输出的Token? |
| 1-1342 | A,B,C,D,E,F |  |
| 2-0504 | A,B |  |
| 1-1200 | A,B,C,D | 以下哪些代码片段可以用于检测用户输入中是否包含敏感词? |
| 2-0479 | A,B |  |
| 2-0522 | A,B,C | 该提示词中规定了哪些任务要求？ |
| 1-1393 | C,E,F | 在开发基于RAG的智能答疑机器人过程中，以下那些代码可以用于检测用户输入中是否包含敏感词？ |
| 2-0469 | A,B,C,D | 该提示词中规定了哪些输出要求？ |
| 3-0503 | A,B | 以下哪些内容属于知识库召回结果？ |
| 3-0529 | A,B,C,D | 在切片向量化与存储阶段，以下哪些是 compare_em bedding_models 函数的参数？ |
| 3-1235 | A,B | 关于 node_postprocessors 的参数设置，以下哪些是合理的? |
| 3-0642 | A,D | 通过LlamaIndex创建RAG应用时，编写了如下代码，这段代码有哪些问题？ |
| 4-1018 | A | 在使用Assistant API 的 Assistant 类操作智能体过程中，使用了如下代码，分析这段代码主要的作用是什么？ |
| 4-0599 | C,D | 下列哪些技术或领域特别适合利用单Agent系统的集中处理能力？ |
| 5-0008 | C | 下面是一qwen2.5-1.5b 微调训练过程中的损失趋势图，当前的状态是？ |
| 5-1303 | C | 下面是一qwen2.5-1.5b 微调训练过程中的损失趋势图，当前的状态是？dd677d671ff006c466a528e0e9a3c59.png |
| 4-0588 | B,C,E | 大模型Agent自动处理任务时，可以减少哪些人工工作量？ |
| 5-1162 | A,B,E | 在监控大语言模型训练性能时，哪些指标是常用的？ |
| 9-0463 | A | 关于如下代码的解释中，正确的是哪一项？ |
| 10-0640 | A,B,C |  |
| 10-1388 | B,C,D,F | APIAssistantAgent 的 query 流程里，哪些步骤与大语言模型交互？def query(self, query:str):"""query: string, the query string to the assistan |
| 10-1426 | B,F | 在下列 Assistant API 示例代码的 query 方法中，dashscope.Runs.wait 的以下哪些作用描述是正确的？ class APIAssistantAgent(AgentModule):def query(self |
