# -*- coding: utf-8 -*-
"""应用 manual_decisions.json 的人工裁决：可回滚修复/移章/软删除 + 审计表更新 + 缺口重算。

流程：指纹校验 → 题型/选项修复 → 证据定位校验（引用存在与支持结论分记）→ 统一守卫
→ 答案修正（旧值入 answer_history）→ 软删除 → 移章 → 写库+台账 → 审计表结案 → 缺口重算。

用法:
  python apply_manual_decisions.py --dry-run   # 校验，不写库
  python apply_manual_decisions.py --apply     # 实际应用（写台账、可回滚）
"""
import argparse
import copy
import json
import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import curate_core as cc
import quiz_curate as qc

ROOT = pathlib.Path(__file__).resolve().parent.parent
GOV = ROOT / 'data' / 'curate' / 'governance'
DEC = GOV / 'manual_decisions.json'
AUDIT = GOV / 'audit.json'


def norm_repair(rep: dict) -> dict | None:
    """两种修复形态归一：{field, before, after, reason} 或 {option:{L:text}, repair_reason}。"""
    if not rep:
        return None
    if 'field' in rep:
        return {'field': rep['field'], 'before': rep.get('before'),
                'after': rep.get('after'), 'reason': rep.get('reason', '修复')}
    label, new_text = next(iter(rep['option'].items()))
    return {'field': 'option_label:' + label, 'before': None, 'after': new_text,
            'reason': rep.get('repair_reason', '选项修复')}


