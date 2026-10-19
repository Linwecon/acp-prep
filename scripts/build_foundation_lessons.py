"""Compile 360 independently authored learning prompts, never sample the exam bank."""
from pathlib import Path
import hashlib
import json
import re
import random

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'docs/ACP高频知识点总结.md'
AUTHORING = ROOT / 'data/foundation_authoring'
STAGES = ['概念起步', '原理与辨析', '应用与串联']
REFERENCES = {
    '7': [('RAGAS 指标与版本说明', 'https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/')],
    '8': [('生成式人工智能服务管理暂行办法（第2、17条）', 'https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm'),
          ('生成合成内容标识办法说明', 'https://www.cac.gov.cn/2025-03/14/c_1743654685896173.htm'),
          ('数据跨境流动规定说明', 'https://www.cac.gov.cn/2024-03/22/c_1712776611649184.htm')],
    '10': [('PAI DSW', 'https://www.alibabacloud.com/help/en/pai/create-and-manage-dsw-instances'),
           ('PAI DLC 训练流程', 'https://www.alibabacloud.com/help/en/pai/product-overview/distributed-training-dlc-quickstart')],
    '12': [('LangChain Agent 接口', 'https://reference.langchain.com/python/langchain/agents')],
}


def compile_lessons(directory=AUTHORING, source=SOURCE):
    text = source.read_text(encoding='utf-8')
    chapters = dict(re.findall(r'^## (\d+)\. (.+)$', text, re.M))
    sections = dict(re.findall(r'^### (\d+\.\d+) (.+)$', text, re.M))
    section_lines = {m.group(1): text[:m.start()].count('\n') + 1 for m in re.finditer(r'^### (\d+\.\d+) ', text, re.M)}
    packs, stems = {}, set()
    for ch in range(1, 13):
        lines = [line for line in (directory / f'{ch:02}.txt').read_text(encoding='utf-8').splitlines() if line.strip()]
        if len(lines) != 30:
            raise ValueError(f'第{ch}章需要30题，实际{len(lines)}')
        choice_lines = (directory / f'{ch:02}.choices.txt').read_text(encoding='utf-8').splitlines()
        if len(choice_lines) != 30:
            raise ValueError(f'第{ch}章需要30组选择题选项')
        positions = [i % 4 for i in range(30)]
        random.Random(4096 + ch).shuffle(positions)
        items = []
        for number, line in enumerate(lines, 1):
            fields = line.split('|')
            if len(fields) != 5 or any(not f.strip() for f in fields):
                raise ValueError(f'{ch}-{number}: 需要来源、知识点、题目、答案、讲解五个字段')
            refs, topic, question, answer, explanation = fields
            refs = refs.split(',')
            if any(ref not in sections or not ref.startswith(f'{ch}.') for ref in refs):
                raise ValueError(f'{ch}-{number}: 无效或跨章来源 {refs}')
            if question in stems:
                raise ValueError(f'重复题干: {question}')
            stems.add(question)
            if len(answer) < 2 or len(explanation) < 15:
                raise ValueError(f'{ch}-{number}: 答案或讲解不足')
            parts = choice_lines[number - 1].split('|')
            if len(parts) != 6 or any(not part.strip() for part in parts):
                raise ValueError(f'{ch}-{number}: 需要三个干扰项及各自解析')
            distractors = [{'text': parts[i], 'explanation': parts[i + 1], 'correct': False} for i in range(0, 6, 2)]
            if any(len(o['explanation']) < 10 for o in distractors):
                raise ValueError(f'{ch}-{number}: 干扰项解析不足')
            random.Random(ch * 1000 + number).shuffle(distractors)
            distractors.insert(positions[number-1], {'text': answer, 'explanation': explanation, 'correct': True})
            options = [{'label': chr(65+i), **o} for i, o in enumerate(distractors)]
            if len({o['text'].strip('。') for o in options}) != 4:
                raise ValueError(f'{ch}-{number}: 选项重复')
            items.append({'id': f'foundation-{ch:02}-{number:02}', 'number': number,
                          'stage': (number - 1) // 10, 'topic': topic, 'question': question,
                          'answer': chr(65+positions[number-1]), 'answer_text': answer,
                          'explanation': explanation, 'options': options, 'type': 'single',
                          'revision': hashlib.sha256((line + json.dumps(options, ensure_ascii=False)).encode()).hexdigest()[:16],
                          'sources': [{'section': ref, 'title': sections[ref], 'line': section_lines[ref]} for ref in refs]})
        expected = {s for s in sections if s.startswith(f'{ch}.')}
        covered = {s['section'] for q in items for s in q['sources']}
        if expected - covered:
            raise ValueError(f'第{ch}章未覆盖一级小节：{sorted(expected - covered)}')
        packs[str(ch)] = {'title': chapters[str(ch)], 'count': 30, 'stages': STAGES,
                          'items': items, 'references': [{'title': t, 'url': u} for t, u in REFERENCES.get(str(ch), [])]}
    return {'format': 'authored-choice-v2', 'source': 'docs/ACP高频知识点总结.md',
            'source_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'method': '独立编写的360道单选学习题，每题四项、唯一正确答案；干扰项围绕概念混淆与常见错误，配备逐项解释。',
            'chapters': packs}


