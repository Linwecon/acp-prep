# -*- coding: utf-8 -*-
"""题库治理共享核心库（curate core）

为 quiz_curate.py / verify_disputed.py / merge_new_questions.py 提供统一能力：

- 操作台账（data/curate/ledger.json）：所有批量变更记录批次、原因、时间、旧值，
  append-only，支持按批次回滚，重复执行天然幂等。
- 软删除 / 恢复：题目加 deleted + deleted_meta 字段，不出现在运行时 .js 中，
  JSON 主文件保留完整数据，可随时恢复。
- 答案修正历史：题内 answer_history 保存旧答案/旧解析，可按批次回滚。
- 语义查重：字符 bigram Jaccard 相似度，不依赖外部库。
- 章节正文提取：从 docs/ACP高频知识点总结.md 提取 12 章正文。

所有写库操作先备份 data/quiz_categorized.json / .js 到 data/backup/。
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import threading
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "data" / "quiz_categorized.json"
JS_PATH = ROOT / "data" / "quiz_categorized.js"
CURATE_DIR = ROOT / "data" / "curate"
LEDGER_PATH = CURATE_DIR / "ledger.json"
BACKUP_DIR = ROOT / "data" / "backup"
KNOWLEDGE_MD = ROOT / "docs" / "ACP高频知识点总结.md"

DIFF_LABELS = {"入门": 1, "进阶": 2, "挑战": 3}


# ---------------- 题库基础 ----------------

def qid_of(ch, seq) -> str:
    return f"{ch}-{str(seq).zfill(4)}"


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def stem_key(text: str) -> str:
    return re.sub(r"\s", "", str(text or ""))


def load_bank() -> dict:
    return json.loads(JSON_PATH.read_text(encoding="utf-8"))


def bank_questions(bank: dict, include_deleted=False) -> list[dict]:
    out = []
    for ch, qs in bank["questions_by_chapter"].items():
        for q in qs:
            if q.get("deleted") and not include_deleted:
                continue
            q = dict(q)
            q["chapter"] = int(ch)
            q["qid"] = qid_of(ch, q["seq"])
            out.append(q)
    return out


def build_index(bank: dict) -> dict:
    """qid -> (ch, q)。软删除的题也在索引中（恢复/回滚需要）。"""
    index = {}
    for ch, qs in bank["questions_by_chapter"].items():
        for q in qs:
            index[qid_of(ch, q["seq"])] = (ch, q)
    return index


def backup_bank() -> str:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for p in (JSON_PATH, JS_PATH):
        if p.exists():
            (BACKUP_DIR / f"{p.stem}_{stamp}{p.suffix}").write_text(
                p.read_text(encoding="utf-8"), encoding="utf-8")
    return stamp


def _atomic_write_text(path: pathlib.Path, text: str) -> None:
    """原子替换写文件：先写临时文件再 os.replace，避免并发/中断产生半写状态。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_bank(bank: dict, backup: bool = True) -> None:
    """写回 JSON 主文件（含软删除数据）与运行时 .js（排除软删除题）。原子替换。"""
    if backup:
        backup_bank()
    by_ch = bank["questions_by_chapter"]
    diff = {"入门": 0, "进阶": 0, "挑战": 0}
    for arr in by_ch.values():
        for q in arr:
            label = q.get("difficulty_label", "进阶")
            if label in diff:
                diff[label] += 1
    bank["total"] = sum(len(v) for v in by_ch.values())
    bank["difficulty_counts"] = diff
    bank["active_total"] = sum(
        1 for arr in by_ch.values() for q in arr if not q.get("deleted"))
    _atomic_write_text(JSON_PATH, json.dumps(bank, ensure_ascii=False, indent=2))
    live = {ch: [q for q in qs if not q.get("deleted")] for ch, qs in by_ch.items()}
    js = (
        "const QUIZ_CHAPTERS = " + json.dumps(bank["chapters"], ensure_ascii=False) + ";\n\n"
        "const QUIZ_DATA_BY_CHAPTER = "
        + json.dumps(live, ensure_ascii=False, separators=(",", ":")) + ";\n"
    )
    _atomic_write_text(JS_PATH, js)


