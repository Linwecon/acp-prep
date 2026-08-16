"""
ACP 题目分类器：基于关键词权重将原始题库归入 12 个知识点章节
"""
import json
import html
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_FILE = DATA_DIR / "raw" / "quiz_data.json"
PROCESSED_JSON_FILE = DATA_DIR / "processed" / "quiz_categorized.json"
BUILD_JS_FILE = DATA_DIR / "build" / "quiz_categorized.js"

# 12 个知识点章节（与 ACP高频知识点总结.md 对齐）
CHAPTERS = {
    1:  "大模型基础",
    2:  "提示工程",
    3:  "RAG 检索增强生成",
    4:  "Agent 智能体",
    5:  "模型微调与训练",
    6:  "模型部署与推理优化",
    7:  "模型评估",
    8:  "AI 安全与合规",
    9:  "API 调用与工具使用",
    10: "阿里云 AI 平台",
    11: "多模态 AI",
    12: "框架与工具",
}

# 每个章节的关键词规则： (关键词列表, 权重)
# 权重越高表示该关键词对该章节的指向性越强
RULES = {
    1: {  # 大模型基础
        "keywords": [
            ("大语言模型", 5), ("大模型的基础", 5), ("LLM的基础", 5), ("语言模型是", 5),
            ("Token", 4), ("词元", 4), ("分词化", 4), ("分词", 2),
            ("参数规模", 5), ("参数数量", 4), ("模型参数", 3), ("B参数", 3), ("亿参数", 3),
            ("上下文窗口", 5), ("上下文长度", 4), ("context window", 5),
            ("Transformer", 5), ("自注意力", 5), ("Self-Attention", 5), ("注意力机制", 4),
            ("幻觉", 4), ("Hallucination", 5), ("知识截止", 4), ("训练数据截止", 4),
            ("预训练", 3), ("模型能力", 3), ("模型局限", 4), ("模型的工作流程", 4),
            ("大模型的优势", 4), ("模型生成内容", 3), ("LLM 的", 3),
            ("概率选择", 3), ("候选 Token", 4), ("采样策略", 3),
            ("语言模型能", 3), ("生成式AI", 3), ("生成式人工智能", 3),
            ("应用开发", 3), ("核心流程", 4), ("开发流程", 4),
            ("模型输出", 2), ("模型会", 1),
        ],
    },
    2: {  # 提示工程
        "keywords": [
            ("提示工程", 5), ("提示词设计", 5), ("提示词优化", 4), ("提示词模板", 4),
            ("提示词", 3), ("Prompt", 4), ("prompt", 3),
            ("System Prompt", 5), ("系统提示词", 5), ("系统提示", 4),
            ("Few-shot", 5), ("few-shot", 5), ("少样本", 4), ("Zero-shot", 5), ("零样本", 4),
            ("思维链", 5), ("Chain-of-Thought", 5), ("CoT", 5), ("一步一步思考", 4),
            ("Temperature", 2), ("温度参数", 3), ("输出随机性", 3),
            ("明确角色", 4), ("明确任务", 3), ("明确受众", 3), ("设定约束", 4),
            ("提供示例", 4), ("分步引导", 4),
            ("样例", 5), ("示例输入", 4), ("提示词最有效", 7),
            ("适配到中文问答场景", 8), ("翻译为中文", 6), ("优化 prompt", 8),
            ("优化prompt", 8), ("忠实反映", 6), ("不要引入原文之外的信息", 8),
            ("ask_llm_route", 7),
            ("提示信息", 3), ("输入提示", 3), ("提示策略", 4),
            ("输出格式", 2), ("回答格式", 2),
            ("写出", 1),  # low weight, catches "写出提示词" etc
        ],
    },
    3: {  # RAG
        "keywords": [
            ("RAG", 5), ("检索增强", 5), ("检索增强生成", 5),
            ("知识库", 3), ("外部知识", 3), ("外部信息", 3),
            ("文档解析", 5), ("文本切片", 5), ("切片策略", 5), ("切片大小", 5),
            ("Chunk", 5), ("chunk", 5), ("切片", 3),
            ("Embedding", 5), ("embedding", 5), ("向量化", 5), ("向量嵌入", 5),
            ("向量数据库", 4), ("向量存储", 4), ("向量检索", 4),
            ("召回", 4), ("召回率", 4), ("检索结果", 3), ("检索质量", 4),
            ("ReRank", 5), ("重排", 5), ("重排序", 4),
            ("余弦相似度", 5), ("相似度计算", 4), ("相似度搜索", 4),
            ("Top K", 4), ("top_k", 4), ("similarity_top_k", 4),
            ("文本检索", 3), ("信息检索", 3), ("检索系统", 3),
            ("语义检索", 4), ("语义搜索", 4), ("语义匹配", 4),
            ("关键词检索", 3), ("混合检索", 4),
            ("文档索引", 4), ("创建索引", 3), ("索引构建", 3),
            ("段落检索", 4), ("句子滑窗", 5),
            ("知识检索", 3), ("动态检索", 3),
            ("检索器", 4), ("Retriever", 5),
            ("Markdown", 2),  # in context of document parsing
            ("改写 query", 8), ("query 改写", 8), ("检查知识库", 8),
            ("知识库内容", 6), ("更换 embedding 模型", 8), ("检索阶段", 5),
            ("CondenseQuestionChatEngine", 8), ("超长文档", 8), ("长文档", 6),
        ],
    },
    4: {  # Agent
        "keywords": [
            ("Agent", 5), ("智能体", 5), ("agent", 5),
            ("多智能体", 5), ("Multi-Agent", 5), ("多Agent", 5),
            ("Planner", 5), ("规划器", 5), ("调度", 3),
            ("Agent", 4), ("智能体架构", 4),
            ("工具调用", 3), ("Function Calling", 3), ("function calling", 3),
            ("Agent 的", 4), ("智能体的", 4),
            ("独立凭据", 5), ("共用凭据", 5), ("账号凭据", 5),
            ("中央调度", 5), ("Planner Agent", 5),
            ("Agent 框架", 4), ("ModelScope-Agent", 5),
            ("记忆模块", 3), ("Memory", 2),
            ("单Agent", 5), ("多Agent系统", 5),
            ("Agent设计", 4), ("设计Agent", 4),
        ],
    },
    5: {  # 模型微调与训练
        "keywords": [
            ("微调", 4), ("Fine-tuning", 5), ("fine-tuning", 5), ("Fine-tune", 5),
            ("全参微调", 5), ("全量微调", 5),
            ("SFT", 5), ("监督微调", 5),
            ("LoRA", 5), ("QLoRA", 5), ("低秩适配", 5),
            ("PEFT", 5), ("参数高效微调", 5),
            ("RLHF", 5), ("人类反馈强化学习", 5),
            ("DPO", 5), ("直接偏好优化", 5),
            ("训练过程", 3), ("训练数据", 2), ("训练集", 3), ("验证集", 3),
            ("过拟合", 5), ("泛化能力", 4),
            ("损失函数", 5), ("Loss", 4), ("loss", 4),
            ("学习率", 5), ("learning rate", 5),
            ("数据标注", 3), ("标注数据", 3), ("训练样本", 3),
            ("指令微调", 4), ("指令数据集", 4),
            ("Epoch", 4), ("epoch", 4), ("Batch", 3), ("batch", 3),
            ("模型训练", 2), ("训练模型", 2),
            ("增量训练", 4), ("继续训练", 3),
            ("微调方法", 4), ("微调策略", 4),
            ("微调前", 4), ("启动微调", 4), ("进行微调", 3),
        ],
    },
    6: {  # 模型部署与推理优化
        "keywords": [
            ("模型部署", 5), ("部署模型", 5), ("部署到", 3), ("上线部署", 4),
            ("量化", 4), ("INT8", 5), ("INT4", 5), ("FP16", 4), ("FP32", 3),
            ("GPTQ", 5), ("AWQ", 5), ("训练后量化", 5),
            ("vLLM", 5), ("TGI", 5), ("Text Generation Inference", 5),
            ("推理框架", 4), ("推理引擎", 4), ("推理加速", 3), ("推理优化", 3),
            ("QPS", 5), ("吞吐量", 3), ("并发", 3), ("并发限制", 4),
            ("限流", 4), ("弹性伸缩", 4),
            ("MaaS", 5), ("模型即服务", 5),
            ("PagedAttention", 5), ("连续批处理", 5),
            ("GPU", 2), ("显存", 2), ("显卡", 2),
            ("响应时间", 3), ("延迟", 2), ("RT", 3),
            ("推理性能", 3), ("推理速度", 3), ("推理效率", 3),
            ("模型服务化", 4), ("模型上线", 3),
            ("资源调度", 3), ("算力", 2),
            ("部署方式", 3), ("部署策略", 3),
            ("服务部署", 2), ("Context Cache", 8), ("上下文缓存", 8),
            ("BatchAPI", 8), ("批量推理", 8), ("成本优化", 4),
        ],
    },
    7: {  # 模型评估
        "keywords": [
            ("模型评估", 5), ("评估模型", 4), ("评测模型", 4),
            ("BLEU", 5), ("ROUGE", 5), ("Perplexity", 5), ("困惑度", 5),
            ("准确率", 3), ("精确率", 3), ("F1分数", 4), ("F1", 3),
            ("自动化评估", 5), ("自动化评分", 5), ("自动评估", 5),
            ("LLM-as-Judge", 5), ("LLM as Judge", 5), ("裁判模型", 5),
            ("人工评测", 4), ("人工评估", 4), ("专家评测", 4),
            ("评估指标", 4), ("评价指标", 4), ("评测指标", 4),
            ("评估方法", 3), ("评估体系", 3), ("评估标准", 3),
            ("基准测试", 4), ("Benchmark", 4), ("benchmark", 4),
            ("模型效果", 2), ("效果评估", 3), ("性能评估", 2),
            ("evaluate", 3), ("evaluation", 3),
            ("评测集", 3), ("测试集", 2),
            ("RAGAS", 8), ("ragas", 8), ("Faithfulness", 7), ("faithfulness", 7),
            ("Answer Correctness", 7), ("Answer Relevancy", 7), ("Answer Relevance", 7),
            ("Context Precision", 7), ("Context Recall", 7),
            ("整体回答质量", 6), ("生成阶段", 5), ("召回阶段", 5),
            ("ground_truth", 4), ("ground truth", 4),
        ],
    },
    8: {  # AI 安全与合规
        "keywords": [
            ("安全", 2), ("合规", 3), ("安全风险", 4), ("内容安全", 4),
            ("越狱攻击", 5), ("Jailbreak", 5), ("jailbreak", 5),
            ("提示注入", 5), ("Prompt Injection", 5), ("prompt injection", 5),
            ("内容审核", 5), ("内容过滤", 4), ("安全过滤", 4),
            ("Guardrail", 5), ("护栏", 5),
            ("API Key", 3), ("API密钥", 4), ("密钥管理", 4), ("密钥安全", 4),
            ("环境变量", 2),  # in context of security
            ("数据脱敏", 5), ("数据安全", 4), ("隐私", 3),
            ("访问控制", 4), ("权限管理", 3), ("RAM", 2),
            ("审计日志", 4), ("审计", 3),
            ("传输加密", 4), ("HTTPS", 3), ("加密传输", 3),
            ("安全防护", 3), ("安全机制", 3), ("安全措施", 3),
            ("违法信息", 4), ("违规内容", 4),
            ("偏见", 3), ("歧视", 3),
            ("合规步骤", 4), ("合规要求", 4), ("上下文污染", 8),
            ("Context Contamination", 8), ("敏感词", 7),
            ("备案", 6), ("合规备案", 7), ("算法备案", 7),
            ("非法查询", 4),
            ("注入攻击", 4),
        ],
    },
    9: {  # API 调用与工具使用
        "keywords": [
            ("API调用", 4), ("调用API", 4), ("API 调用", 4),
            ("temperature", 3), ("top_p", 4), ("top_p参数", 10), ("top_k", 3), ("max_tokens", 4),
            ("seed参数", 4), ("随机种子", 3), ("stop参数", 4),
            ("累计概率", 6), ("Token 超出限制", 12), ("超出限制", 5),
            ("API参数", 3), ("参数设置", 2),
            ("SDK", 3), ("HTTP请求", 3), ("请求头", 3),
            ("JSON-Schema", 5), ("JSON Schema", 5), ("Schema定义", 4),
            ("工具描述", 3), ("参数定义", 2), ("参数提取", 3),
            ("Function Calling", 3), ("function calling", 3), ("工具调用", 2),
            ("API Key", 2),  # lower weight here, higher in security
            ("端点", 2), ("Endpoint", 3),
            ("状态码", 3), ("错误码", 3), ("返回码", 3),
            ("流式输出", 3), ("stream", 3), ("SSE", 4),
            ("回调函数", 2), ("异步调用", 2),
            ("API接口", 2), ("接口调用", 2),
            ("请求参数", 2), ("响应格式", 2),
        ],
    },
    10: {  # 阿里云 AI 平台
        "keywords": [
            ("百炼", 5), ("阿里云百炼", 5), ("百炼平台", 5),
            ("DashScope", 5), ("dashscope", 5), ("DashScopeParse", 5),
            ("PAI", 4), ("MaxCompute", 5), ("OSS", 3), ("DataWorks", 5),
            ("阿里云", 3), ("通义千问", 3), ("Qwen", 3),
            ("Qwen-Plus", 5), ("Qwen-Max", 5), ("Qwen-Turbo", 5),
            ("模型广场", 5), ("Prompt调试", 4),
            ("阿里云模型", 4), ("阿里云服务", 3),
            ("弹性伸缩", 2),  # Alibaba Cloud context
            ("计算服务", 2), ("大数据计算", 3),
            ("模型服务", 2),
            ("云服务", 2), ("云平台", 2),
            ("批量推理服务", 8), ("离线方式处理数据", 8),
            ("开发效率", 5),
            ("CosyVoice", 5), ("通义万相", 5), ("通义听悟", 5),
            ("Paraformer", 5), ("SenseVoice", 5),
        ],
    },
    11: {  # 多模态 AI
        "keywords": [
            ("多模态", 5), ("多模态模型", 5), ("多模态AI", 5),
            ("图像识别", 4), ("图像理解", 4), ("图像生成", 4),
            ("语音识别", 4), ("语音合成", 4), ("语音转文本", 4),
            ("ASR", 5), ("TTS", 5), ("OCR", 4),
            ("视频理解", 4), ("视频分析", 4), ("视频处理", 3),
            ("视觉模型", 4), ("视觉识别", 4), ("视觉理解", 4),
            ("音频处理", 3), ("音频分析", 3),
            ("文本转语音", 4), ("文字转语音", 4),
            ("图像与文本", 4), ("图文", 3),
            ("拍照", 2), ("图片", 2), ("照片", 1),
            ("语音播报", 3), ("语音输出", 3),
            ("通义万相", 3), ("通义听悟", 3),
            ("CosyVoice", 4), ("语音克隆", 4),
        ],
    },
    12: {  # 框架与工具
        "keywords": [
            ("LangChain", 5), ("langchain", 5),
            ("LlamaIndex", 5), ("llamaindex", 5), ("llama_index", 5),
            ("Unstructured", 5), ("PDFPlumber", 5),
            ("Chain", 3), ("链式调用", 4), ("处理链", 4),
            ("Prompt Template", 4), ("提示模板", 3),
            ("Memory", 2), ("对话记忆", 3), ("记忆组件", 4),
            ("Retriever", 3), ("检索器组件", 4),
            ("ChatEngine", 4), ("Data Agent", 4),
            ("context_str", 5),
            ("SentenceWindowNodeParser", 7), ("MetadataReplacementPostProcessor", 7),
            ("SimpleDirectoryReader", 7), ("get_nodes_from_documents", 6),
            ("VectorStoreIndex.from_documents", 7), ("index.storage_context.persist", 7),
            ("load_index_from_storage", 7), ("Dataset.from_dict", 7),
            ("框架", 2), ("工具库", 2),
            ("自定义Reader", 4), ("自定义 Reader", 4),
            ("解析工具", 2), ("解析库", 3),
            ("Tool", 2), ("工具组件", 3),
            ("ConversationBufferMemory", 5), ("ConversationChain", 5),
        ],
    },
}

