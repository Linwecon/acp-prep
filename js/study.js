/* ============================================================
   ACP — Study view (interactive knowledge universe)
   Gallery (knowledge domains) → Chapter mode (interactive
   knowledge-point cards with collapsible explanations)
   ============================================================ */
(function (ACP) {

    /* ---------- tiny markdown renderer (document subset) ---------- */

    function esc(s) {
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function slugify(s) {
        return s.toLowerCase()
            .replace(/[^\p{L}\p{N}\s-]/gu, ' ')
            .trim()
            .replace(/\s+/g, '-');
    }

    function inline(s) {
        let h = esc(s);
        h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
        h = h.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        h = h.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
        return h;
    }

    function tableHTML(buf) {
        const rows = buf.map(l => {
            let s = l.trim();
            if (s.startsWith('|')) s = s.slice(1);
            if (s.endsWith('|')) s = s.slice(0, -1);
            return s.split(/(?<!\\)\|/).map(c => c.replace(/\\\|/g, '|'));
        });
        let sep = -1;
        for (let r = 1; r < rows.length; r++) {
            if (rows[r].length && rows[r].every(c => /^\s*:?-{2,}:?\s*$/.test(c.trim()))) { sep = r; break; }
        }
        let html = '<div class="tbl-wrap"><table>';
        if (sep >= 0) {
            html += '<thead><tr>' + rows[0].map(c => `<th>${inline(c.trim())}</th>`).join('') + '</tr></thead><tbody>';
            for (let r = sep + 1; r < rows.length; r++) {
                const row = rows[r];
                html += '<tr>' + row.map(c => `<td>${inline(c.trim())}</td>`).join('') + '</tr>';
            }
            html += '</tbody>';
        } else {
            rows.forEach(row => {
                html += '<tr>' + row.map(c => `<td>${inline(c.trim())}</td>`).join('') + '</tr>';
            });
        }
        return html + '</table></div>';
    }

    function blockquoteHTML(buf) {
        const t = buf.map(l => l.replace(/^\s*>\s?/, '')).join(' ');
        let cls = 'study-bq';
        if (t.indexOf('⚠️') >= 0) cls += ' warn';
        else if (t.indexOf('导读') >= 0) cls += ' guide';
        else if (t.indexOf('白话') >= 0) cls += ' plain';
        else if (t.indexOf('💡') >= 0 || t.indexOf('📝') >= 0) cls += ' tip';
        return `<blockquote class="${cls}">${inline(t)}</blockquote>`;
    }

    function listHTML(buf) {
        // 解析每一行
        const items = buf.map(l => {
            const m = l.match(/^(\s*)([-*]|\d+\.|[A-Z]\.)\s+(.*)$/);
            if (!m) return null;
            const marker = m[2];
            const depth = m[1].length >= 2 ? 1 : 0;
            let kind = 'ul';
            if (/^\d+\.$/.test(marker)) kind = 'ol';
            else if (/^[A-Z]\.$/.test(marker)) kind = 'ola';
            return { depth, kind, text: m[3] };
        }).filter(Boolean);

        // 构建两层嵌套列表：顶层 + 缩进子层（子层若为字母则 type=A）
        let html = '';
        let topOpen = false, topLiOpen = false, subOpen = false, subKind = '';
        const closeSub = () => { if (subOpen) { html += '</ol>'; subOpen = false; } };
        const closeTopLi = () => {
            closeSub();
            if (topLiOpen) { html += '</li>'; topLiOpen = false; }
        };
        const closeTop = () => { closeTopLi(); if (topOpen) { html += '</ol>'; topOpen = false; } };

        for (const it of items) {
            if (it.depth === 0) {
                closeTopLi();
                if (!topOpen) { html += '<ol>'; topOpen = true; }
                html += `<li>${inline(it.text)}`;
                topLiOpen = true;
            } else {
                if (!subOpen || subKind !== it.kind) {
                    if (subOpen) html += '</ol>';
                    const attr = it.kind === 'ola' ? ' type="A"' : '';
                    html += `<ol${attr}>`;
                    subOpen = true; subKind = it.kind;
                }
                html += `<li class="sub">${inline(it.text)}</li>`;
            }
        }
        closeTop();
        // 若顶层无序列表（全是 - *），上面逻辑不适用；回退简单渲染
        if (items.length && items.every(x => x.kind === 'ul')) {
            return '<ul>' + items.map(it => `<li${it.depth ? ' class="sub"' : ''}>${inline(it.text)}</li>`).join('') + '</ul>';
        }
        return html;
    }

    /* ---------- textbook component blocks (::: type) ---------- */

    const TB_LABELS = {
        objectives: '🎯 学习目标',
        scenario: '🌍 现实场景',
        problem: '❗ 传统做法的局限',
        value: '✨ 核心价值',
        principle: '⚙️ 工作原理',
        concept: '📌 核心概念',
        best: '✅ 最佳实践',
        cost: '💰 成本与限制',
        risk: '⚠️ 风险与误区',
        exam: '📝 考试重点',
        qa: '❓ 自测题',
        compare: '⚖️ 对比辨析',
        note: '📎 补充说明',
        case: '🏢 案例'
    };

    function containerHTML(type, body) {
        const label = TB_LABELS[type] || '';
        return `<div class="tb tb-${type}">${label ? `<div class="tb-hd">${label}</div>` : ''}<div class="tb-bd">${mdToHtml(body)}</div></div>`;
    }

    function mdToHtml(md) {
        const lines = md.replace(/\r\n/g, '\n').split('\n');
        const out = [];
        let i = 0;

        while (i < lines.length) {
            const line = lines[i];

            // textbook component: ::: type [title]
            const fm = line.trim().match(/^:::(\w+)(?:\s+(.+))?$/);
            if (fm) {
                const buf = [];
                i++;
                while (i < lines.length && !/^:::\s*$/.test(lines[i].trim())) { buf.push(lines[i]); i++; }
                i++;
                out.push(containerHTML(fm[1], buf.join('\n').trim()));
                continue;
            }

            // chart block: ```chart <type>
            const cm = line.trim().match(/^```chart\s+(\w+)/);
            if (cm) {
                const buf = [];
                i++;
                while (i < lines.length && !/^```/.test(lines[i].trim())) { buf.push(lines[i]); i++; }
                i++;
                out.push(chartHTML(cm[1], buf.join('\n').trim()));
                continue;
            }

            if (/^```/.test(line.trim())) {
                const buf = [];
                i++;
                while (i < lines.length && !/^```/.test(lines[i].trim())) { buf.push(lines[i]); i++; }
                i++;
                out.push('<pre><code>' + esc(buf.join('\n')) + '</code></pre>');
                continue;
            }

            if (/^\s*\|/.test(line)) {
                const buf = [line];
                i++;
                while (i < lines.length && /^\s*\|/.test(lines[i])) { buf.push(lines[i]); i++; }
                out.push(tableHTML(buf));
                continue;
            }

            if (/^\s*>/.test(line)) {
                const buf = [line];
                i++;
                while (i < lines.length && /^\s*>/.test(lines[i])) { buf.push(lines[i]); i++; }
                out.push(blockquoteHTML(buf));
                continue;
            }

            if (/^\s*[-*]\s+/.test(line) || /^\s*\d+\.\s+/.test(line) || /^\s*[A-Z]\.\s+/.test(line)) {
                const buf = [line];
                i++;
                // 列表遇空行即终止（标准 Markdown 行为），不跨空行收集
                while (i < lines.length && lines[i].trim() !== '' &&
                    ( /^\s*[-*]\s+/.test(lines[i]) || /^\s*\d+\.\s+/.test(lines[i]) ||
                      /^\s*[A-Z]\.\s+/.test(lines[i]) || /^\s{2,}[-*]\s+/.test(lines[i]) ||
                      /^\s{2,}[A-Z]\.\s+/.test(lines[i]) ) &&
                    !/^\s*\*\*解析/.test(lines[i])) {
                    buf.push(lines[i]); i++;
                }
                out.push(listHTML(buf));
                continue;
            }

            const h = line.match(/^(#{1,4})\s+(.*)$/);
            if (h) {
                const level = h[1].length;
                const id = slugify(h[2]);
                out.push(`<h${level} id="${id}">${inline(h[2])}</h${level}>`);
                i++;
                continue;
            }

            if (/^\s*---+\s*$/.test(line)) { out.push('<hr>'); i++; continue; }

            const buf = [];
            while (i < lines.length && lines[i].trim() !== '') {
                const ln = lines[i];
                // 遇到块级起始行（列表、标题、引用、组件、图表、代码块）则结束段落
                if (/^\s*([-*]|\d+\.|[A-Z]\.)\s+/.test(ln) ||
                    /^#{1,4}\s+/.test(ln) || /^\s*>/.test(ln) ||
                    /^\s*:::/.test(ln) || /^\s*```/.test(ln)) break;
                buf.push(ln); i++;
            }
            if (buf.length) {
                // 段落内换行按 Markdown 语义合并为空格
                const joined = buf.join(' ');
                const first = buf[0].trim();
                let cls = null;
                if (/^\*\*核心概念\*\*/.test(first)) cls = 'core-concept';
                else if (/^\*\*【?白话版】?\*\*/.test(first)) cls = 'plain-block';
                else if (/^\*\*【?深入原理】?\*\*/.test(first)) cls = 'deep-block';
                else if (/^\*\*【?实战\/考试要点】?\*\*/.test(first)) cls = 'practice-block';
                else if (/^\*\*【?常见误区】?\*\*/.test(first)) cls = 'pitfall-block';
                if (cls) out.push(`<div class="${cls}">${inline(joined)}</div>`);
                else out.push(`<p>${inline(joined)}</p>`);
            }
            else i++;
        }
        return out.join('\n');
    }

    /* ---------- charts (SVG/CSS animated) ---------- */

    const CHART_COLORS = ['#6366f1', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444', '#a855f7',
        '#ec4899', '#14b8a6', '#f97316', '#3b82f6', '#84cc16', '#f472b6', '#94a3b8'];

    function chartHTML(type, data) {
        const lines = data.split('\n').map(l => l.trim()).filter(Boolean);
        switch (type) {
            case 'flow': return flowChart(lines);
            case 'pipeline': return pipelineChart(lines);
            case 'bars': return barsChart(lines);
            case 'ring': return ringChart(lines);
            case 'attn': return attnChart(lines);
            case 'matrix': return matrixChart(lines);
            default: return `<p>未知图表类型: ${esc(type)}</p>`;
        }
    }

    function flowChart(steps) {
        const items = steps.map((s, idx) => {
            const label = esc(s.replace(/^\d+[.、]\s*/, ''));
            return `<span class="flow-node" style="animation-delay:${idx * 280}ms"><span class="flow-num">${idx + 1}</span>${label}</span>` +
                (idx < steps.length - 1 ? `<span class="flow-arrow" style="animation-delay:${idx * 280 + 160}ms">→</span>` : '');
        }).join('');
        return `<div class="chart-wrap"><div class="chart-title">流程</div><div class="flow-chart">${items}</div></div>`;
    }

    // pipeline: groups of steps separated by a "--" line.
    // First line (before any "--") is treated as the chart title if it contains "|".
    function pipelineChart(lines) {
        let title = '';
        const groups = [[]];
        for (const l of lines) {
            if (/^--+$/.test(l)) { groups.push([]); continue; }
            if (l.indexOf('|title=') === 0) { title = l.split('=')[1] || ''; continue; }
            groups[groups.length - 1].push(l);
        }
        const phases = ['离 线 建 库', '在 线 问 答'];
        const colors = ['var(--accent-2)', 'var(--accent)'];
        const stages = groups.filter(g => g.length).map((g, gi) => {
            const nodes = g.map((s, idx) => {
                const label = esc(s.replace(/^\d+[.、]\s*/, ''));
                return `<span class="pl-node" style="animation-delay:${gi * 200 + idx * 180}ms">${label}</span>` +
                    (idx < g.length - 1 ? '<span class="pl-arrow">→</span>' : '');
            }).join('');
            return `<div class="pl-phase">
        <div class="pl-phase-tag" style="background:${colors[gi] || 'var(--accent)'}">${phases[gi] || ('阶段' + (gi + 1))}</div>
        <div class="pl-track">${nodes}</div>
      </div>`;
        }).join('<div class="pl-stage-arrow" aria-hidden="true">↓</div>');
        return `<div class="chart-wrap">${title ? `<div class="chart-title">${esc(title)}</div>` : ''}<div class="pipeline-chart">${stages}</div></div>`;
    }

    function barsChart(lines) {
        const pairs = lines.map(l => {
            const [label, val] = l.split('|').map(s => s.trim());
            return { label, val: parseFloat(val) || 0 };
        });
        const max = Math.max(...pairs.map(p => p.val), 1);
        const items = pairs.map((p, idx) => `
        <div class="bar-row">
          <span class="bar-label">${esc(p.label)}</span>
          <span class="bar-track"><i style="width:${Math.round(p.val / max * 100)}%;background:${CHART_COLORS[idx % CHART_COLORS.length]};animation-delay:${idx * 160}ms"></i></span>
          <span class="bar-val">${esc(String(p.val))}</span>
        </div>`).join('');
        return `<div class="chart-wrap"><div class="bars-chart">${items}</div></div>`;
    }

    function ringChart(lines) {
        const pairs = lines.map(l => {
            const [label, val] = l.split('|').map(s => s.trim());
            return { label, val: parseFloat(val) || 0 };
        });
        const total = pairs.reduce((s, p) => s + p.val, 0) || 1;
        const R = 52, C = 2 * Math.PI * R;
        let offset = 0;
        const segs = pairs.map((p, idx) => {
            const len = p.val / total * C;
            const seg = `<circle cx="60" cy="60" r="${R}" fill="none" stroke="${CHART_COLORS[idx % CHART_COLORS.length]}" stroke-width="15" stroke-dasharray="${len.toFixed(2)} ${(C - len).toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}" class="ring-seg" style="animation-delay:${idx * 180}ms"></circle>`;
            offset += len;
            return seg;
        }).join('');
        const legend = pairs.map((p, idx) =>
            `<span class="ring-legend"><i style="background:${CHART_COLORS[idx % CHART_COLORS.length]}"></i>${esc(p.label)} · ${esc(String(p.val))}%</span>`).join('');
        return `<div class="chart-wrap"><div class="ring-chart">
      <svg viewBox="0 0 120 120" class="ring-svg">${segs}</svg>
      <div class="ring-legend-wrap">${legend}</div>
    </div></div>`;
    }

    function attnChart(words) {
        // 示例句："苹果 很 便宜 而且 好吃" —— 第一个 Token 关注其余 Token，
        // 权重数组对应 [很, 便宜, 而且, 好吃]（描述性词语相关性更高）
        const weights = [0.4, 0.85, 0.25, 0.95];
        // 放射状布局：中心"苹果"，右侧目标词纵向扇形分散，连线互不交叉
        const cx = 70, cy = 100, cr = 30;
        const targets = [
            { x: 238, y: 24 },  // 很
            { x: 268, y: 72 },  // 便宜
            { x: 268, y: 128 }, // 而且
            { x: 238, y: 176 }  // 好吃
        ];
        const W = 500, H = 200;

        const lines = words.slice(1).map((_, j) => {
            const w = weights[j] || 0.5;
            const t = targets[j];
            const dx = t.x - cx, dy = t.y - cy;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            // 从"苹果"圆边缘出发、到目标词圆边缘结束（不穿过圆）
            const sx = cx + dx / dist * (cr + 4), sy = cy + dy / dist * (cr + 4);
            const ex = t.x - dx / dist * 25, ey = t.y - dy / dist * 25;
            const sw = 1.6 + w * 3.4;
            const op = 0.4 + w * 0.55;
            return `<line x1="${sx.toFixed(1)}" y1="${sy.toFixed(1)}" x2="${ex.toFixed(1)}" y2="${ey.toFixed(1)}"
              class="attn-curve" style="stroke-width:${sw.toFixed(2)};opacity:${op.toFixed(2)};animation-delay:${j * 170}ms"/>`;
        }).join('');

        const center = `<g class="attn-node focus">
          <circle class="attn-pulse" cx="${cx}" cy="${cy}" r="${cr}"/>
          <text x="${cx}" y="${cy}" text-anchor="middle" dominant-baseline="central">${esc(words[0])}</text>
        </g>`;
        const outers = words.slice(1).map((wd, j) => {
            const t = targets[j];
            return `<g class="attn-node" style="animation-delay:${(j + 1) * 140}ms">
              <circle cx="${t.x}" cy="${t.y}" r="24"/>
              <text x="${t.x}" y="${t.y}" text-anchor="middle" dominant-baseline="central">${esc(wd)}</text>
            </g>`;
        }).join('');

        return `<div class="chart-wrap">
      <div class="attn-title">自注意力：每个 Token 都在关注句中所有其他 Token</div>
      <div class="attn-scroll">
        <svg viewBox="0 0 ${W} ${H}" width="100%" class="attn-svg" role="img" aria-label="自注意力示意图">
          <defs>
            <linearGradient id="attnFocus" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stop-color="var(--accent)"/>
              <stop offset="1" stop-color="var(--accent-2)"/>
            </linearGradient>
          </defs>
          ${lines}
          ${center}
          ${outers}
        </svg>
      </div>
      <div class="chart-note">线越粗越亮 = 关注度越高："好吃""便宜"直接描述苹果，权重最高；"很""而且"为功能词，权重较低</div>
    </div>`;
    }

    function matrixChart(lines) {
        const parts = (lines[0] || 'W | B | A').split('|').map(s => s.trim());
        const [w, b, a] = parts.length >= 3 ? parts : ['W', 'B', 'A'];
        return `<div class="chart-wrap"><div class="matrix-chart">
      <span class="mx-block mx-b">${esc(b)}</span>
      <span class="mx-op">×</span>
      <span class="mx-block mx-a">${esc(a)}</span>
      <span class="mx-op">=</span>
      <span class="mx-block mx-w">${esc(w)}</span>
    </div><div class="chart-note">ΔW = B × A：低秩分解使可训练参数量骤降（冻结的 W₀ 不产生梯度）</div></div>`;
    }

    /* ---------- structured parsing: chapters → knowledge points ---------- */

    function parseDoc(md) {
        const lines = md.replace(/\r\n/g, '\n').split('\n');
        const chapters = [];
        let curCh = null, curKp = null;
        for (const line of lines) {
            const h2 = line.match(/^##\s+(.*)$/);
            const h3 = line.match(/^###\s+(.*)$/);
            if (h2) {
                if (h2[1] === '目录' || h2[1] === '如何使用本手册') continue;
                curCh = { id: slugify(h2[1]), title: h2[1], intro: [], kps: [] };
                chapters.push(curCh);
                curKp = null;
                continue;
            }
            if (!curCh) continue;
            if (h3) {
                curKp = { title: h3[1], md: [] };
                curCh.kps.push(curKp);
                continue;
            }
            if (curKp) curKp.md.push(line);
            else curCh.intro.push(line);
        }
        chapters.forEach(ch => {
            ch.html = ch.intro.length ? mdToHtml(ch.intro.join('\n')) : '';
            ch.kps.forEach(kp => { kp.html = mdToHtml(kp.md.join('\n')); });
        });
        return chapters;
    }

    /* ---------- study view ---------- */

    let studyClickHandler = null;
    let chapters = [];          // parsed knowledge structure
    let chapterMode = null;     // current chapter index (null = gallery)
    const DONE_KEY = 'acp_kp_done';

    function loadDone() {
        try { return JSON.parse(localStorage.getItem(DONE_KEY) || '{}'); }
        catch (e) { return {}; }
    }
    function saveDone(d) {
        try { localStorage.setItem(DONE_KEY, JSON.stringify(d)); } catch (e) {}
    }

    const STUDY_KEY = 'acp_study_course_v1';
    function loadStudy() {
        try { return JSON.parse(localStorage.getItem(STUDY_KEY) || '{}'); } catch (e) { return {}; }
    }
    function saveStudy(d) {
        try { localStorage.setItem(STUDY_KEY, JSON.stringify(d)); } catch (e) {}
    }

    const RELATED_RULES = [
        { kw: 'Embedding', title: 'RAG 检索增强生成' },
        { kw: '向量化', title: 'RAG 检索增强生成' },
        { kw: '向量数据库', title: 'RAG 检索增强生成' },
        { kw: 'RAG', title: 'RAG 检索增强生成' },
        { kw: 'RAGAS', title: '模型评估' },
        { kw: 'BLEU', title: '模型评估' },
        { kw: 'ROUGE', title: '模型评估' },
        { kw: 'Function Calling', title: 'Agent 智能体' },
        { kw: '工具调用', title: 'Agent 智能体' },
        { kw: 'MCP', title: 'Agent 智能体' },
        { kw: 'LoRA', title: '模型微调与训练' },
        { kw: '微调', title: '模型微调与训练' },
        { kw: 'RLHF', title: '模型微调与训练' },
        { kw: 'vLLM', title: '模型部署与推理优化' },
        { kw: '量化', title: '模型部署与推理优化' },
        { kw: '部署', title: '模型部署与推理优化' },
        { kw: 'RAM', title: 'AI 安全与合规' },
        { kw: '安全组', title: 'AI 安全与合规' },
        { kw: 'WAF', title: 'AI 安全与合规' },
        { kw: 'DDoS', title: 'AI 安全与合规' },
        { kw: '备案', title: 'AI 安全与合规' },
        { kw: '百炼', title: '阿里云 AI 平台' },
        { kw: 'DashScope', title: '阿里云 AI 平台' },
        { kw: 'PAI', title: '阿里云 AI 平台' },
        { kw: 'Assistant API', title: 'Agent 智能体' },
        { kw: 'LangChain', title: '框架与工具' },
        { kw: 'LlamaIndex', title: '框架与工具' },
        { kw: 'Dify', title: '框架与工具' },
        { kw: 'CosyVoice', title: '多模态 AI' },
        { kw: 'TTS', title: '多模态 AI' },
        { kw: 'ASR', title: '多模态 AI' },
        { kw: '多模态', title: '多模态 AI' }
    ];

    function findChapterByTitle(title) {
        return chapters.findIndex(ch => ch.title === title || ch.title.includes(title));
    }

    function relatedChapters(kpText, currentIdx) {
        const out = [];
        const seen = new Set();
        for (const rule of RELATED_RULES) {
            if (kpText.includes(rule.kw)) {
                const idx = findChapterByTitle(rule.title);
                if (idx >= 0 && idx !== currentIdx && !seen.has(idx)) {
                    seen.add(idx);
                    out.push(idx);
                }
            }
            if (out.length >= 4) break;
        }
        return out;
    }

    function moduleTag(kp) {
        const t = kp.title + ' ' + (kp.md || []).join(' ');
        if (/误区|陷阱|易错|注意|风险|安全/.test(t)) return 'warning';
        if (/流程|链路|步骤|架构|工作模式|运行机制|工作流/.test(t)) return 'flow';
        if (/对比|区别|选型|方案|vs|差异|比较/.test(t)) return 'compare';
        if (/案例|场景|实战|实践|应用|示例|行业/.test(t)) return 'example';
        if (/评估|指标|RAGAS|评测|考试|考点/.test(t)) return 'exam';
        if (/原理|深入|数学|机制|本质|为什么/.test(t)) return 'detail';
        return 'core';
    }

    const MODULE_TAG_LABEL = {
        core: '核心', detail: '深入', exam: '考试', example: '案例',
        warning: '易错', flow: '流程', compare: '对比'
    };

    function estimateMinutes(ch) {
        return Math.max(6, Math.round(ch.kps.length * 4));
    }

    const H2_ICONS = [
        ['易混', '⚖️'], ['应试', '💪'], ['陷阱', '🎯'],
        ['大模型基础', '🧠'], ['提示工程', '✍️'], ['RAG', '🔎'],
        ['Agent', '🤖'], ['微调', '🔧'], ['部署', '🚀'],
        ['评估', '📊'], ['安全', '🛡️'], ['API', '🔌'],
        ['阿里云', '☁️'], ['多模态', '🎨'], ['框架', '🧩'], ['附录', '🎓']
    ];

    function h2IconFor(title) {
        for (const [kw, icon] of H2_ICONS) {
            if (title.includes(kw)) return icon;
        }
        return '📖';
    }

    function galleryClass(idx, title) {
        if (title.includes('附录')) return 'gk-appendix';
        return 'gk-' + (idx + 1);
    }

    /* 画廊页"官方大纲占比"环形图（数据与模拟考试抽题一致） */
    function outlineRing() {
        const doms = ACP.EXAM_DOMAINS || [];
        if (!doms.length) return '';
        const pairs = doms.map(d => ({ label: d.name, val: d.pct }));
        const total = pairs.reduce((s, p) => s + p.val, 0) || 1;
        const R = 52, C = 2 * Math.PI * R;
        let offset = 0;
        const segs = pairs.map((p, idx) => {
            const len = p.val / total * C;
            const seg = `<circle cx="60" cy="60" r="${R}" fill="none" stroke="${CHART_COLORS[idx % CHART_COLORS.length]}" stroke-width="15" stroke-dasharray="${len.toFixed(2)} ${(C - len).toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}" class="ring-seg" style="animation-delay:${idx * 180}ms"></circle>`;
            offset += len;
            return seg;
        }).join('');
        const legend = pairs.map((p, idx) =>
            `<span class="ring-legend"><i style="background:${CHART_COLORS[idx % CHART_COLORS.length]}"></i>${ACP.esc(p.label)} · ${p.val}%</span>`).join('');
        return `<div class="chart-wrap"><div class="ring-chart">
      <svg viewBox="0 0 120 120" class="ring-svg">${segs}</svg>
      <div class="ring-legend-wrap">${legend}</div>
    </div></div>`;
    }

    function chapterStats(ch) {
        const done = loadDone();
        let n = 0;
        ch.kps.forEach((kp, i) => { if (done[ch.id + '|' + i]) n++; });
        return { done: n, total: ch.kps.length };
    }

    function totalStats() {
        const done = loadDone();
        let n = 0, total = 0;
        chapters.forEach((ch, ci) => {
            ch.kps.forEach((kp, i) => {
                total++;
                if (done[ch.id + '|' + i]) n++;
            });
        });
        return { done: n, total };
    }

    /* ---------- gallery view ---------- */

    function renderGallery(root) {
        ACP.setCrumb('知识点', '互动学习 · 知识宇宙');
        const s = totalStats();
        const pct = s.total ? Math.round(s.done / s.total * 100) : 0;

        root.innerHTML = `
      <div class="study">
        <div class="study-hero">
          <div class="sh-head">
            <span class="sh-title">✦ 知识宇宙</span>
            <span class="sh-sub">${s.total} 个知识点 · 官方大纲考点全覆盖 · 点击知识域开始闯关</span>
          </div>
          <div class="sh-progress">
            <div class="sh-track"><i style="width:${pct}%"></i></div>
            <span class="sh-num">已掌握 <b>${s.done}</b> / ${s.total} 个知识点</span>
          </div>
        </div>
        <div class="study-outline">
          <div class="ol-title">官方大纲考点占比</div>
          ${outlineRing()}
        </div>
        <div class="study-gallery">
          ${chapters.map((ch, i) => {
            const st = chapterStats(ch);
            return `
            <button class="gallery-card ${galleryClass(i, ch.title)}" data-ch="${i}"
                    style="animation-delay:${i * 40}ms"
                    onclick="ACP.openStudyChapter(${i})">
              <span class="gk-icon">${h2IconFor(ch.title)}</span>
              <span class="gk-name">${ACP.esc(ch.title)}</span>
              <span class="gk-meta">${st.total ? `已掌握 ${st.done}/${st.total} · 进入闯关 →` : '进入学习 →'}</span>
            </button>`;
          }).join('')}
        </div>
      </div>`;
    }

    /* ---------- 课程化章节视图（三栏课程布局） ---------- */

    function courseNavHTML(ci) {
        return chapters.map((c, i) => {
            const st = chapterStats(c);
            const pct = st.total ? Math.round(st.done / st.total * 100) : 0;
            return `
        <button class="lx-ch-btn ${i === ci ? 'active' : ''}" data-ci="${i}" onclick="ACP.openStudyChapter(${i})">
          <span class="lx-ch-ico">${h2IconFor(c.title)}</span>
          <span class="lx-ch-txt">
            <span class="lx-ch-name">${ACP.esc(c.title)}</span>
            <span class="lx-ch-meta"><i style="width:${pct}%"></i>${st.done}/${st.total}</span>
          </span>
        </button>`;
        }).join('');
    }

    function relatedHTML(relIdxs, currentIdx) {
        if (!relIdxs.length) return '<p class="lx-muted">本章暂无关联章节推荐。</p>';
        return relIdxs.map(i => {
            const c = chapters[i];
            const st = chapterStats(c);
            return `
        <button class="lx-rel" onclick="ACP.openStudyChapter(${i})">
          <span>${h2IconFor(c.title)}</span>
          <em>${ACP.esc(c.title)}</em>
          <small>${st.done}/${st.total}</small>
        </button>`;
        }).join('');
    }

    function nextUnfinished(ch, done) {
        for (let i = 0; i < ch.kps.length; i++) {
            if (!done[ch.id + '|' + i]) return i;
        }
        return -1;
    }

    // 从章节 intro 中提取纯文本摘要供 hero 显示（去除 Markdown 标记）
    function heroSummary(ch) {
        const raw = (ch.intro || []).join(' ');
        let txt = raw
            .replace(/<!--[\s\S]*?-->/g, '')
            .replace(/^>\s?/gm, '')
            .replace(/\*\*([^*]+)\*\*/g, '$1')
            .replace(/`([^`]+)`/g, '$1')
            .replace(/^[-*]\s+/gm, '')
            .replace(/^#{1,6}\s+/gm, '')
            .replace(/:::\w+.*$/gm, '')
            .replace(/:::/g, '')
            .replace(/\|/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
        // 优先取"本章要解决的问题"那句
        const m = txt.match(/本章要解决的问题["」：:]?\s*([^。]*。?)/);
        if (m) txt = m[1];
        return txt.slice(0, 140) || '本章知识点课程';
    }

    function renderCourseView(root, ci) {
        const ch = chapters[ci];
        if (!ch) { chapterMode = null; renderGallery(root); return; }
        const study = loadStudy();
        const mode = study.mode || 'deep';
        const done = loadDone();
        const st = chapterStats(ch);
        const pct = st.total ? Math.round(st.done / st.total * 100) : 0;
        const est = estimateMinutes(ch);
        const isTextbook = /class="tb /.test(ch.html) || ch.kps.some(kp => /class="tb /.test(kp.html));

        ACP.setCrumb(ch.title, `课程模式 · ${st.done}/${st.total}`);

        root.innerHTML = `
      <div class="lx-course ${mode === 'exam' ? 'exam-mode' : ''} ${isTextbook ? 'lx-textbook' : ''}">
        <main class="lx-main-col">
          <header class="lx-hero ${galleryClass(ci, ch.title)}">
            <div class="lx-hero-top">
              <button class="lx-back" onclick="ACP.backToGallery()">← 知识宇宙</button>
              <div class="lx-mode">
                <button class="lx-mode-btn ${mode === 'deep' ? 'active' : ''}" data-mode="deep">深度学习</button>
                <button class="lx-mode-btn ${mode === 'exam' ? 'active' : ''}" data-mode="exam">考前速记</button>
              </div>
            </div>
            <div class="lx-hero-body">
              <span class="lx-hero-ico">${h2IconFor(ch.title)}</span>
              <div class="lx-hero-info">
                <h1>${ACP.esc(ch.title)}</h1>
                <p>${ACP.esc(heroSummary(ch))}</p>
                <div class="lx-hero-meta">
                  <span>📚 ${ch.kps.length} 个知识模块</span>
                  <span>⏱ 约 ${est} 分钟</span>
                  <span>📊 进度 ${st.done}/${st.total}</span>
                </div>
              </div>
              <div class="lx-hero-ring" style="--pct:${pct}">
                <span>${pct}%</span>
              </div>
            </div>
            <div class="lx-progress"><i style="width:${pct}%"></i></div>
          </header>

          ${ch.html ? `<section class="lx-chapter-intro">${ch.html}</section>` : ''}

          <div class="lx-module-list">
            ${ch.kps.map((kp, i) => {
                const key = ch.id + '|' + i;
                const isDone = !!done[key];
                const tag = moduleTag(kp);
                return `
            <article class="lx-module ${tag} ${isDone ? 'done' : ''}" id="lx-m-${i}" data-tag="${tag}">
              <header class="lx-module-head">
                <span class="lx-module-num">${String(i + 1).padStart(2, '0')}</span>
                <div class="lx-module-title">
                  <span class="lx-tag tag-${tag}">${MODULE_TAG_LABEL[tag] || '核心'}</span>
                  <h2>${ACP.esc(kp.title)}</h2>
                </div>
                <button class="lx-kp-done ${isDone ? 'on' : ''}" data-kp="${key}" title="标记为已掌握">${isDone ? '✓ 已掌握' : '标记掌握'}</button>
              </header>
              <div class="lx-module-body">${kp.html}</div>
              <footer class="lx-module-rel">
                <span>相关：</span>
                ${relatedHTML(relatedChapters(kp.title + ' ' + (kp.md || []).join(' '), ci), ci)}
              </footer>
            </article>`;
            }).join('')}
          </div>

          <nav class="lx-bottom-nav">
            <button class="btn" onclick="ACP.openStudyChapter(${ci - 1})" ${ci === 0 ? 'disabled' : ''}>← 上一章</button>
            <button class="btn" onclick="ACP.backToGallery()">章节目录</button>
            <button class="btn btn-primary" onclick="ACP.openStudyChapter(${ci + 1})" ${ci === chapters.length - 1 ? 'disabled' : ''}>下一章 →</button>
          </nav>
        </main>
      </div>`;

        enhanceCourse(root, ch, mode);
    }

    function enhanceCourse(root, ch, mode) {
        // 折叠深入内容
        root.querySelectorAll('.lx-module-body .plain-block, .lx-module-body .deep-block, .lx-module-body .practice-block, .lx-module-body .pitfall-block').forEach(el => {
            let label = '展开';
            let cls = '';
            if (el.classList.contains('plain-block')) { label = '💬 白话解释'; cls = 'plain'; }
            else if (el.classList.contains('deep-block')) { label = '📚 深入原理'; cls = 'deep'; }
            else if (el.classList.contains('practice-block')) { label = '🎯 实战 / 考试要点'; cls = 'practice'; }
            else if (el.classList.contains('pitfall-block')) { label = '⚠️ 常见误区'; cls = 'pitfall'; }
            const details = document.createElement('details');
            details.className = 'lx-fold ' + cls;
            const summary = document.createElement('summary');
            summary.textContent = label;
            details.open = mode !== 'exam';
            if (mode === 'exam') details.open = cls === 'practice' || cls === 'pitfall';
            el.parentNode.insertBefore(details, el);
            details.appendChild(summary);
            details.appendChild(el);
        });

        // 代码块加复制按钮
        root.querySelectorAll('.lx-module-body pre').forEach(pre => {
            const wrap = document.createElement('div');
            wrap.className = 'lx-code';
            const btn = document.createElement('button');
            btn.className = 'lx-copy';
            btn.textContent = '复制';
            btn.type = 'button';
            btn.addEventListener('click', () => {
                const text = pre.innerText || '';
                navigator.clipboard && navigator.clipboard.writeText(text);
                btn.textContent = '已复制';
                setTimeout(() => { btn.textContent = '复制'; }, 1500);
            });
            pre.parentNode.insertBefore(wrap, pre);
            wrap.appendChild(pre);
            wrap.appendChild(btn);
        });

        // 表格移动端卡片化
        root.querySelectorAll('.lx-module-body table').forEach(table => {
            const headers = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
            table.querySelectorAll('tbody tr').forEach(tr => {
                tr.querySelectorAll('td').forEach((td, i) => {
                    if (headers[i]) td.setAttribute('data-label', headers[i]);
                });
            });
        });

        // 模块进入视口时记录最近阅读位置
        const content = document.getElementById('content');
        content.onscroll = () => {
            const topBtn = document.getElementById('studyTop');
            if (topBtn) topBtn.classList.toggle('show', content.scrollTop > 420);
        };
    }

    function openStudyChapter(i) {
        if (i < 0 || i >= chapters.length) return;
        chapterMode = i;
        try { history.pushState(null, '', '#study?ch=' + i); } catch (e) {}
        ACP.renderStudy(document.getElementById('contentInner'));
        document.getElementById('content').scrollTop = 0;
    }

    function backToGallery() {
        chapterMode = null;
        try { history.pushState(null, '', '#study'); } catch (e) {}
        ACP.renderStudy(document.getElementById('contentInner'));
        document.getElementById('content').scrollTop = 0;
    }

    function studyTop() {
        document.getElementById('content').scrollTo({ top: 0, behavior: 'smooth' });
    }

    function renderStudy(root) {
        const md = window.KNOWLEDGE_MD || '';
        if (!md) {
            root.innerHTML = `
        <div class="empty-state">
          <div class="icon">📚</div>
          <h3>知识点内容未加载</h3>
          <p>请运行 <code>python scripts/build_knowledge.py</code> 生成 <code>data/knowledge.js</code></p>
        </div>`;
            return;
        }
        if (!chapters.length) chapters = parseDoc(md);

        if (chapterMode === null) {
            const m = location.hash.match(/[?&]ch=(\d+)/);
            if (m) chapterMode = Math.min(parseInt(m[1], 10), chapters.length - 1);
        }

        if (studyClickHandler) root.removeEventListener('click', studyClickHandler);
        studyClickHandler = e => {
            const kpBtn = e.target.closest('.lx-kp-done');
            if (kpBtn) {
                const d = loadDone();
                d[kpBtn.dataset.kp] = !d[kpBtn.dataset.kp];
                saveDone(d);
                kpBtn.classList.toggle('on', d[kpBtn.dataset.kp]);
                kpBtn.textContent = d[kpBtn.dataset.kp] ? '✓ 已掌握' : '标记掌握';
                kpBtn.closest('.lx-module').classList.toggle('done', d[kpBtn.dataset.kp]);
                const ci = chapterMode;
                if (ci !== null) {
                    const st = chapterStats(chapters[ci]);
                    const pct = st.total ? Math.round(st.done / st.total * 100) : 0;
                    root.querySelectorAll('.lx-progress > i').forEach(el => { el.style.width = pct + '%'; });
                    root.querySelectorAll('.lx-progress-ring').forEach(el => { el.style.setProperty('--pct', pct); el.querySelector('span').textContent = `${st.done}/${st.total}`; });
                    const heroRing = root.querySelector('.lx-hero-ring');
                    if (heroRing) { heroRing.style.setProperty('--pct', pct); heroRing.querySelector('span').textContent = pct + '%'; }
                }
                return;
            }

            const modeBtn = e.target.closest('.lx-mode-btn, .lx-mode-btn-sm');
            if (modeBtn) {
                const d = loadStudy();
                d.mode = modeBtn.dataset.mode;
                saveStudy(d);
                renderCourseView(root, chapterMode);
                return;
            }
        };
        root.addEventListener('click', studyClickHandler);

        window.removeEventListener('popstate', studyPopHandler);
        window.addEventListener('popstate', studyPopHandler);

        if (chapterMode === null) renderGallery(root);
        else renderCourseView(root, chapterMode);
    }

    function studyPopHandler() {
        const m = location.hash.match(/[?&]ch=(\d+)/);
        if (m) {
            chapterMode = Math.min(parseInt(m[1], 10), chapters.length - 1);
        } else if (location.hash.startsWith('#study')) {
            chapterMode = null;
        }
        ACP.renderStudy(document.getElementById('contentInner'));
        document.getElementById('content').scrollTop = 0;
    }

    ACP.mdToHtml = mdToHtml;
    ACP.renderStudy = renderStudy;
    ACP.openStudyChapter = openStudyChapter;
    ACP.backToGallery = backToGallery;
    ACP.studyTop = studyTop;

})(window.ACP);
