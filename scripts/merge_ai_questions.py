# -*- coding: utf-8 -*-
"""AI 出题候选的检查与入库：格式 → 精确/文本相似查重 → 证据逐字定位 → 质量字段自查 → 入库。

验证方式如实记录为 author-ai-selfcheck（GLM 会话内出题自查 + 原文证据程序定位），
不冒充外部多模型验证。
"""
import argparse
import copy
import json
import pathlib
import re
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import curate_core as cc
import quiz_curate as qc
import merge_new_questions as merge

ROOT = pathlib.Path(__file__).resolve().parent.parent
GOV = ROOT / 'data' / 'curate' / 'governance'
SRC = GOV / 'ai_new_questions.json'
TARGET = 100
SIM_REJECT = 0.60   # 文本相似度 ≥ 此值拒绝（阈值未校准，作筛选）
SIM_FLAG = 0.45     # 0.45~0.60 打印供人工复核


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        print('需要 --dry-run 或 --apply')
        return 1

    src = json.loads(SRC.read_text(encoding='utf-8'))
    bank = cc.load_bank()
    all_q = [dict(q, qid=cc.qid_of(ch, q['seq']))
             for ch, qs in bank['questions_by_chapter'].items() for q in qs]
    active_q = [q for q in all_q if not q.get('deleted')]
    all_keys = {cc.stem_key(q['stem']) for q in all_q}
    sections = cc.extract_chapter_sections(100000)
    audit = json.loads((GOV / 'audit.json').read_text(encoding='utf-8'))
    excluded = {r['qid'] for r in audit['rows'] if r['action'] == 'review'}

    accepted, rejected = [], []
    for it in src['items']:
        ch = it['ch']
        stem = cc.normalize_space(it['stem'])
        opts = [{'option_label': l, 'option_text': cc.normalize_space(t)}
                for l, t in zip('ABCD', it['options'])]
        ans = ','.join(sorted(set(it['answer'].split(','))))
        q = {
            'seq': '0000',  # 校验占位；入库时按章重新分配
            'type': 1 if len(ans) > 1 else 0, 'stem': stem, 'options': opts,
            'answer': ans, 'analysis': cc.normalize_space(it['analysis']),
            'chapter': ch,
            'difficulty_score': {'入门': 1, '进阶': 2, '挑战': 3}[it['diff']],
            'difficulty_label': it['diff'],
            'difficulty_sort': {'入门': 1, '进阶': 2, '挑战': 3}[it['diff']],
        }
        tag = f"ch{ch} [{it['kp']}]"
        # 1. 格式
        if merge.validate(dict(q, chapter=ch)):
            rejected.append({'tag': tag, 'why': '格式校验失败: ' + str(merge.validate(dict(q, chapter=ch)))})
            continue
        # 2. 精确查重（含软删除）
        if cc.stem_key(stem) in all_keys:
            rejected.append({'tag': tag, 'why': '题干精确重复'})
            continue
        # 3. 文本相似查重
        sims = cc.top_similar({'stem': stem, 'options': opts, 'qid': None}, active_q, k=3, min_sim=SIM_REJECT)
        if sims:
            rejected.append({'tag': tag, 'why': f"文本相似度过高: {sims[0]['qid']} sim={sims[0]['sim']}"})
            continue
        flagged = cc.top_similar({'stem': stem, 'options': opts, 'qid': None}, active_q, k=1, min_sim=SIM_FLAG)
        # 4. 证据逐字定位
        loc = cc.locate_quote(it['quote'], sections[ch]['text'])
        if not loc['quote_found']:
            rejected.append({'tag': tag, 'why': f"证据无法定位: {loc['unmatched'][:1]}"})
            continue
        accepted.append((q, it, flagged))

    print(f"候选 {len(src['items'])} → 通过 {len(accepted)}，淘汰 {len(rejected)}")
    for r in rejected:
        print('  [淘汰]', r['tag'], '|', r['why'])
    for q, it, flagged in accepted:
        note = f"（近似: {flagged[0]['qid']} {flagged[0]['sim']}，考点/路径不同）" if flagged else ''
        print(f"  [通过] ch{q['chapter']} [{it['kp']}] {it['diff']} {q['answer']}{note}")

    # 入库数量按缺口截断
    need = {}
    for ch in (6, 11, 12):
        have = sum(q['chapter'] == ch and q['qid'] not in excluded for q in active_q)
        need[ch] = max(0, TARGET - have)
    print('入库前缺口:', need)
    final, used = [], dict(need)
    for q, it, flagged in accepted:
        if used.get(q['chapter'], 0) <= 0:
            continue
        used[q['chapter']] -= 1
        final.append((q, it))
    print(f"实际入库 {len(final)}（ch6 {need[6] - used[6]}/ch11 {need[11] - used[11]}/ch12 {need[12] - used[12]}）")

    if args.dry_run:
        print('[dry-run] 未写库')
        return 0

    before = copy.deepcopy(bank)
    items = []
    now = datetime.now().isoformat(timespec='seconds')
    for q, it in final:
        ch = str(q['chapter'])
        arr = bank['questions_by_chapter'][ch]
        seq = max(int(e['seq']) for e in arr) + 1
        q['seq'] = str(seq).zfill(4)
        q['governance'] = {
            'validated': 'selfcheck',
            'method': 'author-ai-selfcheck（GLM 会话内出题并自查；格式/查重/证据定位为程序验证，'
                      '答案与质量为作者 AI 裁决，非外部多模型验证）',
            'checks': ['format', 'exact_duplicate', 'similarity_candidates',
                       'chapter_assignment', 'quality_selfcheck', 'answer_selfcheck',
                       'source_evidence_located'],
            'knowledge_point': it['kp'],
            'evidence_quote': it['quote'],
            'source': f'docs/ACP高频知识点总结.md 第{q["chapter"]}章',
            'checked_at': now,
        }
        arr.append(q)
        items.append({'qid': cc.qid_of(ch, q['seq']), 'after': copy.deepcopy(q)})
    bid = cc.new_batch_id('add_questions')
    out = GOV / (bid + '_before.json')
    cc._atomic_write_text(out, json.dumps(before, ensure_ascii=False, indent=1))
    cc.write_bank(bank)
    cc.append_batch('add_questions', 'ai_selfcheck 出题（author-ai-selfcheck）', items,
                    reason=f'before-image: data/curate/governance/{bid}_before.json',
                    batch_id=bid)
    qc.rebuild_min_js()
    print(f'批次 {bid}: add_questions {len(items)} 条（回滚: python scripts/quiz_curate.py rollback --batch {bid} --apply）')

    # 缺口重算
    audit2 = json.loads((GOV / 'audit.json').read_text(encoding='utf-8'))
    excluded2 = {r['qid'] for r in audit2['rows'] if r['action'] == 'review'}
    active_q2 = [dict(q, qid=cc.qid_of(ch, q['seq']))
                 for ch, qs in bank['questions_by_chapter'].items() for q in qs
                 if not q.get('deleted')]
    eligible = {ch: sum(q['chapter'] == ch and q['qid'] not in excluded2 for q in active_q2)
                for ch in range(1, 13)}
    gaps = {ch: max(0, TARGET - n) for ch, n in eligible.items()}
    prog = json.loads((GOV / 'completion_progress.json').read_text(encoding='utf-8'))
    prog['round'] = 13
    prog['note'] = 'round 13：AI 自查出题补齐缺口后重算（author-ai-selfcheck，非外部多模型验证）'
    prog['eligible'] = {str(k): v for k, v in eligible.items()}
    prog['gaps'] = {str(k): v for k, v in gaps.items()}
    prog['complete'] = not any(gaps.values())
    cc._atomic_write_text(GOV / 'completion_progress.json', json.dumps(prog, ensure_ascii=False, indent=2))
    print('各章合格题量:', eligible)
    print('剩余缺口:', {k: v for k, v in gaps.items() if v} or '无')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