def apply_repair(q: dict, rep: dict) -> tuple | None:
    """把单条修复应用到题目，返回 (before_state, after_state) 供台账记录。"""
    field = rep['field']
    if field == 'options':
        before = copy.deepcopy(q.get('options'))
        q['options'] = copy.deepcopy(rep['after'])
        return {'options': before}, {'options': copy.deepcopy(q['options'])}
    if field.startswith('option_label:'):
        label = field.split(':', 1)[1]
        before = copy.deepcopy(q.get('options'))
        for o in q['options']:
            if o['option_label'] == label:
                o['option_text'] = rep['after']
        if before == q['options']:
            return None
        return {'options': before}, {'options': copy.deepcopy(q['options'])}
    before = copy.deepcopy(q.get(field))
    if before == rep['after']:
        return None
    q[field] = copy.deepcopy(rep['after'])
    return {field: before}, {field: copy.deepcopy(q[field])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--apply', action='store_true')
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        print('需要 --dry-run 或 --apply')
        return 1

    dec = json.loads(DEC.read_text(encoding='utf-8'))
    audit = json.loads(AUDIT.read_text(encoding='utf-8'))
    bank = cc.load_bank()
    index = cc.build_index(bank)
    sections = cc.extract_chapter_sections(100000)
    now = datetime.now().isoformat(timespec='seconds')
    reviewer = dec['meta']['reviewer']
    rows_by_qid = {r['qid']: r for r in audit['rows']}
    problems = []

    # ---------- 0. 存在性与指纹校验（与 audit 时点比对） ----------
    all_qids = (list(dec['keeps']) + [m['qid'] for m in dec['moves']]
                + [f['qid'] for f in dec['fixes']] + [d['qid'] for d in dec['deletes']]
                + [r['qid'] for r in dec['repairs']])
    for qid in all_qids:
        if qid not in index:
            problems.append(f'{qid}: 题号不存在')
            continue
        r = rows_by_qid.get(qid)
        if r is None:
            problems.append(f'{qid}: 不在 audit.json 中')
            continue
        if cc.q_fingerprint(index[qid][1]) != r.get('fingerprint'):
            problems.append(f'{qid}: 题目内容与 audit 时点不一致（指纹失配），拒绝自动处理')
    if problems:
        print('[阻断] 发现问题，不执行：')
        for p in problems:
            print(' -', p)
        return 1

    # ---------- 1. 先应用题型/选项修复（守卫须基于修复后的题型校验答案数量） ----------
    print('== 结构修复（题型/选项/题干，先于答案守卫） ==')
    fix_items = []
    for f in dec['fixes']:
        rep = norm_repair(f.get('repair') or {})
        if rep:
            q = index[f['qid']][1]
            states = apply_repair(q, rep)
            if states:
                fix_items.append({'qid': f['qid'], 'before': states[0],
                                  'after': states[1], 'reason': rep['reason']})
                print(f"  [修复] {f['qid']} {rep['field']}")
    for r in dec['repairs']:
        rep = norm_repair(r)
        q = index[r['qid']][1]
        states = apply_repair(q, rep)
        if states:
            fix_items.append({'qid': r['qid'], 'before': states[0],
                              'after': states[1], 'reason': rep['reason']})
            print(f"  [修复] {r['qid']} {rep['field']}")

    # ---------- 2. 证据定位校验 + 统一守卫 ----------
    print('== 证据定位校验与守卫（引用存在 ≠ 支持结论，分别记录） ==')
    fix_entries = []
    for f in dec['fixes']:
        qid = f['qid']
        q = index[qid][1]
        fp = cc.q_fingerprint(q)  # 修复后内容指纹（本次验证绑定当前版本）
        entry = {
            'qid': qid, 'final': f['final'], 'analysis': f.get('analysis'),
            'fingerprint': fp,
            'reason': ('人工裁决（' + reviewer + '）：'
                       + (f.get('manual_reason') or f.get('quote', ''))[:80]),
        }
        if f.get('manual_reason'):
            entry['manual_reason'] = f['manual_reason']
            entry['external_evidence'] = {
                'supported': True, 'quote_found': None, 'mode': 'manual_override',
                'note': '人工裁决覆盖（未经外部证据自动验证，台账记录为人工覆盖）',
                'fingerprint': fp, 'source': f.get('source', 'AI 裁决 + 官方/学科资料'),
            }
        else:
            sec = sections[q['chapter']]['text']
            loc = cc.locate_quote(f['quote'], sec)
            entry['external_evidence'] = {
                'supported': True,            # 人工确认引用支持结论
                'quote_found': loc['quote_found'],  # 程序验证引用逐段存在于原文
                'segments': [{'mode': s['mode'], 'offset': s['offset'],
                              'excerpt': s['excerpt'][:60]} for s in loc['segments']],
                'unmatched': loc['unmatched'], 'quote': f['quote'],
                'source': f.get('source', ''), 'fingerprint': fp,
            }
            if not loc['quote_found']:
                problems.append(f"{qid}: 证据引用无法在原文逐段定位: {loc['unmatched'][:1]}")
        fix_entries.append(entry)
    if problems:
        print('[阻断] 证据问题：')
        for p in problems:
            print(' -', p)
        return 1
    for entry in fix_entries:
        ok, why, info = cc.check_fix_entry(entry, index[entry['qid']][1], allow_manual=True)
        tag = 'MANUAL' if info.get('manual') else 'VERIFIED'
        print(f"  [{tag}] {entry['qid']} -> {','.join(entry['final'])} | {why[:60]}")
        if not ok:
            problems.append(f"{entry['qid']}: 守卫拒绝: {why}")
    if problems:
        print('[阻断] 守卫拒绝：')
        for p in problems:
            print(' -', p)
        return 1

    # ---------- 3. 答案修正（旧值入 answer_history） ----------
    plan = {'keeps': len(dec['keeps']), 'fixes': 0, 'repairs': len(fix_items),
            'deletes': 0, 'moves': 0}
    for entry in fix_entries:
        r = cc.apply_answer_fix(bank, [entry], 'manual_decisions 人工裁决', batch_id='(pending)')
        if r['applied']:
            fix_items.extend(r['ledger_items'])
            plan['fixes'] += 1
        else:
            print('  [答案无变化]', entry['qid'], r['skipped'])

    # ---------- 4. 软删除 ----------
    del_result = cc.soft_delete(
        bank, [{'qid': d['qid'], 'reason': d['reason'][:120]} for d in dec['deletes']],
        source='manual_decisions 人工裁决')
    plan['deletes'] = len(del_result['ledger_items'])

    # ---------- 5. 移章（最后执行：qid 可能随 seq 变化） ----------
    move_result = cc.move_questions(
        bank, [{'qid': m['qid'], 'to': m['to'], 'reason': m['reason'][:120]}
               for m in dec['moves']], qc.CHAPTERS)
    plan['moves'] = len(move_result['ledger_items'])

    print(f"\n计划: keep {plan['keeps']} · fix {plan['fixes']} · 结构修复 {plan['repairs']} · "
          f"delete {plan['deletes']} · move {plan['moves']} · "
          f"review 保留 {len(audit['rows']) - len(all_qids)}")
    if args.dry_run:
        print('[dry-run] 未写库。移章跳过（前5）:',
              [s['qid'] + ':' + s['why'] for s in move_result['skipped'][:5]])
        return 0

    # ---------- 6. 写库 + 台账 ----------
    bid_fix = cc.new_batch_id('answer_fix')
    bid_del = cc.new_batch_id('soft_delete')
    bid_move = cc.new_batch_id('move')
    cc.write_bank(bank)
    for kind, bid, items in [('answer_fix', bid_fix, fix_items),
                             ('soft_delete', bid_del, del_result['ledger_items']),
                             ('move', bid_move, move_result['ledger_items'])]:
        if items:
            cc.append_batch(kind, 'manual_decisions 人工裁决', items, batch_id=bid)
            print(f'批次 {bid}: {kind} {len(items)} 条')
    for s in del_result['skipped'][:5]:
        print('  [删除跳过]', s['qid'], s['why'])
    for s in move_result['skipped'][:5]:
        print('  [移章跳过]', s['qid'], s['why'])

    # ---------- 7. audit.json 结案（待复核行 → 终态，保留裁决人与时间） ----------
    new_qid_of = {li['qid']: f"{li['to']}-{li['after_seq']}"
                  for li in move_result['ledger_items']}
    for qid, reason in dec['keeps'].items():
        rows_by_qid[qid].update(
            action='keep', reason='人工裁决确认：' + reason[:150],
            manual_review={'by': reviewer, 'at': now, 'from': 'review'})
    for m in dec['moves']:
        nq = new_qid_of.get(m['qid'], m['qid'])
        rows_by_qid[m['qid']].update(
            action='keep', qid=nq,
            reason=f"人工裁决移章至第{m['to']}章：" + m['reason'][:120],
            manual_review={'by': reviewer, 'at': now, 'from': 'review',
                           'moved_to': m['to']})
    for f in dec['fixes']:
        rows_by_qid[f['qid']].update(
            action='answer_fix',
            reason='人工裁决修正答案：'
                   + (f.get('analysis') or f.get('manual_reason', ''))[:120],
            manual_review={'by': reviewer, 'at': now, 'from': 'review'})
    for d in dec['deletes']:
        rows_by_qid[d['qid']].update(
            action='remove', reason='人工裁决软删除：' + d['reason'][:150],
            manual_review={'by': reviewer, 'at': now, 'from': 'review'})
    audit['manual_review_round'] = {'at': now, 'reviewer': reviewer, 'decisions': plan}
    cc._atomic_write_text(AUDIT, json.dumps(audit, ensure_ascii=False, indent=2))

    # ---------- 8. 运行时文件 + 缺口重算 ----------
    qc.rebuild_min_js()
    qs = cc.bank_questions(bank)
    excluded = {r['qid'] for r in audit['rows'] if r['action'] == 'review'}
    eligible = {ch: sum(q['chapter'] == ch and cc.qid_of(ch, q['seq']) not in excluded
                        for q in qs) for ch in range(1, 13)}
    gaps = {ch: max(0, 100 - n) for ch, n in eligible.items()}
    cc._atomic_write_text(GOV / 'completion_progress.json', json.dumps({
        'round': 12,
        'note': 'round 12：人工裁决 255 条待复核后重算（复核人：' + reviewer + '）',
        'eligible': {str(k): v for k, v in eligible.items()},
        'gaps': {str(k): v for k, v in gaps.items()},
        'complete': not any(gaps.values()),
    }, ensure_ascii=False, indent=2))
    print('\n各章合格题量:', eligible)
    print('剩余缺口:', {k: v for k, v in gaps.items() if v})
    print(f'总缺口 {sum(gaps.values())}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
