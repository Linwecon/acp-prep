# -*- coding: utf-8 -*-
"""批次D-1：结构规范化。
1) type=2 -> 1（旧多选标记）
2) 多选但仅1答案且题干为单选措辞 -> type=0（1-0521/2-1166 同步改题干）
3) 题干残留"（多选，N 个选项）" -> "（多选）"
4) 代码粘连题干/选项重排为换行格式
5) 补写/修正解析（6-1190、1-0521、4-1286、12-1288 等）
6) 删除 7-1184（from_dict 选项技术错误），新增 7-6002 替代
全部设 revised_at，走台账。
"""
import pathlib, sys, re, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import curate_core as cc
from datetime import datetime

NOW = datetime.now().isoformat(timespec="seconds")
BANK = cc.load_bank()
BY = BANK["questions_by_chapter"]

def get(qid):
    ch, seq = qid.split("-")
    for q in BY.get(ch, []):
        if str(q["seq"]).zfill(4) == seq and not q.get("deleted"):
            return q
    return None

changed = []

def touch(q):
    q["revised_at"] = NOW

# ---------- 1) type 2 -> 1 ----------
n2 = 0
for ch, arr in BY.items():
    for q in arr:
        if not q.get("deleted") and q.get("type") == 2:
            q["type"] = 1
            touch(q)
            n2 += 1
print("type2->1:", n2)

# ---------- 2) 多选1答案 -> 单选 ----------
M1 = ["1-0521", "1-1457", "1-1459", "1-1462", "1-1464", "1-1465", "1-1458",
      "2-1025", "2-1440", "2-1444", "2-1166", "2-1438", "2-1439", "2-1460",
      "2-1463", "2-6001", "2-1445", "2-1290", "3-1458", "4-1459", "5-1264",
      "5-1452", "6-1360", "6-1361", "6-1366", "6-1367", "6-1382", "8-1448",
      "9-1383", "10-1458", "11-1441", "12-1289", "12-1291"]
for qid in M1:
    q = get(qid)
    if q and q.get("type") == 1:
        q["type"] = 0
        touch(q)
print("multi1->single:", len(M1))

# 题干"哪些"改"哪个"
q = get("1-0521")
if q:
    q["stem"] = q["stem"].replace("以下哪些阶段涉及Tone的处理", "以下哪个阶段主要涉及 Tone（语气风格）的处理")
q = get("2-1166")
if q:
    q["stem"] = "以下选项中，属于在提示词中使用分隔符的主要目的的是？"

# ---------- 3) 残留标注 ----------
for ch, arr in BY.items():
    for q in arr:
        if q.get("deleted"):
            continue
        s = q.get("stem", "")
        s2 = re.sub(r"[（(]\s*多选[,，]\s*\d+\s*个选项\s*[)）]", "（多选）", s)
        if s2 != s:
            q["stem"] = s2
            touch(q)
            changed.append("MULTI_TAG")