def main():
    data = compile_lessons()
    (ROOT / 'data/foundation.js').write_text('window.ACP_FOUNDATION = ' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf-8')
    coverage = ['# 每章30题：基础学习覆盖表', '', '12章共360道独立编写的学习题，未从原题库抽取。', '',
                '每章第1–10题为概念起步，第11–20题为原理与辨析，第21–30题为应用与串联。先选择并提交，再对照答案、原理与逐项辨析。', '',
                '覆盖统计以教材三级标题为单位，表示该节已有对应题，不代表该节每个细节都被穷尽。内容为作者编写并自查，非独立教师审定。题目不进入模拟考试。', '',
                '选择与作答保存在本机当前账号档案，暂不云同步；旧版问答自评记录保留，单选记录使用独立空间。题目变更后旧答案不视为当前题目已完成。', '',
                '重新构建：`python scripts/build_foundation_lessons.py`。原稿：`data/foundation_authoring/01.txt` 至 `12.txt`。', '']
    workbook = ['# 基础学习题与讲解（360题）', '', data['method'], '']
    for ch, pack in data['chapters'].items():
        coverage += [f"## {ch}. {pack['title']}", '', '| 教材小节 | 对应题号 |', '|---|---|']
        refs = {}
        for q in pack['items']:
            for s in q['sources']:
                refs.setdefault((s['section'], s['title']), []).append(str(q['number']))
        for (sec, title), numbers in sorted(refs.items(), key=lambda x: tuple(map(int, x[0][0].split('.')))):
            coverage.append(f"| {sec} {title} | {', '.join(numbers)} |")
        coverage += ['', *[f"- [{r['title']}]({r['url']})" for r in pack['references']], '']
        workbook += [f"## {ch}. {pack['title']}", '']
        for q in pack['items']:
            if (q['number'] - 1) % 10 == 0:
                workbook += [f"### {STAGES[q['stage']]}", '']
            workbook += [f"**{q['number']:02}. {q['topic']}**", '', q['question'], '',
                         *[f"{o['label']}. {o['text']}" for o in q['options']], '',
                         f"正确答案：{q['answer']}", '', f"讲解：{q['answer_text']}{q['explanation']}", '',
                         *[f"- {o['label']}（{'正确' if o['correct'] else '错误'}）：{o['explanation']}" for o in q['options']], '',
                         '对应教材：' + '、'.join(s['section'] for s in q['sources']), '']
    (ROOT / 'docs/基础学习30题覆盖表.md').write_text('\n'.join(coverage), encoding='utf-8')
    (ROOT / 'docs/基础学习360题与讲解.md').write_text('\n'.join(workbook), encoding='utf-8')
    print('Compiled 12 chapters x 30 authored questions = 360; all main subsections mapped.')


if __name__ == '__main__':
    main()