# 从分析文本中的额外关键词
ANALYSIS_RULES = {
    "RAG": 3,
    "Agent": 4,
    "微调": 5,
    "提示工程": 5,
    "量化": 6,
    "部署": 6,
    "评估": 7,
    "安全": 8,
    "API": 9,
}

# 面向初学者的章节学习顺序：先基础，再工具/API，再进阶主题
BEGINNER_CHAPTER_ORDER = [1, 2, 9, 10, 3, 11, 4, 5, 6, 7, 8, 12]
CHAPTER_BASE_SORT = {
    ch: order * 10 for order, ch in enumerate(BEGINNER_CHAPTER_ORDER)
}

NEGATION_HINTS = (
    "不正确", "错误", "不能", "不包括", "不属于", "不常用于",
    "不能有效", "不支持", "不需要", "不适合"
)
CODE_HINTS = (
    "代码", "Python", "API", "SDK", "JSON", "Schema", "schema",
    "client.", "completion", "cosine_similarity", "embedding",
    "prompt", "XML", "HTTP", "HTTPS", "SQL"
)
EASY_HINTS = (
    "什么是", "主要作用", "核心设计", "核心概念", "用于评估什么",
    "以下哪种", "以下哪项", "以下哪个", "主要优势"
)

# 已人工确认的坏题修正表：只修有把握的题，避免误改题意
MANUAL_FIXES = {
    (1, "0072"): {
        "chapter": 7,
    },
    (1, "0078"): {
        "chapter": 9,
    },
    (1, "0080"): {
        "chapter": 2,
    },
    (1, "0086"): {
        "chapter": 2,
    },
    (1, "0092"): {
        "chapter": 7,
    },
    (1, "0101"): {
        "chapter": 3,
    },
    (1, "0104"): {
        "chapter": 3,
    },
    (1, "0133"): {
        "chapter": 2,
    },
    (1, "0143"): {
        "chapter": 3,
    },
    (1, "0150"): {
        "chapter": 7,
    },
    (1, "0155"): {
        "chapter": 3,
    },
    (3, "0160"): {
        "chapter": 7,
        "answer": "A,B,C",
        "analysis": "RAGAS 中与回答质量直接相关的指标包括 Answer Correctness、Answer Relevancy 和 Faithfulness；Context Precision 更偏向检索排序质量，不属于整体回答质量本身。",
    },
    (1, "0183"): {
        "chapter": 3,
    },
    (1, "0208"): {
        "chapter": 2,
    },
    (3, "0215"): {
        "answer": "A,B",
        "analysis": "本地向量数据库更适合小规模应用与开发测试场景；在大规模或高并发生产环境中，通常会考虑更成熟的持久化或云端向量存储方案。",
    },
    (3, "0231"): {
        "chapter": 7,
    },
    (1, "0236"): {
        "chapter": 3,
    },
    (1, "0237"): {
        "chapter": 3,
    },
    (3, "0241"): {
        "chapter": 3,
    },
    (3, "0242"): {
        "chapter": 7,
        "options": [
            {"option_label": "A", "option_text": "生成答案与问题的相关性"},
            {"option_label": "B", "option_text": "RAG 应用生成答案的准确度"},
            {"option_label": "C", "option_text": "生成答案是否忠实于检索上下文"},
            {"option_label": "D", "option_text": "相关参考资料被检索到的数量"},
        ],
        "analysis": "Answer Relevancy 用于评估生成答案是否直接、恰当地回应用户问题，关注的是答案与问题的匹配程度，而不是事实准确率或检索数量。",
    },
    (1, "0244"): {
        "chapter": 9,
    },
    (2, "0245"): {
        "chapter": 8,
    },
    (3, "0252"): {
        "chapter": 7,
        "options": [
            {"option_label": "A", "option_text": "相关参考资料被检索到的数量"},
            {"option_label": "B", "option_text": "RAG 应用生成答案的准确度"},
            {"option_label": "C", "option_text": "生成答案与问题的相关性"},
            {"option_label": "D", "option_text": "检索结果中相关条目是否排名靠前"},
        ],
        "analysis": "Context Recall 用于评估回答所需的相关参考资料是否被成功检索出来，核心是看需要的信息有没有被召回，而不是排序质量或答案相关性。",
    },
    (1, "0086"): {
        "chapter": 2,
        "stem": "在优化后的答疑机器人中，以下哪一项是提示词中规定的输入格式？",
    },
    (2, "0082"): {
        "stem": "在优化 answer correctness 指标时，优化 prompt 的以下哪项好处是正确的？",
    },
    (3, "0083"): {
        "stem": "在检索召回阶段，以下哪种方法会结合用户信息、行为等数据扩写问题？",
    },
    (3, "0087"): {
        "stem": "在检索召回阶段，以下哪种方法是通过向用户追问来获取更多信息？",
        "options": [
            {"option_label": "A", "option_text": "反向追问用户"},
            {"option_label": "B", "option_text": "问题改写"},
            {"option_label": "C", "option_text": "重排序"},
            {"option_label": "D", "option_text": "增加模型的训练数据"},
        ],
    },
    (3, "0091"): {
        "stem": "在示例中，以下哪项任务需要经过 RAG 链路来生成答案？",
    },
    (3, "0095"): {
        "stem": "在检索召回阶段，以下哪种方法会提取标签，用于后续标签过滤和向量相似度检索？",
    },
    (3, "0096"): {
        "stem": "在优化 context precision 指标时，rerank（重排序）的以下哪项好处是正确的？",
    },
    (3, "0100"): {
        "stem": "Ragas 提供的以下哪个指标用于评估生成答案与检索资料的事实一致性？",
    },
    (3, "0102"): {
        "stem": "在问题改写中，以下哪种方法会通过生成假想文档来增强检索效果？",
    },
    (3, "0105"): {
        "stem": "在切片向量化与存储阶段，embedding_models 字典的以下哪项作用是正确的？",
    },
    (1, "0143"): {
        "chapter": 3,
        "stem": "在优化检索效果时，以下哪种方法可以提升大模型对参考信息的查找效率？",
    },
    (1, "0155"): {
        "chapter": 3,
        "stem": "在优化检索效果时，以下哪种方法可以提升文档的结构性？",
    },
    (1, "0178"): {
        "chapter": 2,
        "stem": "在 ask_lm_route 函数中，以下哪一项是提示词中规定的输入格式？",
    },
    (1, "0202"): {
        "chapter": 2,
        "stem": "在意图识别中，使用提示词的以下哪项优点是正确的？",
    },
    (2, "0142"): {
        "stem": "在提示词框架中，以下哪一项要素最适合用于提供任务的背景信息？",
    },
    (2, "0221"): {
        "stem": "在示例中，COT 方法的以下哪项优点是正确的？",
    },
    (2, "0271"): {
        "stem": "在优化 answer correctness 指标时，调整大模型生成超参数（如 temperature）的以下哪项好处是正确的？",
    },
    (2, "0276"): {
        "stem": "在提示词框架中，以下哪一项要素可以用于明确模型的具体任务？",
        "options": [
            {"option_label": "A", "option_text": "任务目标（Object）"},
            {"option_label": "B", "option_text": "上下文（Context）"},
            {"option_label": "C", "option_text": "角色（Role）"},
            {"option_label": "D", "option_text": "受众（Audience）"},
        ],
    },
    (2, "1416"): {
        "stem": "在提示词框架中，以下哪一项要素可以用于直接提供任务的背景信息？",
    },
    (1, "0253"): {
        "chapter": 3,
        "stem": "在优化检索效果时，以下哪种方法可以提升大模型对参考信息的结构化理解？",
    },
    (1, "0188"): {
        "chapter": 7,
        "stem": "在 context recall 的计算过程中，以下哪一步用于核验召回内容是否覆盖 ground truth 观点？",
    },
    (1, "0290"): {
        "chapter": 7,
        "stem": "在 context recall 的计算过程中，首先需要完成哪一步准备？",
    },
    (1, "1362"): {
        "chapter": 7,
        "stem": "在 context recall 的计算过程中，以下哪一步用于判断观点能否在 contexts 中找到依据？",
    },
    (3, "0106"): {
        "stem": "在切片向量化与存储阶段，compare_embeddings 函数的主要用途是什么？",
    },
    (3, "1400"): {
        "stem": "在切片向量化与存储阶段，compare_embeddings 函数输出结果的含义是什么？",
    },
    (3, "0113"): {
        "stem": "在文档切片过程中，以下哪种切片方法更适合刚刚开始接触 RAG 的用户？",
    },
    (3, "0119"): {
        "stem": "在构建 RAG 应用时，以下哪一项是本地向量数据库的特点？",
    },
    (3, "0140"): {
        "stem": "在切片向量化与存储阶段，compare_embedding_models 函数的以下哪项作用是正确的？",
    },
    (3, "0158"): {
        "stem": "在文档切片过程中，以下哪种切片方法更适合处理 Markdown 文档？",
    },
    (3, "0162"): {
        "stem": "在切片向量化与存储阶段，以下哪个是较旧的 Embedding 模型？",
    },
    (3, "0164"): {
        "stem": "在优化检索效果时，以下哪种方法可以增加召回的文档切片数量？",
    },
    (3, "0191"): {
        "stem": "在切片向量化与存储阶段，cosine_similarity 函数的以下哪项作用是正确的？",
    },
    (3, "0214"): {
        "stem": "GraphRAG 技术结合了下列哪一组选项的优点？",
    },
    (3, "0217"): {
        "stem": "在问题改写中，以下哪种方法会通过分解复杂问题为多个子问题来解决问题？",
    },
    (3, "0246"): {
        "stem": "在优化检索效果时，调整 similarity_top_k 参数的以下哪项好处是正确的？",
    },
    (3, "0255"): {
        "stem": "在创建索引时，以下哪个方法被使用？",
    },
    (3, "0257"): {
        "stem": "在检索召回阶段，以下哪种方法会通过滑动窗口检索补充相邻切片？",
    },
    (3, "0261"): {
        "stem": "在检索召回阶段，以下哪种方法会通过重排序和过滤来减少无关信息？",
    },
    (3, "0263"): {
        "stem": "在 RAG 应用中，以下哪个组件可以用于存储向量化后的文本段？",
    },
    (3, "0269"): {
        "stem": "在 RAG 应用中，检索生成阶段包括以下哪一组步骤？",
    },
    (3, "0279"): {
        "stem": "在 RAG 应用中，建立索引阶段包括以下哪一组步骤？",
    },
    (3, "0291"): {
        "stem": "在检索召回阶段，以下哪种方法会通过思考并规划多次检索来解决问题？",
    },
    (3, "0292"): {
        "stem": "Ragas 提供的以下哪个指标用于评估生成答案与问题的相关性？",
    },
    (3, "1399"): {
        "stem": "在切片向量化与存储阶段，Compare_embedding_models 函数的以下哪项作用是正确的？",
    },
    (3, "1400"): {
        "stem": "在切片向量化与存储阶段，compare_embeddings 函数的以下哪项作用是正确的？",
    },
    (3, "0209"): {
        "stem": "在 RAG 应用的多轮对话中，以下哪个工具可以快速实现多轮对话？",
    },
    (5, "0197"): {
        "stem": "在意图识别中，对模型进行微调的以下哪项优点是正确的？",
    },
    (7, "0258"): {
        "stem": "在 context recall 的计算过程中，ground_truth 观点列表的生成依据主要是什么？",
    },
    (3, "0192"): {
        "answer": "A,B",
        "analysis": "内存向量存储通常更适合开发测试和小规模应用场景，优点是部署轻量、使用简单；而面向大规模或正式生产环境时，通常更需要具备持久化、扩展性和运维能力的向量数据库方案。",
    },
    (10, "0652"): {
        "answer": "B",
        "analysis": "`dashscope.Runs.wait()` 的主要作用是同步等待 run 完成或进入下一步可处理状态，因此最准确的表述是“阻塞当前线程，直到请求的响应准备好为止”。",
    },
    (10, "1301"): {
        "answer": "D",
        "analysis": "这类 Assistant API 示例里，`dashscope.Runs.wait()` 的核心职责是阻塞等待 run 执行结果；“等待所有辅助工具输出”更像完整流程效果，不是该调用本身最准确的单项定义。",
    },
    (10, "1426"): {
        "stem": "在下列 Assistant API 示例代码的 query 方法中，dashscope.Runs.wait 的以下哪些作用描述是正确的？ class APIAssistantAgent(AgentModule):def query(self,query:str):Message =dashscope.Messages.create(self.thread.id,content=query)message_run =dashscope.Runs.create(self.thread.id,assistant_id=self.assistant.id)Run_status =dashscope.Runs.wait(message_run.id,thread_id=self.thread.id,Callback=lambda progress:print(f\"Progress:{progress}%\"))if Run_status.required_action:self.forward_and_submit_outputs(run_status)Run_status =dashscope.Runs.wait(run_status.id,thread_id=self.thread.id)msgs =dashscope.Messages.list(self.thread.id)answer=json.loads(json.dumps(msgs,Default=lambda o:0. dict )['data'][0]['content'][O]['text']['value']return Answer",
    },
    (2, "1007"): {
        "stem": "如果你基于网页版的大模型写了以下提示词（请你生成一份季度财务报告），以下哪组建议最合理，可以帮助改进这个提示词？",
    },
    (9, "1388"): {
        "chapter": 10,
    },
    (1, "1468"): {
        "chapter": 5,
    },
    (3, "1468"): {
        "chapter": 4,
    },
    (7, "1468"): {
        "chapter": 2,
    },
    (3, "1467"): {
        "chapter": 2,
    },
    (7, "1467"): {
        "chapter": 3,
    },
    (1, "1460"): {
        "chapter": 2,
    },
    (7, "1460"): {
        "chapter": 2,
    },
    (7, "1466"): {
        "chapter": 3,
    },
    (1, "1466"): {
        "chapter": 12,
    },
    (7, "1461"): {
        "chapter": 12,
    },
    (1, "1461"): {
        "chapter": 3,
    },
    (2, "1441"): {
        "chapter": 11,
    },
    (6, "1362"): {
        "chapter": 9,
    },
    (9, "1382"): {
        "chapter": 6,
    },
    (11, "1415"): {
        "chapter": 10,
    },
    (12, "1286"): {
        "chapter": 4,
    },
    (12, "1290"): {
        "chapter": 2,
    },
    (6, "1363"): {
        "chapter": 10,
    },
    (7, "1462"): {
        "chapter": 7,
    },
    (4, "0575"): {
        "chapter": 10,
        "answer": "B",
        "analysis": "在这段 Assistant API 示例代码里，`dashscope.Runs.wait(...)` 的核心职责是阻塞当前线程，直到本次 run 的结果准备好或进入下一步可继续处理状态。题干并未展示实时进度回调，因此不应把“返回实时进度”算作本题正确项。",
    },
    (9, "1386"): {
        "chapter": 8,
    },
    (3, "0229"): {
        "chapter": 12,
    },
    (12, "1285"): {
        "chapter": 3,
    },
    (12, "1287"): {
        "chapter": 8,
    },
    (1, "1463"): {
        "chapter": 2,
    },
    (1, "0270"): {
        "options": [
            {"option_label": "A", "option_text": "用户：你好；助手：你好，有什么可以帮你的？"},
            {"option_label": "B", "option_text": "<<用户>> 你好 <<助手>> 你好，有什么可以帮你的？"},
            {"option_label": "C", "option_text": "### 用户：你好 ### 助手：你好，有什么可以帮你的？"},
            {"option_label": "D", "option_text": "<chat_history><user>你好</user><assistant>你好，有什么可以帮你的？</assistant></chat_history>"},
        ],
        "answer": "D",
        "analysis": "区分多轮对话或历史记录时，结构化标签最清晰、边界最稳定。像 `<chat_history>`、`<user>`、`<assistant>` 这类标签能帮助模型更准确地识别对话角色和历史范围。",
    },
    (3, "0242"): {
        "chapter": 7,
        "options": [
            {"option_label": "A", "option_text": "生成答案与问题的相关性"},
            {"option_label": "B", "option_text": "RAG 应用生成答案的准确度"},
            {"option_label": "C", "option_text": "生成答案是否忠于检索到的上下文"},
            {"option_label": "D", "option_text": "检索到的参考资料对问题关键事实的覆盖程度"},
        ],
        "answer": "A",
        "analysis": "Answer Relevancy 用于评估生成答案与用户问题之间的相关性，而不是准确度、忠实度或上下文覆盖程度。",
    },
    (3, "0252"): {
        "chapter": 7,
        "options": [
            {"option_label": "A", "option_text": "与问题相关的参考信息被召回的完整程度"},
            {"option_label": "B", "option_text": "RAG 应用生成答案的准确度"},
            {"option_label": "C", "option_text": "生成答案与问题的相关性"},
            {"option_label": "D", "option_text": "生成答案是否忠于检索到的上下文"},
        ],
        "answer": "A",
        "analysis": "Context Recall 用于衡量与问题相关的关键信息是否被检索阶段尽可能完整地召回。",
    },
    (3, "1306"): {
        "stem": "以下代码片段旨在模拟RAG应用的向量检索过程。哪一行代码实现了计算用户问题向量与文档向量相似度的功能?",
        "options": [
            {"option_label": "A", "option_text": "import numpy as np"},
            {"option_label": "B", "option_text": "query_embedding=np.array([0.1,0.2,0.02])"},
            {"option_label": "C", "option_text": "scores = cosine_similarity(query_embedding, doc_embeddings)"},
            {"option_label": "D", "option_text": "print(scores)"},
        ],
        "answer": "C",
        "analysis": "本题考察向量相似度计算。`scores = cosine_similarity(query_embedding, doc_embeddings)` 这行代码真正完成了查询向量与文档向量之间的相似度计算。",
    },
    (8, "1451"): {
        "options": [
            {"option_label": "A", "option_text": "视频上传后的用户评论分析"},
            {"option_label": "B", "option_text": "视频预处理，例如视频分段和帧提取"},
            {"option_label": "C", "option_text": "音频合规检测"},
            {"option_label": "D", "option_text": "视频编码格式的选择"},
            {"option_label": "E", "option_text": "图片合规检测"},
            {"option_label": "F", "option_text": "文本合规检测（包括字幕和音频转录文本）"},
        ],
        "answer": "B,C,E,F",
        "analysis": "视频合规检测通常包括视频预处理、音频合规检测、关键帧/图片合规检测，以及字幕和转录文本的文本合规检测。",
    },
    (10, "0447"): {
        "options": [
            {"option_label": "A", "option_text": "completion = client.chat.create(model=\"qwen-max\", messages=[{\"role\": \"user\", \"content\": \"你好\"}])"},
            {"option_label": "B", "option_text": "completion = client.chat.completions.create(model=\"qwen-max\", messages=[{\"role\": \"user\", \"content\": \"你好\"}])"},
            {"option_label": "C", "option_text": "completion = client.chat.create(model=\"qwen-max\", records=[{\"role\": \"user\", \"content\": \"你好\"}])"},
            {"option_label": "D", "option_text": "completion = client.chat.completions.create(model=\"qwen-max\", records=[{\"role\": \"user\", \"content\": \"你好\"}])"},
        ],
        "answer": "B",
        "analysis": "对话补全应使用 `client.chat.completions.create(...)`，并通过 `messages` 传递消息列表；`create` 或 `records` 写法都不符合这里的接口要求。",
    },
    (2, "0275"): {
        "options": [
            {"option_label": "A", "option_text": "[]"},
            {"option_label": "B", "option_text": "<context></context>"},
            {"option_label": "C", "option_text": "##"},
            {"option_label": "D", "option_text": "以上都可以"},
        ],
        "answer": "D",
        "analysis": "方括号、自定义标签和 `##` 都可以作为提示词中的分隔符。关键不在于具体符号，而在于边界清晰、含义稳定、前后一致。",
    },
    (2, "0523"): {
        "options": [
            {"option_label": "A", "option_text": "[]"},
            {"option_label": "B", "option_text": "<context></context>"},
            {"option_label": "C", "option_text": "##"},
        ],
        "answer": "A,B,C",
        "analysis": "提示词里的分隔符可以采用方括号、自定义 XML/HTML 风格标签、井号标题等形式。只要能稳定地区分不同内容块，都可以作为分隔符使用。",
    },
    (2, "1157"): {
        "options": [
            {"option_label": "A", "option_text": "XML 标签"},
            {"option_label": "B", "option_text": "<context></context>"},
            {"option_label": "C", "option_text": "一整段不加标记的自然语言"},
            {"option_label": "D", "option_text": "..."},
            {"option_label": "E", "option_text": "##"},
        ],
        "answer": "A,B,E",
        "analysis": "常见的提示词分隔方式包括 XML 风格标签、自定义结构化标签以及 `##` 这类显式分隔标记。纯自然语言长句缺少清晰边界，不适合作为稳定分隔符。",
    },
    (3, "0090"): {"chapter": 7},
    (3, "0100"): {
        "chapter": 7,
        "stem": "Ragas 提供的以下哪个指标用于评估生成答案与检索资料的事实一致性？",
    },
    (3, "0139"): {"chapter": 7},
    (3, "0165"): {"chapter": 7},
    (3, "0204"): {"chapter": 7},
    (3, "0218"): {"chapter": 7},
    (3, "0292"): {
        "chapter": 7,
        "stem": "Ragas 提供的以下哪个指标用于评估生成答案与问题的相关性？",
    },
    (3, "0413"): {"chapter": 7},
    (3, "0413"): {
        "chapter": 7,
        "stem": "在 Ragas 的 faithfulness、answer_relevancy、context_recall、context_precision 四项指标中，哪一个主要评估生成阶段的答案质量？",
    },
    (3, "0438"): {"chapter": 12},
    (3, "0438"): {
        "chapter": 12,
        "stem": "在借助 LlamaIndex 构建问答机器人时，如果存储目录不存在，首次创建索引应使用哪个类读取文档？",
    },
    (3, "0465"): {"chapter": 7},
    (3, "0472"): {"chapter": 7},
    (3, "0493"): {"chapter": 7},
    (3, "0500"): {"chapter": 12},
    (3, "0650"): {
        "chapter": 7,
        "stem": "在使用 Ragas 评估 RAG 应用时，answer_correctness 通常由哪些指标共同构成？",
    },
    (3, "1080"): {"chapter": 7},
    (3, "1158"): {"chapter": 7},
    (3, "1184"): {"chapter": 7},
    (3, "1205"): {"chapter": 12},
    (3, "1197"): {"chapter": 12},
    (3, "1294"): {"chapter": 7},
    (3, "1294"): {
        "chapter": 7,
        "stem": "在 Ragas 的常见指标中，哪一个不依赖检索覆盖而更关注生成答案本身的表现？",
    },
    (3, "1367"): {"chapter": 7},
    (3, "1368"): {"chapter": 7},
    (3, "1391"): {"chapter": 12},
    (3, "1391"): {
        "chapter": 12,
        "stem": "在借助 LlamaIndex 构建问答机器人时，若本地尚无存储索引，应使用哪个类先读取文档并创建索引？",
    },
    (3, "1414"): {"chapter": 7},
    (3, "0209"): {
        "chapter": 12,
        "stem": "在 RAG 应用的多轮对话中，以下哪个工具可以快速实现多轮对话？",
    },
    (3, "0255"): {
        "chapter": 12,
        "stem": "在创建索引时，以下哪个方法被使用？",
    },
    (11, "0649"): {"chapter": 8},
    (11, "1300"): {
        "chapter": 8,
        "stem": "下列哪些 AIGC 应用场景依法需要办理算法备案？",
    },
    (10, "0259"): {"chapter": 8},
    (12, "0458"): {"chapter": 10},
    (10, "1022"): {"chapter": 8},
    (10, "1033"): {"chapter": 8},
    (10, "1058"): {"chapter": 3},
    (10, "1461"): {"chapter": 8},
    (10, "1028"): {"chapter": 8},
    (1, "0545"): {"chapter": 9},
    (1, "0702"): {"chapter": 8},
    (1, "0710"): {"chapter": 2},
    (1, "0717"): {"chapter": 9},
    (1, "0749"): {"chapter": 2},
    (1, "0163"): {"chapter": 2},
    (1, "0484"): {"chapter": 2},
    (1, "1025"): {"chapter": 2},
    (1, "1242"): {"chapter": 3},
    (1, "1080"): {"chapter": 7},
    (1, "1099"): {"chapter": 6},
    (1, "1134"): {"chapter": 2},
    (1, "1362"): {"chapter": 7},
    (1, "0167"): {
        "chapter": 9,
        "stem": "max_tokens=512 的作用是什么？",
    },
    (1, "0080"): {
        "stem": "以下哪项任务需求最符合用于文本扩写和润色的提示词？",
    },
    (1, "0086"): {
        "stem": "该答疑机器人提示词中规定的输入格式是什么？",
    },
    (1, "0097"): {
        "stem": "extract_tags 函数的作用是什么？",
    },
    (1, "0107"): {
        "stem": "Dataset.from_dict(data_samples) 的主要作用是什么？",
    },
    (1, "0125"): {
        "stem": "response_format={\"type\": \"json_object\"} 的作用是什么？",
    },
    (1, "0151"): {
        "stem": "seed=42 的作用是什么？",
    },
    (1, "0172"): {
        "stem": "score.to_pandas() 的主要作用是什么？",
    },
    (1, "0178"): {
        "stem": "ask_lm_route 规定的输入格式是什么？",
    },
    (1, "0181"): {
        "stem": "data_samples 字典的主要作用是什么？",
    },
    (1, "0184"): {
        "stem": "为了避免知识信息干扰大模型推理，以下哪种方法更合适？",
    },
    (1, "0186"): {
        "stem": "evaluate 函数的主要作用是什么？",
    },
    (1, "0219"): {
        "stem": "为了节省答疑机器人的资源消耗，以下哪种方法更合适？",
    },
    (3, "0236"): {
        "stem": "为什么某些问题不需要每次都经过 RAG 链路？",
    },
    (3, "0237"): {
        "stem": "index.as_query_engine 方法的主要作用是什么？",
    },
    (9, "0244"): {
        "stem": "is_chat_model=True 的作用是什么？",
    },
    (1, "0268"): {
        "stem": "OpenAILike 类的主要作用是什么？",
    },
    (1, "0273"): {
        "stem": "completion.choices[0].message.content 的作用是什么？",
    },
    (1, "0280"): {
        "stem": "answer_correctness 指标的主要作用是什么？",
    },
    (1, "0294"): {
        "stem": "presence_penalty=0.6 的作用是什么？",
    },
    (1, "0300"): {
        "stem": "以下关于大模型、机器学习与知识库应用的描述中，错误的是？",
    },
    (1, "0403"): {
        "stem": "以下哪个用户查询语句不适合用于指导大语言模型生成简洁摘要？",
    },
    (1, "1312"): {
        "stem": "以下关于大模型、机器学习与知识库应用的描述中，不正确的是？",
    },
    (1, "1317"): {
        "stem": "以下哪个用户查询语句无法有效指导大语言模型完成摘要任务？",
    },
    (1, "1434"): {
        "chapter": 3,
        "stem": "在优化检索效果时，以下哪种方法可以提升大模型对参考信息的语义理解？",
    },
    (1, "1433"): {
        "chapter": 3,
        "stem": "在优化检索效果时，以下哪种方法可以提升大模型对参考信息的定位效率？",
    },
    (1, "0236"): {
        "chapter": 3,
        "stem": "为什么某些问题不需要每次都经过 RAG 链路？",
    },
    (1, "0237"): {
        "stem": "index.as_query_engine 方法的主要作用是什么？",
    },
    (1, "0244"): {
        "chapter": 9,
        "stem": "is_chat_model=True 的作用是什么？",
    },
    (1, "0497"): {
        "stem": "OpenAILike 类的参数有哪些？",
    },
    (2, "0114"): {
        "stem": "COT 方法如何帮助大模型计算总差旅费用？",
    },
    (2, "0127"): {
        "stem": "ask_llm_route 函数在“文档审查”场景下会使用哪个提示词？",
    },
    (2, "0141"): {
        "stem": "ask_llm_route 函数在“内容翻译”场景下会使用哪个提示词？",
    },
    (2, "0173"): {
        "stem": "system_message 的作用是什么？",
    },
    (2, "0207"): {
        "stem": "ask_lm_route 函数在“公司内部文档查询”场景下会使用哪个方法？",
    },
    (2, "0210"): {
        "stem": "ask_lm_route 函数在问题类型无法识别时会返回什么？",
    },
    (2, "0221"): {
        "stem": "以下哪项最能体现 COT 方法的优点？",
    },
    (2, "0469"): {
        "stem": "该提示词中规定了哪些输出要求？",
    },
    (2, "0479"): {
        "stem": "该答疑机器人提示词中规定了哪些任务要求？",
    },
    (1, "0484"): {
        "chapter": 2,
        "stem": "ask_llm_route 函数可能的输出有哪些？",
    },
    (2, "0486"): {
        "stem": "该答疑机器人的可能处理流程有哪些？",
    },
    (2, "0504"): {
        "stem": "该答疑机器人提示词中规定了哪些角色背景？",
    },
    (2, "0522"): {
        "stem": "该提示词中规定了哪些任务要求？",
    },
    (2, "0524"): {
        "stem": "ask_llm_route 函数对应提示词中规定了哪些角色背景？",
    },
    (2, "0541"): {
        "stem": "ask_llm_route 函数可能的处理流程有哪些？",
    },
    (2, "0546"): {
        "stem": "ask_llm_route 函数对应提示词中规定了哪些任务要求？",
    },
    (2, "1170"): {
        "stem": "abstract_generator 提示词模板包含哪些关键组成部分？",
    },
    (2, "0630"): {
        "stem": "在生成插图提示词时，哪些因素有助于提升提示词的可执行性？",
    },
    (2, "0634"): {
        "stem": "已知 prompt_template 已定义摘要要求，以下哪些措施可以进一步提高摘要生成质量？",
    },
    (2, "1305"): {
        "stem": "在摘要 prompt_template 已给定的前提下，哪些改进有助于提升生成质量？",
    },
    (2, "1407"): {
        "stem": "在生成插图提示词时，应该考虑哪些因素来确保提示词更准确可控？",
    },
    (2, "1437"): {
        "stem": "ask_llm_route 函数在问题类型无法识别时会返回什么？",
    },
    (3, "0084"): {
        "stem": "query_engine = index.as_query_engine(...) 的作用是什么？",
    },
    (3, "0091"): {
        "stem": "以下哪项任务需要经过 RAG 链路来生成答案？",
    },
    (3, "0132"): {
        "stem": "response = ask(\"张伟是哪个部门的\", query_engine=query_engine) 的作用是什么？",
    },
    (3, "0153"): {
        "stem": "答疑机器人没有理解用户意图的主要原因是什么？",
    },
    (3, "0170"): {
        "stem": "SimilarityPostprocessor(similarity_cutoff=0.2) 的作用是什么？",
    },
    (3, "0179"): {
        "stem": "similarity_top_k=5 的主要作用是什么？",
    },
    (3, "0198"): {
        "stem": "DashScopeRerank(top_n=3, model=\"gte-rerank\") 的作用是什么？",
    },
    (3, "0260"): {
        "stem": "以下哪种问题不需要经过 RAG 链路？",
    },
    (3, "0286"): {
        "stem": "display(evaluate_result(question, response, ground_truth)) 的作用是什么？",
    },
    (3, "0289"): {
        "stem": "similarity_top_k=20 的作用是什么？",
    },
    (3, "0422"): {
        "stem": "StorageContext 的作用是什么？",
    },
    (3, "0421"): {
        "stem": "以下哪种方法最适合批量解析 PDF 和 Word 文档中的文本，以便进行后续 RAG 处理？",
    },
    (3, "0451"): {
        "stem": "在构建大语言模型 RAG 应用过程中，向量数据库承担的核心职责是什么？",
    },
    (3, "0572"): {
        "stem": "在 RAG 应用的建立索引阶段，核心步骤通常包括哪些？",
    },
    (3, "0574"): {
        "stem": "在 RAG 应用中，从原始文档到索引构建通常包括哪些步骤？",
    },
    (3, "0489"): {
        "stem": "哪些操作有助于提高检索的准确性？",
    },
    (3, "0503"): {
        "stem": "以下哪些内容属于知识库召回结果？",
    },
    (3, "0507"): {
        "stem": "index.as_query_engine 方法的参数有哪些？",
    },
    (3, "0553"): {
        "stem": "重排序过程中的关键步骤有哪些？",
    },
    (3, "0570"): {
        "stem": "OpenAIEmbedding 类的参数有哪些？",
    },
    (3, "1374"): {
        "stem": "OpenAIEmbedding 类的主要作用是什么？",
    },
    (3, "1347"): {
        "stem": "以下哪种方式最适合统一抽取 PDF 和 Word 文档文本，用于后续的 RAG 处理？",
    },
    (3, "1385"): {
        "stem": "在 RAG 流程中，向量数据库的主要作用更偏向于哪一项？",
    },
    (2, "0038"): {"chapter": 3},
    (2, "0498"): {"chapter": 3},
    (2, "0077"): {
        "chapter": 7,
        "analysis": "这题本质上考察的是如何解读评测指标组合并定位问题来源：当 answer correctness 低、而 context recall 与 context precision 高时，更可能是生成阶段需要优化。虽然正确动作是优化 prompt，但题目核心仍属于模型评估结果解读。",
    },
    (2, "1034"): {
        "chapter": 7,
        "analysis": "这题虽然包含 prompt 翻译和 system prompt 调整，但核心仍是 RAGAS 中文评测适配，属于模型评估流程中的本地化与评测配置问题。",
    },
    (2, "1462"): {
        "chapter": 7,
        "analysis": "题目讨论的是 RAGAS 中文评测适配方案，核心语境是模型评估而不是通用提示工程，因此更适合归入模型评估。",
    },
    (8, "1188"): {"chapter": 9},
    (4, "1175"): {
        "chapter": 4,
        "analysis": "这段 APIAssistantAgent 代码体现的是智能体在工具调用阶段如何执行 function call 并回传工具结果。虽然底层调用了 DashScope API，但考点本质上是 Agent 的工具编排与执行流程。",
    },
    (4, "1438"): {
        "stem": "get_multi_agent_response 中异常处理模块有哪些作用？",
    },
    (5, "0009"): {"chapter": 8},
    (5, "0488"): {"chapter": 7},
    (5, "0538"): {"chapter": 7},
    (5, "0852"): {"chapter": 8},
    (5, "1124"): {"chapter": 6},
    (5, "0120"): {
        "stem": "以下哪种任务可以直接输入给大模型生成答案？",
    },
    (5, "0149"): {
        "stem": "以下哪种问题需要经过 RAG 链路？",
    },
    (5, "0417"): {
        "stem": "微调大语言模型的流程中，通常不包括以下哪一项？",
    },
    (5, "0427"): {
        "stem": "大语言模型微调时，通过调节哪个参数可以直接控制参数更新的步长？",
    },
    (5, "0436"): {
        "stem": "在设定训练参数时，哪个参数决定单次迭代中同时处理的样本数量，并影响显存占用？",
    },
    (5, "0299"): {
        "stem": "在确保计算资源与基础设施满足大规模微调需求时，以下哪项不属于关键硬件与系统指标？",
    },
    (5, "1402"): {
        "stem": "在大规模微调场景下，以下哪项不属于资源基础设施评估的核心指标？",
    },
    (5, "1216"): {
        "stem": "大语言模型微调时，哪个训练参数最直接决定模型学习新知识的速度？",
    },
    (5, "0639"): {
        "stem": "以下关于大语言模型预训练与微调关系的描述，哪些是正确的？",
    },
    (5, "0641"): {
        "stem": "大语言模型微调通常可能涉及哪些步骤？",
    },
    (5, "1215"): {
        "stem": "在一次典型的大语言模型微调流程中，可能涉及哪些步骤？",
    },
    (5, "1287"): {
        "stem": "微调大语言模型的核心步骤中，以下哪一项通常不属于标准流程？",
    },
    (5, "1307"): {
        "stem": "以下关于大语言模型预训练与微调分工关系的说法，哪些是正确的？",
    },
    (5, "1403"): {
        "stem": "在训练配置中，哪个参数会影响每轮同时处理的数据量，并进而影响收敛速度和内存使用？",
    },
    (5, "1192"): {
        "stem": "哪一段代码用于计算模型预测结果（前向传播）？",
    },
    (6, "1292"): {"chapter": 8},
    (3, "0571"): {
        "chapter": 3,
        "analysis": "更换 embedding 模型的直接收益在于提升文本语义表示能力和检索召回准确率，这属于 RAG 检索链路优化，而不是评测定义本身。",
    },
    (9, "0073"): {
        "stem": "temperature=0.1 的作用是什么？",
    },
    (9, "0212"): {
        "stem": "client.chat.completions.create 的作用是什么？",
    },
    (9, "0487"): {
        "stem": "哪些操作有助于生成更具确定性的文本？",
    },
    (9, "0519"): {
        "stem": "哪些参数可以影响生成文本的多样性？",
    },
    (9, "0530"): {
        "stem": "哪些操作有助于生成更具创造性的文本？",
    },
    (9, "1193"): {
        "stem": "temperature 参数设置为 0.6 的主要作用是什么？",
    },
    (9, "1388"): {
        "chapter": 10,
        "stem": "APIAssistantAgent 的 query 流程里，哪些步骤与大语言模型交互？def query(self, query:str):\"\"\"query: string, the query string to the assistant, e.g. Who is the Jack Chou?\"\"\"message = dashscope.Messages.create(self.thread_id, content=query)message_run = dashscope.Runs.create(self.thread_id, assistant_id=self.assistant_id)run_status = dashscope.Runs.wait(message_run.id, thread_id=self.thread_id)if run_status.required_action:self.forward_and_submit_outputs(run_status)run_status = dashscope.Runs.wait(run_status.id, thread_id=self.thread_id)msgs = dashscope.Messages.list(self.thread_id)answer=json.loads(json.dumps(msgs,default=lambdao:o.__dict__))[\"data\"][0][\"content\"][0][\"text\"][\"value\"]return answer",
    },
    (10, "0076"): {
        "stem": "model=\"qwen-plus\" 的作用是什么？",
    },
    (10, "0196"): {
        "stem": "model=\"qwen-turbo\" 的作用是什么？",
    },
    (10, "0447"): {
        "stem": "以下哪行 Python 代码能够正确调用百炼的 \"qwen-max\" 模型进行对话补全？",
        "options": [
            {"option_label": "A", "option_text": "completion = client.chat.create(model=\"qwen-max\", messages=[{\"role\": \"user\", \"content\": \"你好\"}])"},
            {"option_label": "B", "option_text": "completion = client.chat.completions.create(model=\"qwen-max\", messages=[{\"role\": \"user\", \"content\": \"你好\"}])"},
            {"option_label": "C", "option_text": "completion = client.chat.create(model=\"qwen-max\", records=[{\"role\": \"user\", \"content\": \"你好\"}])"},
            {"option_label": "D", "option_text": "completion = client.chat.completions.create(model=\"qwen-max\", records=[{\"role\": \"user\", \"content\": \"你好\"}])"},
        ],
        "answer": "B",
    },
    (10, "1344"): {
        "stem": "以下哪种写法能够正确调用百炼 \"qwen-max\" 模型完成对话补全？",
    },
    (10, "0259"): {
        "chapter": 8,
        "stem": "api_key=os.getenv(\"DASHSCOPE_API_KEY\") 的作用是什么？",
    },
    (10, "1199"): {
        "stem": "APIAssistantAgent 的 query 函数里，哪些步骤与大语言模型交互？\ndef query(self, query: str):\n    \"\"\"\n    query: string, the query string to the assistant, e.g. Who is the Jack Chou?\n    \"\"\"\n    message = dashscope.Messages.create(self.thread_id, content=query)\n    message_run = dashscope.Runs.create(\n        self.thread_id,\n        assistant_id=self.assistant_id\n    )\n    run_status = dashscope.Runs.wait(message_run.id, thread_id=self.thread_id)    \n    if run_status.required_action:\n        self.forward_and_submit_outputs(run_status)\n        run_status = dashscope.Runs.wait(run_status.id, thread_id=self.thread_id)\n    msgs = dashscope.Messages.list(self.thread_id)\n    answer = json.loads(\n        json.dumps(msgs, default=lambda o: o.__dict__)\n    )[\"data\"][0][\"content\"][0][\"text\"][\"value\"]\n    return answer",
    },
    (8, "0625"): {
        "stem": "在大模型的内容安全治理中，哪些机制可用于阻断非法或不当生成？",
    },
    (8, "1372"): {
        "stem": "在大模型的内容安全治理中，哪些措施可用于降低违规输出风险？",
    },
    (9, "1031"): {
        "stem": "Assistant API 的 Assistant 类通常涵盖以下哪些能力？",
    },
    (9, "1163"): {
        "stem": "Assistant API 中 Assistant 类的功能范围通常包含以下哪些操作？",
    },
    (11, "0464"): {
        "stem": "在使用大模型提炼图文课程内容时，以下哪些内容组织原则是正确的？",
    },
    (11, "0637"): {
        "stem": "关于智能体应用中的图片合规检查技术，下列说法正确的有哪些？",
    },
    (11, "0643"): {
        "stem": "在使用 CosyVoice 进行语音合成时，哪些做法有助于保证音频质量和自然度？",
    },
    (11, "1246"): {
        "stem": "关于智能体场景下图片合规检测的技术手段，下列说法正确的有哪些？",
    },
    (11, "1410"): {
        "stem": "在使用大模型提炼图文课程内容时，以下哪些表达策略是正确的？",
    },
    (11, "1413"): {
        "stem": "在使用 CosyVoice 合成语音时，哪些方式有助于提升最终音频的自然度与质量？",
    },
    (3, "0090"): {
        "chapter": 7,
        "stem": "在 Ragas 中，context recall 指标主要衡量什么？",
    },
    (3, "0218"): {
        "chapter": 7,
        "stem": "在 Ragas 中，context recall 指标主要反映哪方面能力？",
    },
    (1, "0155"): {
        "chapter": 3,
        "stem": "在优化检索效果时，哪种方法有助于提升文档的结构化程度？",
    },
    (1, "0183"): {
        "chapter": 3,
        "stem": "在优化检索效果时，哪种方法可以增强文档的结构组织性？",
    },
    (3, "0164"): {
        "stem": "在优化检索效果时，哪种方法可以增加检索召回的文档切片数量？",
    },
    (3, "1435"): {
        "stem": "在优化检索效果时，哪种方法可以扩大召回的文档切片范围？",
    },
    (5, "0298"): {
        "stem": "关于技术团队在大模型微调项目中的职责，下列哪一项描述不够准确？",
    },
    (5, "1241"): {
        "stem": "关于技术团队在大模型微调落地中的作用，下列哪一项描述不够准确？",
    },
    (4, "0364"): {
        "stem": "在一个多 Agent 搜救场景中，若要最大化搜索效率，以下哪种共享信息策略最不合理？",
    },
    (4, "1224"): {
        "stem": "在多 Agent 搜救协作场景中，若目标是最大化搜索效率，以下哪种策略最不合理？",
    },
    (3, "0407"): {
        "stem": "以下哪个 RAG 应用场景最适合使用规则匹配的文本合规检测？",
    },
    (3, "1318"): {
        "stem": "在 RAG 场景中，以下哪种应用最适合采用规则匹配式文本合规检测？",
    },
    (1, "0411"): {
        "stem": "在使用大语言模型进行文档审阅时，不建议一次输出全部结果，最可能的原因是什么？",
    },
    (1, "1417"): {
        "stem": "在通过大语言模型做文档审阅时，不建议一次返回所有结果，最可能的原因是什么？",
    },
    (3, "0414"): {
        "stem": "以下代码片段用于模拟 RAG 向量检索，其中哪一行负责计算问题向量与文档向量的相似度？",
    },
    (3, "1306"): {
        "stem": "在这段 RAG 向量检索示例代码中，哪一行执行了用户问题向量与文档向量的相似度计算？",
        "options": [
            {"option_label": "A", "option_text": "import numpy as np"},
            {"option_label": "B", "option_text": "query_embedding=np.array([0.1,0.2,0.02])"},
            {"option_label": "C", "option_text": "scores = cosine_similarity(query_embedding, doc_embeddings)"},
            {"option_label": "D", "option_text": "print(scores)"},
        ],
        "answer": "C",
        "analysis": "本题考察向量相似度计算。`scores = cosine_similarity(query_embedding, doc_embeddings)` 这行代码真正完成了查询向量与文档向量之间的相似度计算。",
    },
    (3, "0416"): {
        "stem": "在大语言模型 RAG 应用的基本流程中，以下哪一项可以提高检索效率？",
    },
    (3, "1373"): {
        "stem": "在 RAG 应用的基本工作流程中，以下哪一项更有助于提升检索效率？",
    },
    (3, "0420"): {
        "stem": "在构建 RAG 应用时，以下关于句子滑窗检索优势的描述，正确的是哪一项？",
    },
    (3, "1386"): {
        "chapter": 3,
        "stem": "在构建 RAG 应用时，以下关于句子滑窗检索优势的说法，正确的是哪一项？",
    },
    (4, "0445"): {
        "stem": "以下哪一项不属于通过多智能体进行文档质量检测的优势？",
    },
    (4, "1313"): {
        "stem": "以下哪一项不属于多智能体协同进行文档质量检测的优势？",
    },
    (2, "0603"): {
        "stem": "在设计 LLM 思维链提示（CoT）时，以下哪些因素有助于提升效果？",
    },
    (2, "1405"): {
        "stem": "在设计思维链提示（Chain-of-Thought, CoT）时，以下哪些关键因素有助于提升效果？",
    },
}


