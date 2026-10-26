# -*- coding: utf-8 -*-
"""重构批次 A：删除虚构/乱码/重复簇落选题 + 修正 + 新增替换题。

逐簇裁决依据见 data/curate/rebuild/conflict_dump.txt 审查记录。
所有操作走 curate_core 台账，固定 batch_id 保证幂等。
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import curate_core as cc

BANK = cc.load_bank()

# ---------- 1. 删除清单 ----------
DELETES = []

# 1a. 虚构 API 题（ask_llm_route/abstract_generator 等在官方教程中不存在，解析伪造出处）
for qid in ["2-0163", "2-0127", "2-0141", "2-0207", "2-0210", "2-0484",
            "2-0524", "2-0546", "2-1437", "2-1170", "2-0541"]:
    DELETES.append({"qid": qid, "reason": "虚构百炼API(ask_llm_route/abstract_generator等)，官方教程无此函数，解析伪造出处"})

# 1b. 图片依赖题
DELETES.append({"qid": "5-0008", "reason": "题干依赖内嵌base64图片，无法独立作答"})

# 1c. 冲突簇裁决落选/缺陷题（逐簇技术裁决，理由见注释）
CONFLICT_DEL = {
    "1-0280": "answer_correctness题：干扰项荒谬且缺解析，由新题7-6001替代",
    "7-1367": "answer_correctness题：答案C『评估RAG系统整体综合指标』技术错误，由新题7-6001替代",
    "1-1436": "分词题：与1-0392同答案，解析更薄",
    "1-0441": "LLM非最佳任务题：与1-1044同答案，缺解析",
    "9-1389": "top_p题：type多选但仅1答案，结构异常；1-0446保留并补解析",
    "1-0400": "try-except题：与1-1349同答案，解析更薄",
    "1-0300": "大模型数据量题：与1-1312同答案，缺解析",
    "1-0453": "system角色代码题：选项代码语法错误(list非dict)，由新题1-6001替代",
    "1-1182": "system角色代码题：代码粘连'python'前缀，由新题1-6001替代",
    "2-0079": "提示词约束题：干扰项荒谬且缺解析；2-0505保留并修正解析",
    "2-0523": "分隔符多选题：仅3选项结构异常；2-0275保留",
    "2-1111": "提示注入防范题：与2-1005同答案，选项措辞含混('避免泄露公开信息')；2-1005保留并补解析",
    "2-1024": "大模型局限题：与2-0628答案集等价(字母序不同)，2-0628解析更完整",
    "2-1450": "输出格式要素题：与2-0864同答案集，解析更薄",
    "4-1395": "上下文压力反向题：解析称D(重启清空)有效，与4-0344答案AB矛盾；保留4-0344",
    "4-1261": "多路径策略题：与4-0302同答案，题干有'投 资'粘连",
    "4-5192": "报销Agent超时题：与4-5175同场景换皮(仅选项字母序不同)",
    "5-1155": "损失下降题：题干粘连'选项：'，与5-0049同答案",
    "5-0293": "LoRA错误项题：'LoR'拼写错误+缺解析；5-1309保留",
    "5-1238": "微调挑战题：选项F残留'(争议点:)'文本；5-0647保留",
    "6-5160": "AWQ量化题：与6-5136同场景换皮，6-5136多选覆盖更全",
    "6-5146": "PagedAttention禁用题：'--disable-visual-batch'参数与报错信息均虚构",
    "6-5164": "PagedAttention禁用题：同上虚构场景",
    "6-5147": "显存节省单选题：解析称'消除碎片非来源'与教材6.5三好处矛盾；6-5162保留",
    "7-0150": "context precision题：干扰项荒谬且缺解析",
    "7-0538": "context precision题：选项C'除以相关的context个数'算法描述错误",
    "7-1362": "context recall单选题：与7-0488同答案，7-0488多选更全",
    "10-1426": "Runs.wait题：代码严重乱粘连(Default=lambda o:0. dict)，不可修复",
    "10-1199": "query交互步骤题：答案含C(Messages.create不触发推理)，歧义",
    "10-5203": "金融合规组合题：与10-5162同答案换皮",
    "10-5163": "DSW验证单选题：与10-5189正反同考，10-5189多选更全",
    "10-5167": "医疗HIPAA单选题：与10-5180同题干换皮",
    "10-5174": "账单成本单选题：与10-5181同题干，10-5181答案集更完整(含max_tokens)",
    "10-5215": "开源价值单选题：与10-5178同题干换皮",
    "11-5170": "图片审核单选题：与11-5208同知识点，11-5208多选更全",
    "12-0425": "LlamaIndex顺序题：'LamalIndex'拼写错误+缺解析；12-1284保留",
    "12-1179": "set_default_model题：代码乱粘连，由新题12-6001替代",
    "12-1205": "set_default_model题：代码乱粘连('TEX_EMBEDDING'/'Settings.ilm')，由新题12-6001替代",
    "12-5075": "NodeParser题：选项D'去重过滤合并'属NodePostprocessor职责，技术错误；12-5065保留",
}
for qid, reason in CONFLICT_DEL.items():
    DELETES.append({"qid": qid, "reason": f"重复簇裁决：{reason}"})

# 1d. 同答案重复簇落选题（每簇保留题干/解析更完整者；簇23/41/42为脚本误判保留双题）
PLAIN_DEL = [
    "1-0448", "1-0849", "1-0761", "1-0867", "1-1185", "1-0698", "1-0738", "1-0792",
    "1-1196", "5-0859", "1-1200", "2-0725", "2-0732", "2-0699", "2-0883", "2-1442",
    "2-0885", "2-1446", "2-1030", "2-1447", "5-0689", "9-0854", "5-0889",
    "5-0695", "5-1454", "5-0887", "5-1037", "6-0879", "6-0880", "6-0770", "6-5163",
    "8-1266", "8-0694", "8-1038", "8-0629", "8-1450", "9-1384", "9-1362", "9-0717",
    "9-0760", "10-0412", "11-0764", "12-1466", "12-1197", "2-1448",
]
for qid in PLAIN_DEL:
    DELETES.append({"qid": qid, "reason": "同答案重复簇：保留同义更完整/解析更佳的一题"})

# 去重（部分题可能同时出现在多个清单）
seen = set()
uniq_del = []
for e in DELETES:
    if e["qid"] in seen:
        continue
    seen.add(e["qid"])
    uniq_del.append(e)
print(f"删除清单: {len(uniq_del)} 题")

# ---------- 2. 执行软删除（批次A） ----------
BID = "rebuild20261027_A_delete"
if not cc.batch_exists(BID):
    res = cc.soft_delete(BANK, uniq_del, source="题库重构批次A：虚构/乱码/重复裁决", batch_id=BID)
    cc.append_batch("soft_delete", "rebuild_batch_A.py", res["ledger_items"],
                    reason=f"重构批次A软删除 {res['applied']} 题", batch_id=BID)
    cc.write_bank(BANK)
    print(f"软删除 applied={res['applied']} skipped={len(res['skipped'])}")
    for s in res["skipped"][:10]:
        print("  skip:", s)
else:
    print("批次A已执行（幂等跳过）")

# ---------- 3. 修正（批次B） ----------
BANK = cc.load_bank()
FIXES = [
    {"qid": "2-0505", "final": ["A", "B", "C"],
     "analysis": "A『根据上下文而非先验知识回答』是 RAG 提示词的经典约束；B『触及安全红线时明确拒答』是安全类硬性约束；C『只回答用户问题、不输出多余信息』是输出范围约束。三者都写在提示词里、作用于推理阶段。D 错误：提示词模板只影响推理行为，无法增加训练数据，混淆了推理控制与模型训练两个层级。",
     "reason": "解析删除无法核验的伪出处（《大模型内容安全规范》/response_format 牵强引用），改为机制解释",
     "manual_reason": "人工裁决：原解析引用不存在的规范文件"},
    {"qid": "10-0575", "final": ["B"],
     "analysis": "dashscope.Runs.wait 是同步阻塞调用：轮询 Run 状态直到 completed 或 requires_action 才返回，即阻塞当前线程直到响应就绪。示例代码未传进度回调参数，故『返回实时进度』不成立；A 错在 wait 是同步而非异步；C/E 夸大了 wait 的职责（工具输出与消息持久化由其他接口负责）。",
     "reason": "type 多选但仅 1 个可辩护答案，改为单选",
     "manual_reason": "人工裁决：结构异常题（multi_but_single_answer）"},
    {"qid": "7-0488", "final": ["A", "B"],
     "analysis": "RAGAS 的 Context Recall 计算：先由 LLM 将 ground_truth 分解为若干观点（claims），再逐条判断每个观点能否在检索到的 contexts 中找到依据，最终得分 = 可归因观点数 / 观点总数。C、D 与评估计算无关。",
     "reason": "补写解析（原为『暂无』）",
     "manual_reason": "人工核验：RAGAS context_recall 算法（官方教程 2_5/7_4）"},
    {"qid": "1-0446", "final": ["B"],
     "analysis": "top_p（核采样）设定累积概率阈值：如 0.9 表示只从累积概率前 90% 的候选词中采样，截断长尾低概率词。它不控制生成长度、CPU 核数或输出格式。",
     "reason": "补写解析（原为『暂无』）",
     "manual_reason": "人工核验：nucleus sampling 定义"},
]
BID2 = "rebuild20261027_B_fix"
if not cc.batch_exists(BID2):
    res = cc.apply_answer_fix(BANK, FIXES, source="题库重构批次B：答案/解析修正", batch_id=BID2)
    cc.append_batch("answer_fix", "rebuild_batch_A.py", res["ledger_items"],
                    reason=f"重构批次B修正 {res['applied']} 题", batch_id=BID2)
    cc.write_bank(BANK)
    print(f"修正 applied={res['applied']} skipped={len(res['skipped'])}")
    for s in res["skipped"][:10]:
        print("  skip:", s)
    # 10-0575 的 type 修正单独落库（apply_answer_fix 不改 type）
    idx = cc.build_index(BANK)
    ch, q = idx["10-0575"]
    if q.get("type") == 1:
        q["type"] = 0
        q["revised_at"] = cc.datetime.now().isoformat(timespec="seconds")
        cc.write_bank(BANK)
        print("10-0575 type 1->0")
else:
    print("批次B已执行（幂等跳过）")

# ---------- 4. 新增替换题（批次C） ----------
BANK = cc.load_bank()
NEW_Q = [
    {"seq": "6001", "type": 0,
     "stem": "在 RAGAS 的常用评测指标中，Answer Correctness 衡量的是什么？",
     "options": [
         {"option_label": "A", "option_text": "生成答案与参考答案（ground truth）的一致程度，综合语义相似度与事实一致性"},
         {"option_label": "B", "option_text": "检索到的上下文与用户问题的相关程度"},
         {"option_label": "C", "option_text": "回答是否严格基于检索上下文、没有凭空编造"},
         {"option_label": "D", "option_text": "回答与用户问题的切题程度"},
     ],
     "answer": "A",
     "analysis": "Answer Correctness 使用 question/answer/ground_truth 三个字段，评估生成答案与标准答案的整体一致程度，实现上是语义相似度与事实 F1 的加权组合。B 对应 Context Precision/Recall；C 对应 Faithfulness；D 对应 Answer Relevancy。",
     "chapter": 7, "difficulty_score": 1, "difficulty_label": "入门", "difficulty_sort": 1,
     "governance": {"origin": "自编重构题", "source_note": "官方教程 C2_2_5/C7_4 RAGAS 指标定义；替代原 1-0280/7-1367"}},
    {"seq": "6001", "type": 0,
     "stem": "在 LlamaIndex 应用中，开发者在启动时调用一个函数，将全局 Settings 的 llm 和 embed_model 分别配置为 DashScope 的 qwen-plus 与文本向量模型。这样做的主要效果是？",
     "options": [
         {"option_label": "A", "option_text": "使 LLM 支持流式输出"},
         {"option_label": "B", "option_text": "后续切片、建索引、检索等步骤无需再逐个指定 llm 和 embed_model"},
         {"option_label": "C", "option_text": "使向量模型直接参与答案的生成过程"},
         {"option_label": "D", "option_text": "降低向量维度以加快检索速度"},
     ],
     "answer": "B",
     "analysis": "LlamaIndex 的 Settings 是全局配置入口，设置默认组件后，NodeParser、VectorStoreIndex、QueryEngine 等后续环节自动复用，无需逐处传参。A 由调用参数（stream）控制；C 混淆了向量模型（检索阶段）与生成模型（生成阶段）的职责；D 与 Settings 配置无关。",
     "chapter": 12, "difficulty_score": 2, "difficulty_label": "进阶", "difficulty_sort": 2,
     "governance": {"origin": "自编重构题", "source_note": "官方教程 LlamaIndex Settings 用法；替代原乱码题 12-1179/12-1205"}},
    {"seq": "6002", "type": 0,
     "stem": "调用大模型 API 时，需要用 system 角色消息指示模型扮演一位友好的客服代表。以下哪个 messages 片段写法正确？",
     "options": [
         {"option_label": "A", "option_text": "messages = [{\"role\": \"system\", \"content\": \"你是一位友好的客服代表，随时准备帮助客户解决问题。\"}]"},
         {"option_label": "B", "option_text": "messages = [{\"role\": \"assistant\", \"content\": \"您好，请问有什么可以帮您的？\"}]"},
         {"option_label": "C", "option_text": "messages = [{\"role\": \"user\", \"content\": \"我想咨询一下退货流程。\"}]"},
         {"option_label": "D", "option_text": "messages = [{\"role\": \"system\", \"content\": \"用户想咨询退货流程。\"}]"},
     ],
     "answer": "A",
     "analysis": "system 角色用于预设模型的身份与行为规范，A 的 role 与 content 均符合要求。B 用了 assistant 角色（模型的历史回复位置）；C 是 user 角色的正常提问；D 虽然 role 正确，但 content 是对用户意图的转述，不是对模型行为的指示。",
     "chapter": 1, "difficulty_score": 2, "difficulty_label": "进阶", "difficulty_sort": 2,
     "governance": {"origin": "自编重构题", "source_note": "OpenAI/DashScope 兼容接口 messages 规范；替代原缺陷题 1-0453/1-1182"}},
]
BID3 = "rebuild20261027_C_add"
if not cc.batch_exists(BID3):
    by_ch = BANK["questions_by_chapter"]
    items = []
    for q in NEW_Q:
        ch = str(q["chapter"])
        qid = f"{ch}-{q['seq']}"
        idx = cc.build_index(BANK)
        if qid in idx:
            print(f"[跳过] {qid} 已存在")
            continue
        by_ch.setdefault(ch, []).append(q)
        items.append({"qid": qid, "before": None, "after": q, "reason": "重构新增替代题"})
    BANK["total"] = sum(len(v) for v in by_ch.values())
    cc.append_batch("add_questions", "rebuild_batch_A.py", items,
                    reason=f"重构批次C新增 {len(items)} 题", batch_id=BID3)
    cc.write_bank(BANK)
    print(f"新增 {len(items)} 题")
else:
    print("批次C已执行（幂等跳过）")

print("批次A/B/C 完成")
