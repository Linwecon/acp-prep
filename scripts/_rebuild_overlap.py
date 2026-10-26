# -*- coding: utf-8 -*-
"""信号重叠分析：确定删除候选与实际补写工作量。"""
import json, pathlib, re
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
att = json.loads((ROOT / "data" / "curate" / "rebuild" / "attention.json").read_text(encoding="utf-8"))
clusters = json.loads((ROOT / "data" / "curate" / "rebuild" / "clusters.json").read_text(encoding="utf-8"))
if isinstance(clusters, dict):
    clusters = clusters.get("clusters", [])
bank = json.loads((ROOT / "data" / "quiz_categorized.json").read_text(encoding="utf-8"))
by_ch = bank["questions_by_chapter"]

flags_by_id = {a["id"]: set(a.get("flags", [])) for a in att}
cluster_ids = set()
for cl in clusters:
    for i in cl:
        cluster_ids.add(i)

# 缺解析题的分布与重叠
no_an = [i for i, f in flags_by_id.items() if "no_analysis" in f]
print(f"缺解析 {len(no_an)}; 其中同时命中重复簇 {len([i for i in no_an if i in cluster_ids])}")
ch_cnt = Counter(i.split('-')[0] for i in no_an)
print("缺解析按章:", dict(sorted(ch_cnt.items(), key=lambda x: int(x[0]))))
# 缺解析且同时有其它硬缺陷
for i in no_an[:0]:
    pass
multi_flag = [i for i in no_an if len(flags_by_id[i]) > 1]
print(f"缺解析且多信号: {len(multi_flag)}")
only_no_an = [i for i in no_an if flags_by_id[i] == {"no_analysis"}]
print(f"仅缺解析(无其它信号): {len(only_no_an)}")

# 重复簇统计
sizes = Counter(len(c) for c in clusters)
print("簇大小分布:", dict(sizes))
dup_to_delete = sum(len(c) - 1 for c in clusters)
print(f"重复簇去重需删除(每簇留1): {dup_to_delete}")

# 簇内答案冲突的簇
conflict_clusters = []
def get_q(qid):
    ch, seq = qid.split('-')
    for q in by_ch.get(ch, []):
        if str(q.get("seq")) == seq or f"{ch}-{seq}" == f"{ch}-{str(q.get('seq')).zfill(4)}":
            return q
    return None

def ans_norm(q):
    if q is None: return None
    a = re.sub(r"[,\s]", "", str(q.get("answer", "")))
    return a

for cl in clusters:
    ans_set = set()
    for i in cl:
        q = get_q(i)
        if q: ans_set.add(ans_norm(q))
    if len(ans_set) > 1:
        conflict_clusters.append(cl)
print(f"答案冲突簇: {len(conflict_clusters)}")

# 虚构题清单确认
FAB = ["ask_llm_route", "abstract_generator", "reviewed_prompt", "translate_prompt"]
fab_ids = []
for ch, arr in by_ch.items():
    for q in arr:
        if q.get("deleted"): continue
        text = q.get("stem","") + json.dumps(q.get("options",[]), ensure_ascii=False) + q.get("analysis","")
        if any(f in text for f in FAB):
            fab_ids.append(f"{ch}-{str(q['seq']).zfill(4)}")
print(f"虚构API题: {len(fab_ids)} -> {fab_ids}")

# 教材引用题
jiaocai = []
for ch, arr in by_ch.items():
    for q in arr:
        if q.get("deleted"): continue
        if re.search(r"(根据|依据|按照|参照)教材|(根据|依据)本章|(根据|依据)第.{1,8}节|教材\d+\.\d", q.get("stem","")):
            jiaocai.append(f"{ch}-{str(q['seq']).zfill(4)}")
print(f"题干教材引用: {len(jiaocai)}")

# 残留多选标注
resid = []
for ch, arr in by_ch.items():
    for q in arr:
        if q.get("deleted"): continue
        if re.search(r"[（(]\s*多选[,，]\s*\d+\s*个选项\s*[)）]", q.get("stem","")):
            resid.append(f"{ch}-{str(q['seq']).zfill(4)}")
print(f"残留'（多选N选项）': {len(resid)} -> {resid}")

# 绝对词泄题 + 最长正确项(需人工复核, 只统计不与删除重叠)
leak = [i for i, f in flags_by_id.items() if "longest_is_answer_leak" in f or "abs_words_only_on_distractors" in f]
print(f"泄题信号题: {len(leak)}, 其中同时在重复簇: {len([i for i in leak if i in cluster_ids])}")

ctx = [i for i, f in flags_by_id.items() if "context_dependent" in f]
print(f"上下文依赖: {len(ctx)}, 在重复簇: {len([i for i in ctx if i in cluster_ids])}")

priv = [i for i, f in flags_by_id.items() if "private_function_reference" in f]
print(f"私有函数引用: {priv}")

# 综合删除预估: 虚构 + 簇内多余 + 图片题
est_delete = len(fab_ids) + dup_to_delete + 1
print(f"\n预估删除: ~{est_delete} (虚构{len(fab_ids)} + 去重{dup_to_delete} + 图片1, 有重叠)")