# ---------------- 操作台账 ----------------

def load_ledger() -> dict:
    if LEDGER_PATH.exists():
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    return {"batches": []}


def save_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(LEDGER_PATH, json.dumps(ledger, ensure_ascii=False, indent=2))


def batch_exists(batch_id: str) -> bool:
    return any(b.get("batch_id") == batch_id for b in load_ledger()["batches"])


def new_batch_id(kind: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    digest = hashlib.md5(f"{kind}:{stamp}".encode()).hexdigest()[:6]
    return f"{stamp}_{digest}"


def append_batch(kind: str, source: str, items: list, reason: str = "",
                 batch_id: str | None = None) -> str:
    """追加一个操作批次。batch_id 重复时视为已执行，直接返回（幂等）。"""
    ledger = load_ledger()
    if batch_id is None:
        batch_id = new_batch_id(kind)
    if batch_exists(batch_id):
        return batch_id
    ledger["batches"].append({
        "batch_id": batch_id,
        "at": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "source": source,
        "reason": reason,
        "count": len(items),
        "items": items,
    })
    save_ledger(ledger)
    return batch_id


def rollback_batch(batch_id: str, dry_run: bool = True) -> tuple[int, list]:
    """按批次逆操作回滚：软删除→恢复，恢复→重新软删除，answer_fix→还原旧答案，move→移回。

    冲突检测：若批次之后题目又被其它操作修改（当前状态 ≠ 本批次的预期结果），
    跳过该条并记录冲突说明，绝不覆盖后续修改内容。
    返回 (可回滚条数, 说明列表)。
    """
    ledger = load_ledger()
    batch = next((b for b in ledger["batches"] if b.get("batch_id") == batch_id), None)
    if not batch:
        return 0, [f"批次不存在: {batch_id}"]
    kind = batch.get("kind")
    notes = []
    undoable = ("soft_delete", "restore", "answer_fix", "move", "add_questions")
    if kind not in undoable:
        return 0, [f"批次类型 {kind} 不支持自动回滚，请手工处理"]
    bank = load_bank()
    index = build_index(bank)
    done = 0
    for it in batch.get("items", []):
        qid = it.get("qid")
        # move 批次：qid 是移动前的编号，题目现在位于 it["to"] 章
        cur_qid = qid
        if kind == "move":
            cur_qid = f"{it.get('to')}-{str(it.get('after_seq') or '').zfill(4)}"
        if cur_qid not in index:
            cur_qid = qid  # 容错：直接按旧编号找
        if cur_qid not in index:
            notes.append(f"{qid}: 题号不存在，跳过")
            continue
        ch, q = index[cur_qid]
        # ---- 冲突检测：当前状态必须等于本批次的预期结果 ----
        if kind == "soft_delete" and not q.get("deleted"):
            notes.append(f"{qid}: 冲突——题目已被后续操作恢复，跳过（不覆盖）")
            continue
        if kind == "restore" and q.get("deleted"):
            notes.append(f"{qid}: 冲突——题目已被后续操作再次删除，跳过（不覆盖）")
            continue
        if kind == "answer_fix":
            after = it.get("after") or {}
            if any(q.get(field) != value for field, value in after.items()):
                notes.append(f"{qid}: 冲突——题目已被后续批次修改，跳过（不覆盖后续修改）")
                continue
        if kind == "add_questions" and q != it.get("after"):
            notes.append(f"{qid}: 冲突——新增题已经发生后续修改，跳过")
            continue
        if kind == "move" and str(ch) != str(it.get("to")):
            notes.append(f"{qid}: 冲突——题目已被后续操作移往他章，跳过（不覆盖）")
            continue
        # ---- 逆操作 ----
        if kind == "soft_delete":
            q.pop("deleted", None)
            q.pop("deleted_meta", None)
        elif kind == "restore":
            q["deleted"] = True
            q["deleted_meta"] = it.get("after_meta") or {"reason": f"回滚批次 {batch_id} 的恢复操作"}
        elif kind == "answer_fix":
            before = it.get("before") or {}
            for field in ("answer", "analysis", "type", "stem", "options"):
                if field in before:
                    q[field] = before[field]
            q["answer_history"] = [h for h in q.get("answer_history", [])
                                   if h.get("batch_id") != batch_id]
        elif kind == "add_questions":
            q["deleted"] = True
            q["deleted_meta"] = {"reason": f"回滚新增题批次 {batch_id}", "batch_id": f"undo_{batch_id}"}
        elif kind == "move":
            frm = str(it.get("from"))
            to = str(ch)
            seq_key = str(q["seq"]).zfill(4)
            by_ch = bank["questions_by_chapter"]
            by_ch[to] = [x for x in by_ch.get(to, []) if x is not q]
            q["chapter"] = int(frm) if frm.isdigit() else frm
            by_ch.setdefault(frm, []).append(q)
            if it.get("before_seq") and str(it["before_seq"]).zfill(4) != seq_key:
                q["seq"] = str(it["before_seq"]).zfill(4)
                notes.append(f"{qid}: seq 还原为 {q['seq']}")
        done += 1
    if not dry_run:
        if any(b.get("batch_id") == f"undo_{batch_id}" for b in ledger["batches"]):
            return 0, ["该批次已回滚过（幂等保护）"]
        write_bank(bank)
        append_batch(f"undo_{batch_id}", f"rollback of {kind}", [], f"回滚批次 {batch_id}",
                     batch_id=f"undo_{batch_id}")
    return done, notes


# ---------------- 软删除 / 恢复 ----------------

def soft_delete(bank: dict, entries: list, source: str, batch_id: str | None = None) -> dict:
    """entries: [{qid, reason}]。已删除的跳过。返回统计。"""
    index = build_index(bank)
    items, skipped, applied = [], [], 0
    for e in entries:
        qid = str(e.get("qid", ""))
        reason = str(e.get("reason", ""))
        if qid not in index:
            skipped.append({"qid": qid, "why": "题号不存在"})
            continue
        ch, q = index[qid]
        if q.get("deleted"):
            skipped.append({"qid": qid, "why": "已是软删除状态"})
            continue
        meta = {"reason": reason, "source": source,
                "at": datetime.now().isoformat(timespec="seconds"),
                "batch_id": batch_id or ""}
        items.append({"qid": qid, "before": {"deleted": False},
                      "after": {"deleted": True, "reason": reason},
                      "after_meta": meta})
        q["deleted"] = True
        q["deleted_meta"] = meta
        applied += 1
    return {"applied": applied, "skipped": skipped, "ledger_items": items}


def restore(bank: dict, qids: list, source: str, batch_id: str | None = None) -> dict:
    index = build_index(bank)
    items, skipped, applied = [], [], 0
    for qid in qids:
        qid = str(qid)
        if qid not in index:
            skipped.append({"qid": qid, "why": "题号不存在"})
            continue
        ch, q = index[qid]
        if not q.get("deleted"):
            skipped.append({"qid": qid, "why": "未处于软删除状态"})
            continue
        items.append({"qid": qid, "before": {"deleted": True,
                                             "reason": (q.get("deleted_meta") or {}).get("reason", "")},
                      "after": {"deleted": False}})
        q.pop("deleted", None)
        q.pop("deleted_meta", None)
        applied += 1
    return {"applied": applied, "skipped": skipped, "ledger_items": items}


# ---------------- 移章 ----------------

def move_questions(bank: dict, entries: list, valid_chapters) -> dict:
    """entries: [{qid, to, reason}]。返回 {plan, skipped, ledger_items}（不写库）。

    目标章 seq 冲突时重编为目标章最大 seq+1；ledger 记录 before_seq 支持回滚。
    """
    index = build_index(bank)
    by_ch = bank["questions_by_chapter"]
    plan, skipped, ledger_items = [], [], []
    for it in entries:
        qid = str(it.get("qid", ""))
        to = it.get("to") or it.get("chapter")
        try:
            to = int(to)
        except (TypeError, ValueError):
            skipped.append({"qid": qid, "why": "目标章非法"})
            continue
        if qid not in index:
            skipped.append({"qid": qid, "why": "题号不存在"})
            continue
        if to not in valid_chapters:
            skipped.append({"qid": qid, "why": f"目标章非法: {to}"})
            continue
        cur_ch, q = index[qid]
        if str(cur_ch) == str(to):
            skipped.append({"qid": qid, "why": "已在目标章"})
            continue
        plan.append({"qid": qid, "from": cur_ch, "to": to,
                     "reason": str(it.get("reason", ""))})
    for p in plan:
        cur_ch, q = index[p["qid"]]
        tgt = str(p["to"])
        old_seq = str(q["seq"]).zfill(4)
        tgt_seqs = {str(x["seq"]).zfill(4) for x in by_ch.get(tgt, [])}
        new_seq = old_seq
        if old_seq in tgt_seqs:
            nums = [int(s) for s in tgt_seqs if s.isdigit()]
            new_seq = str((max(nums) if nums else 0) + 1).zfill(4)
            q["seq"] = new_seq
        by_ch[cur_ch] = [x for x in by_ch[cur_ch] if x is not q]
        q["chapter"] = p["to"]
        by_ch.setdefault(tgt, []).append(q)
        ledger_items.append({"qid": p["qid"],
                             "from": int(cur_ch) if str(cur_ch).isdigit() else cur_ch,
                             "to": p["to"],
                             "before_seq": old_seq, "after_seq": new_seq,
                             "reason": p["reason"]})
    return {"plan": plan, "skipped": skipped, "ledger_items": ledger_items}


# ---------------- 答案修正（带旧版本 + 幂等） ----------------

def apply_answer_fix(bank: dict, fixes: list, source: str,
                     batch_id: str | None = None) -> dict:
    """fixes: [{qid, final: [答案字母], analysis?, reason?, evidence?}]

    - 修正前把旧答案/旧解析写入题内 answer_history（永久可追溯）。
    - 重复执行：答案已等于目标值且历史中已有同一 batch 记录 → 跳过，不重复写入。
    - 台账记录批次，可用 rollback_batch 回滚。
    """
    index = build_index(bank)
    items, skipped, applied = [], [], 0
    for f in fixes:
        qid = str(f.get("qid", ""))
        final = f.get("final") or []
        if qid not in index:
            skipped.append({"qid": qid, "why": "题号不存在"})
            continue
        ch, q = index[qid]
        new_ans = ",".join(final)
        old_ans = str(q.get("answer", ""))
        old_analysis = str(q.get("analysis", ""))
        new_analysis = str(f.get("analysis") or old_analysis)
        # 幂等：答案与解析都已等于目标值 → 无需任何变更
        if old_ans == new_ans and new_analysis == old_analysis:
            skipped.append({"qid": qid, "why": "已应用过（幂等跳过）"})
            continue
        if old_ans != new_ans:
            hist = q.setdefault("answer_history", [])
            hist.append({
                "old_answer": old_ans,
                "old_analysis": old_analysis,
                "new_answer": new_ans,
                "batch_id": batch_id or "",
                "at": datetime.now().isoformat(timespec="seconds"),
                "source": source,
                "reason": str(f.get("reason", "")),
                "evidence": f.get("evidence", {}),
            })
            q["answer"] = new_ans
            items.append({"qid": qid,
                          "before": {"answer": old_ans, "analysis": old_analysis},
                          "after": {"answer": new_ans},
                          "reason": str(f.get("reason", ""))})
        if new_analysis != old_analysis:
            q["analysis"] = new_analysis
            if not any(i["qid"] == qid for i in items):
                items.append({"qid": qid, "before": {"analysis": old_analysis},
                              "after": {"analysis": new_analysis},
                              "reason": "解析更新"})
        applied += 1
    return {"applied": applied, "skipped": skipped, "ledger_items": items}


# ---------------- 统一答案修正守卫（CLI / 管理 API / 显式修正共用） ----------------

OPS_LOCK = threading.Lock()  # 管理 API 的读库→校验→写库→记账全程互斥


def check_fix_entry(fix: dict, q: dict, allow_manual: bool = False) -> tuple[bool, str, dict]:
    """答案修正条目守卫。所有修正入口必须经过本函数。

    检查（全部通过才允许修正）：
    1. 题目存在且指纹已绑定：无指纹的旧结果一律拒绝（不得补绑当前指纹）；
    2. 指纹与当前题目内容（题型+题干+选项）匹配，否则结果失效；
    3. 答案格式：字母在选项内、单选 1 个 / 多选 ≥2 个；
    4. 证据充分：教材证据 supported=true 且 quote_found=true（引用逐段可定位）
       且证据绑定同一内容指纹。"引用存在"与"支持结论"分开记录，缺一不可。

    人工覆盖（allow_manual=True 时）：带 manual_reason 的条目跳过指纹/证据要求
    （仍必须通过答案格式校验），返回 info["manual"]=True，调用方必须在台账中
    记录为人工覆盖（不得记为验证通过）。
    """
    labels = [str(o.get("option_label", "")).upper() for o in q.get("options", [])]
    ans = sorted({re.sub(r"[^A-H]", "", str(a)).upper()
                  for a in (fix.get("final") or []) if re.sub(r"[^A-H]", "", str(a)).upper()})
    if not ans:
        return False, "答案为空", {}
    if any(a not in labels for a in ans):
        return False, f"答案不在选项中: {ans}", {}
    qtype = q.get("type", 0)
    if qtype == 0 and len(ans) != 1:
        return False, f"单选答案数量异常: {ans}", {}
    if qtype == 1 and len(ans) < 2:
        return False, f"多选答案数量异常: {ans}", {}

    manual_reason = str(fix.get("manual_reason", "")).strip()
    if manual_reason:
        if not allow_manual:
            return False, "人工覆盖入口未开放", {}
        if len(manual_reason) < 5:
            return False, "人工覆盖必须提供明确理由（≥5 字）", {}
        return True, "人工覆盖（未通过自动验证，须在台账记录人工覆盖原因）", {"manual": True}

    fp = fix.get("fingerprint")
    if not fp:
        return False, "未绑定题目内容指纹（无历史快照的旧结果须重新验证，不得补绑）", {}
    if fp != q_fingerprint(q):
        return False, "题目内容已变化，校验结果失效", {}

    ev = fix.get("external_evidence") or {}
    if ev.get("supported") is not True or ev.get("quote_found") is not True:
        return False, "教材证据不足或无法确认（进入复核，不自动修正）", {}
    ev_fp = ev.get("fingerprint")
    if not ev_fp:
        return False, "证据未绑定题目内容指纹", {}
    if ev_fp != fp:
        return False, "证据与校验结果的题目版本不一致", {}
    return True, "验证通过（指纹匹配 + 教材证据确认）", {"manual": False}


# ---------------- 语义查重 ----------------

def bigrams(text: str) -> set:
    t = stem_key(text)
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def question_text(q: dict) -> str:
    parts = [q.get("stem", "")]
    parts.extend(o.get("option_text", "") for o in q.get("options", []))
    return " ".join(parts)


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


def top_similar(target: dict, pool: list, k: int = 3, min_sim: float = 0.35) -> list:
    """在 pool 中找与 target 文本最相似的 k 题（bigram Jaccard ≥ min_sim）。

    注意：这是**文本相似度**初筛；是否构成语义重复（考点/解题路径相同）
    须由调用方做进一步语义判定。
    返回 [{qid, sim}] 降序。
    """
    gt = bigrams(question_text(target))
    out = []
    for q in pool:
        if q.get("qid") == target.get("qid"):
            continue
        sim = jaccard(gt, bigrams(question_text(q)))
        if sim >= min_sim:
            out.append({"qid": q["qid"], "sim": round(sim, 3)})
    out.sort(key=lambda x: -x["sim"])
    return out[:k]


# ---------------- 题目内容指纹（校验结果与题目版本绑定） ----------------

def q_fingerprint(q: dict) -> str:
    """题目内容指纹：题型 + 题干 + 选项文本的稳定哈希（不含答案——答案通常是校验的输出）。

    题型（单选/多选）与必要条件（题干、选项）都参与版本判断：
    任一变化即指纹失配，旧校验/投票/证据结果失效，不得复用缓存。
    """
    parts = [str(q.get("type", "")), stem_key(q.get("stem", ""))]
    for o in q.get("options", []):
        parts.append(f"{o.get('option_label', '')}:{stem_key(o.get('option_text', ''))}")
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def fingerprint_stale(rec: dict, q: dict) -> bool:
    """校验记录 rec 的指纹与当前题目 q 是否失配（rec 缺指纹视为未绑定）。"""
    fp = rec.get("fingerprint") if isinstance(rec, dict) else None
    if not fp:
        return False  # 未绑定 ≠ 失效，由调用方按"未绑定"处理
    return fp != q_fingerprint(q)


# ---------------- 证据回溯（引用必须能在章节原文中找到） ----------------

_PUNCT = re.compile(r"[\\\s，。、；：？！“”‘’()（）\[\]【】《》,.:;?!'\"`\-—_*#>]")


def _clean(text: str) -> str:
    return _PUNCT.sub("", str(text or "")).lower()


def locate_quote(quote: str, source_text: str, min_overlap: float = 0.75) -> dict:
    """把"原文证据"逐段定位到资料原文中。

    返回 {
      "segments": [{"text", "located", "mode", "offset", "excerpt"}],
          mode: exact=清洗后逐字命中 / overlap=近似命中(候选定位)；
          offset 为清洗后原文中的起始位置，excerpt 为命中的原文片段（便于人工定位）。
      "quote_found": bool,   # 所有有效段落均定位到原文 → 引用存在
      "unmatched":  [text],  # 未能定位的段落（含编造/改写内容）
    }
    注意：quote_found 只回答"引用是否存在"，不回答"引用是否支持结论"——
    两者必须分开记录（见 check_fix_entry）。
    """
    import difflib

    def clean_with_map(text: str):
        """清洗文本并保留 cleaned[i] -> 原文下标 的映射。"""
        out, mapping = [], []
        for i, ch in enumerate(text):
            if _PUNCT.sub("", ch):
                out.append(ch.lower())
                mapping.append(i)
        return "".join(out), mapping

    s_clean, s_map = clean_with_map(source_text)
    raw = str(quote or "")
    # 按句切分，过短片段并入前一段（避免"对/是"级别碎片被单独算作证据）
    rough = [s for s in re.split(r"[\n]+|(?:。|；|;|！|!|？|\?)+", raw) if s.strip()]
    segs: list[str] = []
    for s in rough:
        s = s.strip()
        if s and len(_clean(s)) < 4 and segs:
            segs[-1] += s
        elif s:
            segs.append(s)

    segments, unmatched = [], []
    for seg in segs:
        seg_clean = _clean(seg)
        if not seg_clean or not s_clean:
            unmatched.append(seg)
            segments.append({"text": seg[:120], "located": False, "mode": "missing",
                             "offset": -1, "excerpt": ""})
            continue
        pos = s_clean.find(seg_clean)
        if pos >= 0:
            orig_start = s_map[pos]
            orig_end = s_map[min(pos + len(seg_clean) - 1, len(s_map) - 1)] + 1
            segments.append({"text": seg[:120], "located": True, "mode": "exact",
                             "offset": orig_start,
                             "excerpt": source_text[orig_start:orig_end][:120]})
            continue
        # 滑窗近似（候选定位，仅用于人工复核，不等同逐字证据）
        found = None
        win = len(seg_clean)
        step = max(1, (len(s_clean) - win) // 8 or 1)
        for i in range(0, max(1, len(s_clean) - win + 1), step):
            window = s_clean[i:i + win + 8]
            if difflib.SequenceMatcher(None, seg_clean, window).ratio() >= min_overlap:
                found = i
                break
        if found is not None:
            orig_start = s_map[found]
            orig_end = s_map[min(found + win + 8 - 1, len(s_map) - 1)] + 1
            segments.append({"text": seg[:120], "located": True, "mode": "overlap",
                             "offset": orig_start,
                             "excerpt": source_text[orig_start:orig_end][:120]})
        else:
            unmatched.append(seg)
            segments.append({"text": seg[:120], "located": False, "mode": "missing",
                             "offset": -1, "excerpt": ""})
    return {
        "segments": segments,
        "quote_found": bool(segs) and not unmatched,
        "unmatched": unmatched,
    }


def verify_evidence_quote(quote: str, source_text: str, min_overlap: float = 0.75) -> dict:
    """兼容旧接口：仅判断引用是否可定位（不含"是否支持结论"的判断）。"""
    r = locate_quote(quote, source_text, min_overlap)
    return {"verified": r["quote_found"], "mode": "exact" if r["quote_found"] else "missing"}


def find_duplicates(questions: list, threshold: float = 0.6) -> list:
    """返回 [{a, b, sim}]（sim 降序）。questions 需含 qid 字段。"""
    grams = [(q["qid"], bigrams(question_text(q))) for q in questions]
    out = []
    n = len(grams)
    for i in range(n):
        qi, gi = grams[i]
        li = len(gi)
        for j in range(i + 1, n):
            qj, gj = grams[j]
            lj = len(gj)
            if abs(li - lj) > 0.9 * max(li, lj):
                continue
            sim = jaccard(gi, gj)
            if sim >= threshold:
                out.append({"a": qi, "b": qj, "sim": round(sim, 3)})
    out.sort(key=lambda x: -x["sim"])
    return out


def dup_groups(questions: list, threshold: float = 0.6) -> list[list[str]]:
    """并查集聚合为重复组，组内按 qid 排序，只返回 size>1 的组。"""
    pairs = find_duplicates(questions, threshold)
    parent = {q["qid"]: q["qid"] for q in questions}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs:
        ra, rb = find(p["a"]), find(p["b"])
        if ra != rb:
            parent[rb] = ra
    groups = {}
    for q in questions:
        groups.setdefault(find(q["qid"]), []).append(q["qid"])
    return sorted([sorted(v) for v in groups.values() if len(v) > 1])


# ---------------- 章节正文提取 ----------------

def chapter_names() -> dict:
    m = re.search(r"const\s+QUIZ_CHAPTERS\s*=\s*(\{.*?\});",
                  JS_PATH.read_text(encoding="utf-8"), re.S)
    return json.loads(m.group(1)) if m else {}


def extract_chapter_sections(max_chars: int = 7000) -> dict:
    """从 docs/ACP高频知识点总结.md 提取 12 章正文。

    注意：原文档没有结构化的"学习目标"块，这里只能提供章节正文与代码示例；
    学习目标如需原文依据，属于缺失资料，由使用方明确声明。
    """
    md = KNOWLEDGE_MD.read_text(encoding="utf-8")
    sections = {}
    for n in range(1, 13):
        m = re.search(rf"^## {n}\. (.+)$", md, re.M)
        if not m:
            continue
        start = m.start()
        if n < 12:
            m2 = re.search(rf"^## {n + 1}\. ", md[start + 10:], re.M)
        else:
            m2 = re.search(r"^## 附录", md[start + 10:], re.M)
        end = start + 10 + m2.start() if m2 else len(md)
        seg = md[start:end]
        # 去掉 md 内嵌代码块行首的 '#' 伪标题噪音，压缩空白
        seg = re.sub(r"\n{3,}", "\n\n", seg)
        sections[n] = {
            "title": m.group(1).strip(),
            "text": seg[:max_chars],
            "truncated": len(seg) > max_chars,
        }
    return sections