# ---------- 4/5) 个案重写 ----------
REWRITE = {
 "6-1190": {
  "stem": "下列代码片段的作用是？\n\nfrom keras.preprocessing.sequence import pad_sequences\npadded_sequences = pad_sequences(sequences, maxlen=max_len, padding='post', truncating='post')",
  "analysis": "pad_sequences 把变长的 token 索引序列统一整理成固定宽度 max_len 的矩阵：不足 maxlen 的按 padding='post' 在尾部补 0，超过的按 truncating='post' 从尾部截断。这是深度学习文本预处理中构造等宽输入张量的步骤；它不做摘要生成、不做特征缩放，也不负责把词映射为向量（向量化由 Embedding 层完成）。",
 },
 "1-0521": {
  "analysis": "Tone（语气/风格）是生成阶段的行为特征：模型在推理时依据 system prompt 指令与采样参数（如 temperature、top_p）决定输出的正式程度与情感倾向。分词只做文本切分，向量化是静态嵌入映射，输出 Token 只是推理结果的编码呈现——风格已在推理阶段决定。",
 },
 "10-1187": {
  "stem": "使用 DashScope 的 OpenAI 兼容接口调用 qwen-max，得到响应对象 completion。以下哪个表达式能获取模型回复的文本内容？",
  "analysis": "OpenAI 兼容接口的响应结构中，completion.choices 是候选列表，通常取第 0 个元素 completion.choices[0]，其 message 为回复消息对象，文本内容在 message.content。A 只到 Choice 对象；B 缺少 choices 层级（completion 没有 message 属性）；D 的 choices 列表本身没有 content 属性。",
 },
 "8-1180": {
  "stem": "以下代码片段实现了哪种文本合规检查方法？\n\nimport re\n\ndef check_text(text):\n    pattern = r\"假货|劣质|骗子\"\n    if re.search(pattern, text):\n        return \"包含敏感词\"\n    else:\n        return \"文本安全\"\n\nprint(check_text(\"这个产品质量很好，不像其他假货\"))  # 输出：包含敏感词",
 },
 "9-1176": {
  "stem": "在 LlamaIndex 文档预处理函数 get_documents 中，replacements 字典（把\"，\"\"！\"\"？\"等中文标点替换为对应英文标点）的作用是：\n\ndef get_documents(path):\n    documents = SimpleDirectoryReader(path).load_data()\n    document = Document(text=\"\\n\".join([doc.text for doc in documents]))\n    replacements = {\"，\": \",\", \"！\": \"!\", \"？\": \"?\"}\n    for src, dst in replacements.items():\n        document.text = document.text.replace(src, dst)\n    return document",
 },
 "12-1289": {
  "stem": "这段代码的主要作用是？\n\nnode_parser = SentenceWindowNodeParser.from_defaults(\n    window_size=3,\n    window_metadata_key=\"window\",\n    original_text_metadata_key=\"original_text\",\n)\nnodes = node_parser.get_nodes_from_documents([document])\nwindow_text_replace = MetadataReplacementPostProcessor(target_metadata_key=\"window\")",
  "analysis": "SentenceWindowNodeParser 以每个句子为中心、附带前后各 window_size 句构成\"窗口\"存入元数据；检索命中细粒度句子后，MetadataReplacementPostProcessor 把用于生成的正文替换为扩展窗口内容。这是句子窗口检索：小块精准命中、大块上下文生成。A 是 Rerank；C 是自动合并检索；D 与本代码无关。",
 },
 "12-1291": {
  "stem": "以下哪个代码片段能够正确处理 classify_intent 函数可能抛出的异常，并打印错误信息？",
  "opts": {
   "A": "for id, query in feedback_list:\n    try:\n        intent = classify_intent(query)\n        print(f\"ID: {id}, Intent: {intent}\")\n    finally:\n        print(\"Finished processing query.\")",
   "B": "for id, query in feedback_list:\n    intent = classify_intent(query)\n    print(f\"ID: {id}, Intent: {intent}\")\nexcept Exception as e:\n    print(f\"Error: {e}\")",
   "C": "for id, query in feedback_list:\n    try:\n        intent = classify_intent(query)\n        print(f\"ID: {id}, Intent: {intent}\")\n    except Exception as e:\n        print(f\"Error processing query {id}: {e}\")",
   "D": "for id, query in feedback_list:\n    if classify_intent(query):\n        intent = classify_intent(query)\n        print(f\"ID: {id}, Intent: {intent}\")\n    else:\n        pass",
  },
  "analysis": "C 用 try 包裹可能抛异常的调用，except Exception 捕获后打印含 query id 的错误信息，循环可继续处理其余条目。A 只有 finally，异常不会被捕获、仍会向上抛出；B 的 except 没有对应 try，语法错误；D 没有异常处理，且对同一条 query 重复调用分类函数。",
 },
 "2-1290": {
  "stem": "检查以下代码：如果需要新增一个意图类别（例如\"入职流程\"），需要修改哪一部分？\n\n# 获取用户意图的核心算法\ndef get_purpose(document):\n    prompt_template = \"\"\"【角色背景】你是一个专业的管理者，你将阅读一条用户的问题并进行用户意图分类\n【任务要求】我们需要将用户的意图分成如下几类：请假政策，福利待遇，绩效考核，工作职责，开发规范\n【输出要求】请以json格式输出，不要输出其他内容，格式如\n{\"purpose\":\"请假政策\",\"query\":\"请假流程是怎样的，需要提前多久申请？\"}\n其中，purpose 是你识别出的意图，query 是用户输入的原始文本\n【用户输入】以下是用户输入，请审阅：\"\"\"\n    query = prompt_template + document",
  "analysis": "意图类别清单写在 prompt_template 的【任务要求】中，新增类别首先要在这里补充枚举项；若下游对分类结果有校验或分支处理逻辑，get_purpose 相关逻辑也需同步更新。A 错：用户 query 是待分类输入，不是类别定义处；B 错：输出 JSON 格式与类别数量无关；D 错：不存在需要改的独立 query 函数。",
 },
 "4-1286": {
  "stem": "下列关于将 AgentModule 类设计为基类的原因，正确的有哪些？\n\nclass AgentModule():\n    def __init__(self, name: str, description: str):\n        self.name = name\n        self.description = description\n\n    def __call__(self, query: str):\n        return self.query(query)\n\n    def query(self, query: str):\n        pass",
  "analysis": "A：基类统一实现 __init__，子类无需重复编写构造代码；C：基类 query 留空（pass），各子类按需覆写自己的 query，保持灵活性；E：基类提供统一 __call__，调用方可以用相同方式调用所有子类实例；F：统一接口带来多态与代码复用。B 错误：Python 支持多重继承，该说法本身不成立；D 错误：基类设计目的是复用与统一接口，Python 的私有性靠命名约定，与是否设基类无关。",
 },
 "12-1288": {
  "stem": "通过 LlamaIndex 创建 RAG 应用，关于下面这段代码作用的描述正确的有哪些？\n\ndef get_documents(path):\n    documents = SimpleDirectoryReader(path).load_data()\n    document = Document(text=\"\\n\\n\".join([doc.text for doc in documents]))\n    replacements = {\"，\": \",\", \"！\": \"!\", \"？\": \"?\"}\n    for src, dst in replacements.items():\n        document.text = document.text.replace(src, dst)\n    return document",
  "analysis": "该函数把指定目录的文件加载为 Document 对象（D），再合并为单个 Document（A），并把中文标点替换为英文标点——LlamaIndex 默认按英文标点切句，替换后可正常切分、避免 chunk 过长（C）。B 错误：代码只做标点替换，不涉及乱码检测或清洗。",
 },
}
for qid, spec in REWRITE.items():
    q = get(qid)
    if not q:
        print("missing:", qid)
        continue
    if "stem" in spec:
        q["stem"] = spec["stem"]
    if "analysis" in spec:
        q["analysis"] = spec["analysis"]
    for lab, text in (spec.get("opts") or {}).items():
        for o in q["options"]:
            if o["option_label"] == lab:
                o["option_text"] = text
    touch(q)
