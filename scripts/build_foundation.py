"""Offline current-bank checks and small, topic-balanced learning sets.

No model verdicts are invented: keyword matches are selection aids, not answer
verification. Source questions are never modified by this build.
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
import curate_core as cc

# Explicit teaching units; two complementary questions per unit, at most.
TOPICS = {
    1: [('Token 与上下文', r'token|分词|上下文窗口'), ('生成与采样', r'temperature|top.p|采样'), ('注意力机制', r'注意力|attention'), ('能力边界', r'幻觉|知识截止|概率')],
    2: [('提示词结构', r'提示词.*结构|角色|分隔符'), ('样例与推理', r'few.shot|zero.shot|思维链'), ('输出约束', r'JSON|结构化输出'), ('提示词改进', r'迭代|指令冲突|提示.*优化')],
    3: [('检索增强的用途', r'RAG.*核心|RAG.*主要|私域|知识截止'), ('切片与向量化', r'切片|分块|Embedding'), ('检索与重排序', r'Top.K|重排序|Rerank'), ('效果评估', r'忠实|Faithfulness|RAGAS')],
    4: [('智能体闭环', r'ReAct|观察|规划'), ('工具调用', r'Function Calling|工具调用'), ('记忆管理', r'Memory|记忆'), ('协作与协议', r'MCP|多.*Agent')],
    5: [('微调的用途', r'微调.*目的|微调.*主要|SFT'), ('参数高效微调', r'LoRA|QLoRA'), ('训练数据', r'数据.*质量|训练集|验证集'), ('训练稳定性', r'过拟合|学习率|梯度')],
    6: [('量化基础', r'量化|INT8|INT4'), ('推理缓存', r'KV.?Cache|缓存'), ('批处理与吞吐', r'批处理|吞吐|Batch'), ('部署资源', r'显存|并行|延迟')],
    7: [('评测集', r'测试集|评测集|基准'), ('评估指标', r'准确率|召回率|F1|BLEU|ROUGE'), ('人工与模型评审', r'人工|Judge|裁判'), ('评测可靠性', r'偏差|泄漏|一致性')],
    8: [('提示注入', r'提示注入|Prompt Injection'), ('隐私保护', r'隐私|脱敏'), ('内容安全', r'内容安全|有害|审核'), ('权限与防护', r'最小权限|权限|越狱')],
    9: [('请求与鉴权', r'API.Key|鉴权|认证'), ('消息与接口', r'messages|role|接口'), ('流式响应', r'流式|stream|SSE'), ('调用可靠性', r'重试|限流|超时|429')],
    10: [('百炼平台', r'百炼'), ('模型服务', r'DashScope|Model Studio'), ('训练与部署平台', r'PAI|EAS|DLC'), ('数据与应用', r'知识库|OSS|应用')],
    11: [('视觉理解', r'视觉|图像理解|Qwen.VL'), ('语音处理', r'语音|ASR|TTS'), ('视频处理', r'视频|抽帧'), ('多模态输入', r'多模态|图像.*输入')],
    12: [('应用框架', r'LangChain|LlamaIndex'), ('工作流编排', r'LangGraph|工作流|Dify'), ('模型与数据工具', r'Hugging.Face|Transformers|ModelScope'), ('检索与向量工具', r'FAISS|向量|检索')],
}


def fingerprint(q):
    content = {k: q.get(k) for k in ('stem', 'options', 'answer', 'analysis', 'type')}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def inspect(q):
    problems = []
    opts = q.get('options', [])
    labels = [o.get('option_label', '') for o in opts]
    answers = re.findall(r'[A-Z]', str(q.get('answer', '')).upper())
    if not str(q.get('stem', '')).strip() or len(opts) < 2:
        problems.append('题干为空或选项不足')
    if len(set(labels)) != len(labels) or any(not x for x in labels):
        problems.append('选项标签为空或重复')
    if not answers or any(a not in labels for a in answers):
        problems.append('答案为空或指向不存在的选项')
    if q.get('type') == 0 and len(set(answers)) != 1:
        problems.append('单选题答案数量不为一')
    texts = [cc.normalize_space(o.get('option_text')) for o in opts]
    if any(not t for t in texts) or len(set(texts)) != len(texts):
        problems.append('选项文本为空或完全重复')
    if re.search(r'电影py', q.get('stem', '')):
        problems.append('疑似工具名误译，需核对 MoviePy 原名及适用版本')
    if re.search(r'依据教材|根据本章|符合教材|依据原文|违反.*原文', q.get('stem', '')):
        problems.append('题干依赖未附带的教材上下文，需核对来源或改写为独立问题')
    return problems


def build(bank):
    questions = cc.bank_questions(bank)
    findings = defaultdict(list)
    groups = defaultdict(list)
    for q in questions:
        for reason in inspect(q):
            findings[q['qid']].append(reason)
        key = (cc.stem_key(q['stem']), tuple((o['option_label'], cc.normalize_space(o['option_text'])) for o in q['options']))
        groups[key].append(q)
    for group in groups.values():
        if len(group) > 1:
            answers = {tuple(sorted(re.findall(r'[A-Z]', str(q['answer'])))) for q in group}
            for q in group:
                findings[q['qid']].append(('同题异答，必须复核' if len(answers) > 1 else '题干和选项完全重复') + '：' + ', '.join(x['qid'] for x in group if x is not q))
    rows = []
    for q in questions:
        if findings[q['qid']]:
            rows.append({'qid': q['qid'], 'chapter': q['chapter'], 'stem': q['stem'], 'status': 'review', 'reason': '；'.join(findings[q['qid']]), 'fingerprint': fingerprint(q)})
    packs = {}
    for ch, topics in TOPICS.items():
        pool = [q for q in questions if q['chapter'] == ch and not findings[q['qid']] and len(q.get('analysis', '')) >= 20
                and len(q['stem']) <= 100 and not re.search(r'电影py|教材|原文|本章|必须放弃|哪个内置节点', q['stem'])]
        pool.sort(key=lambda q: (len(q['stem']), q.get('difficulty_score', 99), q['qid']))
        used, units = set(), []
        for title, pattern in topics:
            candidates = [q for q in pool if q['qid'] not in used and re.search(pattern, q['stem'], re.I)]
            chosen = candidates[:2]
            used.update(q['qid'] for q in chosen)
            units.append({'title': title, 'reflection': '用自己的话说明“' + title + '”的作用、适用条件，以及一个容易混淆的地方。',
                          'items': [{'qid': q['qid'], 'fingerprint': fingerprint(q), 'stem': q['stem'], 'answer': q['answer'], 'options': q['options'], 'analysis': q['analysis'], 'type': q.get('type')} for q in chosen],
                          'gap': max(0, 2 - len(chosen))})
        packs[str(ch)] = {'title': bank['chapters'][str(ch)], 'units': units, 'count': len(used), 'estimated_minutes': len(used) * 2}
    return rows, packs


def main():
    bank = cc.load_bank()
    rows, packs = build(bank)
    sha = hashlib.sha256(cc.JSON_PATH.read_bytes()).hexdigest()
    meta = {'bank_sha256': sha, 'method': '格式、精确重复、工具名误译和教材上下文依赖线索检查；基础题按教学单元关键词初选，不代表完成答案或章节语义验证。'}
    cc._atomic_write_text(cc.CURATE_DIR / 'current_audit.json', json.dumps({**meta, 'items': rows, 'chapters': packs}, ensure_ascii=False, indent=2))
    # The authored course is built separately; auditing must never overwrite it.
    counts = Counter(q['chapter'] for q in cc.bank_questions(bank))
    lines = ['# 当前题库体检与基础学习改造', '', meta['method'], '', f'当前在用：{sum(counts.values())} 题；规则发现的待复核题：{len(rows)} 题。', '', '| 章 | 在用 | 基础初选 | 预计分钟 | 待补位 |', '|---|---:|---:|---:|---:|']
    for ch, pack in packs.items():
        lines.append(f"| {ch} {pack['title']} | {counts[int(ch)]} | {pack['count']} | {pack['estimated_minutes']} | {sum(u['gap'] for u in pack['units'])} |")
    lines += ['', '## 待复核题', '']
    lines.extend(f"- {r['qid']}：{r['reason']}" for r in rows)
    lines += ['', '## 使用与边界', '', '- 重新生成：`python scripts/build_foundation.py`。原题、答案、学习记录不改写。', '- 章节练习点击「基础学习」：按知识单元作答，答后阅读解析并进行口头自我解释。', '- 治理台「当前体检」支持预览和软删除；删除前需判断是修复还是移除，可通过原有台账恢复。', '- 该体检不检测全部语义错章、荒谬选项或知识性答案错误；历史报告不可直接当作当前题目的有效裁决。', '- 基础题为初选版本，关键词只决定候选归组；教材覆盖与答案仍需逐题核对。缺位明确列出，不用无关题凑数。', '- 基础学习不把一次答对计作知识掌握；完成后仍需自行解释原理和适用条件。', '- 更新题目后请重新生成；前端会跳过题面、选项、答案或解析已经变化的初选记录。', '', f'输入快照 SHA256：`{sha}`', '']
    lines = lines[:lines.index('## 使用与边界')] + [
        '## 使用与边界', '',
        '- 本表为原题库体检和旧题候选分析，不是当前基础学习课程。',
        '- 基础学习已改为每章独立编写30题，见《基础学习30题覆盖表》和《基础学习360题与讲解》。',
        '- 体检重建：`python scripts/build_foundation.py`；原创课程重建：`python scripts/build_foundation_lessons.py`。',
        '- 管理页「当前体检」可查看线索，依据不足不自动删除或改答案。',
        '- 该规则检查不等于全库语义错章与知识性答案验证。', '', f'输入快照 SHA256：`{sha}`', '']
    cc._atomic_write_text(cc.ROOT / 'docs/当前题库体检与基础学习.md', '\n'.join(lines))
    print(json.dumps({'active': sum(counts.values()), 'findings': len(rows), 'foundation': sum(p['count'] for p in packs.values())}, ensure_ascii=False))


if __name__ == '__main__':
    main()