def normalize_chapter(value):
    """将章节编号统一为 int，异常时返回 None"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_answer_labels(answer):
    """将答案统一为标签数组，如 A/C/D"""
    ans = str(answer or "").replace(" ", "")
    if "," in ans:
        return [part for part in ans.split(",") if part]
    return [ch for ch in ans if re.match(r"[A-G]", ch)]


def question_key(q):
    """返回 (chapter, seq) 形式的题目主键"""
    return normalize_chapter(q.get("chapter")), str(q.get("seq", "")).zfill(4)


def normalize_text(text):
    """清洗题目文本，修复过度转义并统一换行"""
    if not isinstance(text, str):
        return text

    normalized = text
    for _ in range(3):
        decoded = html.unescape(normalized)
        if decoded == normalized:
            break
        normalized = decoded

    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def normalize_answer(answer):
    """统一答案格式，单选为 A，多选为 A,B,C"""
    raw = normalize_text(str(answer or "")).upper()
    raw = raw.replace("，", ",").replace("、", ",").replace("；", ",").replace(" ", "")
    labels = [ch for ch in raw if re.match(r"[A-G]", ch)]

    if not labels:
        return raw
    if len(labels) == 1:
        return labels[0]
    return ",".join(labels)


def apply_manual_fixes(q):
    """应用人工确认的题目修正，并做基础字段规范化"""
    fixed = dict(q)
    fixed["seq"] = str(fixed.get("seq", "")).zfill(4)
    fixed["options"] = [dict(opt) for opt in fixed.get("options", [])]

    ch = normalize_chapter(fixed.get("chapter"))
    if ch is not None:
        fixed["chapter"] = ch

    manual_fix = MANUAL_FIXES.get(question_key(fixed))
    if manual_fix:
        fixed.update(manual_fix)

    fixed["stem"] = normalize_text(fixed.get("stem", ""))
    fixed["analysis"] = normalize_text(fixed.get("analysis", ""))
    fixed["answer"] = normalize_answer(fixed.get("answer", ""))
    fixed["options"] = [
        {
            "option_label": normalize_text(opt.get("option_label", "")).upper(),
            "option_text": normalize_text(opt.get("option_text", "")),
        }
        for opt in fixed.get("options", [])
    ]

    return fixed


def estimate_difficulty(q, ch):
    """估算题目难度，返回 (difficulty_score, difficulty_label, difficulty_sort)"""
    stem = str(q.get("stem", ""))
    analysis = str(q.get("analysis", ""))
    option_texts = [str(opt.get("option_text", "")) for opt in q.get("options", [])]
    text = " ".join([stem, analysis, *option_texts])

    score = 1
    answer_labels = normalize_answer_labels(q.get("answer", ""))
    option_count = len(q.get("options", []))

    if q.get("type") in (1, 2) or len(answer_labels) > 1:
        score += 2
    if option_count >= 5:
        score += 1
    if len(stem) >= 38:
        score += 1
    if len(stem) >= 75:
        score += 1
    if any(hint in stem for hint in NEGATION_HINTS):
        score += 2
    if any(hint.lower() in text.lower() for hint in CODE_HINTS):
        score += 2

    english_terms = re.findall(r"[A-Za-z_]{4,}", text)
    if len(english_terms) >= 6:
        score += 1

    if any(hint in stem for hint in EASY_HINTS):
        score -= 1

    score = max(1, min(score, 8))

    if score <= 2:
        label = "入门"
    elif score <= 5:
        label = "进阶"
    else:
        label = "挑战"

    difficulty_sort = CHAPTER_BASE_SORT.get(ch, 999) + score
    return score, label, difficulty_sort
def keyword_count(text: str, keyword: str) -> int:
    """统计关键词命中次数，英文词按边界匹配，避免误伤如 Token/tokenize。"""
    if re.search(r"[A-Za-z0-9_]", keyword) and not re.search(r"[\u4e00-\u9fff]", keyword):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(keyword)}(?![A-Za-z0-9_])"
        return len(re.findall(pattern, text, flags=re.IGNORECASE))
    return text.lower().count(keyword.lower())


def classify_question(q):
    """对单道题进行分类，返回最匹配的章节编号"""
    text = q["stem"] + " " + q.get("analysis", "")
    # 合并选项文本
    for opt in q.get("options", []):
        text += " " + opt["option_text"]

    scores = {ch: 0 for ch in CHAPTERS}

    for ch, rule in RULES.items():
        for keyword, weight in rule["keywords"]:
            count = keyword_count(text, keyword)
            if count > 0:
                scores[ch] += weight * count

    # 如果所有分数都为 0，根据 analysis 中的关键词尝试
    if all(v == 0 for v in scores.values()):
        analysis = q.get("analysis", "")
        for kw, ch in ANALYSIS_RULES.items():
            if kw.lower() in analysis.lower():
                scores[ch] += 1

    # 仍然为 0 的，标记为"综合/其他"
    best_ch = max(scores, key=scores.get)
    if scores[best_ch] == 0:
        # 回退策略：根据题目内容做最基础的判断
        stem = q["stem"]
        if "RAG" in stem or "检索" in stem or "文档" in stem:
            best_ch = 3
        elif "Agent" in stem or "智能体" in stem:
            best_ch = 4
        elif "微调" in stem or "训练" in stem:
            best_ch = 5
        elif "安全" in stem or "合规" in stem:
            best_ch = 8
        elif "API" in stem or "调用" in stem:
            best_ch = 9
        elif "模型" in stem:
            best_ch = 1

    return best_ch


def main():
    PROCESSED_JSON_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUILD_JS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with RAW_DATA_FILE.open("r", encoding="utf-8") as f:
        questions = [apply_manual_fixes(q) for q in json.load(f)]

    print(f"总计 {len(questions)} 道题，开始分类并评估难度...\n")

    categorized = {ch: [] for ch in CHAPTERS}
    difficulty_counts = {"入门": 0, "进阶": 0, "挑战": 0}

    for q in questions:
        ch = normalize_chapter(q.get("chapter"))
        if ch not in CHAPTERS:
            ch = classify_question(q)
        q["chapter"] = ch
        difficulty_score, difficulty_label, difficulty_sort = estimate_difficulty(q, ch)
        q["difficulty_score"] = difficulty_score
        q["difficulty_label"] = difficulty_label
        q["difficulty_sort"] = difficulty_sort
        difficulty_counts[difficulty_label] += 1
        categorized[ch].append(q)

    for ch in categorized:
        categorized[ch].sort(
            key=lambda item: (
                item.get("difficulty_sort", 999),
                item.get("difficulty_score", 99),
                str(item.get("seq", "")),
            )
        )

    # 输出统计
    print("=" * 60)
    print(f"{'章节':<25} {'题数':>6} {'占比':>8}")
    print("=" * 60)
    for ch in sorted(CHAPTERS):
        count = len(categorized[ch])
        pct = count / len(questions) * 100
        print(f"{CHAPTERS[ch]:<25} {count:>6} {pct:>7.1f}%")
    print("=" * 60)
    print(f"{'合计':<25} {len(questions):>6} {100:>7.1f}%")

    print("\n难度分布：")
    print(f"  入门: {difficulty_counts['入门']}")
    print(f"  进阶: {difficulty_counts['进阶']}")
    print(f"  挑战: {difficulty_counts['挑战']}")

    # 保存分类后的数据
    output = {
        "chapters": CHAPTERS,
        "total": len(questions),
        "difficulty_counts": difficulty_counts,
        "questions_by_chapter": {str(ch): categorized[ch] for ch in sorted(CHAPTERS)},
    }

    with PROCESSED_JSON_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n分类结果已保存到 {PROCESSED_JSON_FILE.relative_to(PROJECT_ROOT)}")

    # 同时生成一个 JS 版本供 HTML 使用
    js_data = "const QUIZ_CHAPTERS = " + json.dumps(CHAPTERS, ensure_ascii=False) + ";\n"
    js_data += "const QUIZ_DATA_BY_CHAPTER = " + json.dumps(
        {str(ch): categorized[ch] for ch in sorted(CHAPTERS)},
        ensure_ascii=False
    ) + ";"

    with BUILD_JS_FILE.open("w", encoding="utf-8") as f:
        f.write(js_data)

    print(f"JS 数据已保存到 {BUILD_JS_FILE.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