print("rewrites:", len(REWRITE))

# ---------- 6) 删除 7-1184 + 新增 7-6002 ----------
BID_D = "rebuild20261027_D_struct"
del_entries = [{"qid": "7-1184", "reason": "RAGAS Dataset.from_dict 要求各字段均为列表，原各选项均不严格成立，答案技术不可辩护；由新题 7-6002 替代"}]
res = cc.soft_delete(BANK, del_entries, source="题库重构批次D", batch_id=BID_D + "_del")
cc.append_batch("soft_delete", "rebuild_batch_D1.py", res["ledger_items"], reason="批次D删除1题", batch_id=BID_D + "_del")

NEW = {"seq": "6002", "type": 0,
 "stem": "在 RAGAS 中计算 Faithfulness（忠实度）指标时，评测样本必须包含哪组字段？",
 "options": [
  {"option_label": "A", "option_text": "question、contexts、answer（生成的答案）"},
  {"option_label": "B", "option_text": "question、answer、ground_truth（参考答案）"},
  {"option_label": "C", "option_text": "仅需 contexts 与 ground_truth"},
  {"option_label": "D", "option_text": "question、answer 与检索耗时"},
 ],
 "answer": "A",
 "analysis": "Faithfulness 衡量生成答案是否忠于检索到的上下文：先把答案分解为若干声明，再逐条判断能否由 contexts 支持，计算需要 question、contexts、answer 三个字段。B 是 Answer Correctness 的输入组合；C 缺少答案与问题无法判定；D 中耗时与忠实度无关。",
 "chapter": 7, "difficulty_score": 1, "difficulty_label": "入门", "difficulty_sort": 1,
 "governance": {"origin": "自编重构题", "source_note": "RAGAS Faithfulness 定义（官方教程 C2_2_5 及 RAGAS 文档）；替代原缺陷题 7-1184"}}
by7 = BY.setdefault("7", [])
if not any(str(x["seq"]).zfill(4) == "6002" for x in by7):
    by7.append(NEW)
    cc.append_batch("add_questions", "rebuild_batch_D1.py",
                    [{"qid": "7-6002", "before": None, "after": NEW, "reason": "重构新增替代题"}],
                    reason="批次D新增1题", batch_id=BID_D + "_add")

cc.write_bank(BANK)
print("批次D-1 完成")
