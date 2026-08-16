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
        const items = buf.map(l => {
            const m = l.match(/^(\s*)([-*]|\d+\.)\s+(.*)$/);
            return {
                depth: m[1].length >= 2 ? 1 : 0,
                ordered: /^\d+\.$/.test(m[2]),
                text: m[3]
            };
        });
        const tag = items[0].ordered ? 'ol' : 'ul';
        return `<${tag}>` + items.map(it =>
            `<li${it.depth ? ' class="sub"' : ''}>${inline(it.text)}</li>`
        ).join('') + `</${tag}>`;
    }

    function mdToHtml(md) {
        const lines = md.replace(/\r\n/g, '\n').split('\n');
        const out = [];
        let i = 0;

        while (i < lines.length) {
            const line = lines[i];

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

            if (/^\s*[-*]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
                const buf = [line];
                i++;
                while (i < lines.length &&
                    (/^\s*[-*]\s+/.test(lines[i]) || /^\s*\d+\.\s+/.test(lines[i]) || /^\s{2,}[-*]\s+/.test(lines[i]))) {
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
            while (i < lines.length && lines[i].trim() !== '') { buf.push(lines[i]); i++; }
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
                if (h2[1] === '目录') continue;
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

    /* ---------- chapter view (interactive knowledge cards) ---------- */

    function renderChapterView(root, ci) {
        const ch = chapters[ci];
        if (!ch) { chapterMode = null; renderGallery(root); return; }
        ACP.setCrumb(ch.title, `${ch.kps.length} 个知识点`);
        const done = loadDone();
        const st = chapterStats(ch);
        const pct = st.total ? Math.round(st.done / st.total * 100) : 0;

        root.innerHTML = `
      <div class="study">
        <div class="chap-top">
          <button class="back-btn" onclick="ACP.backToGallery()">← 知识宇宙</button>
          <div class="chap-banner ${galleryClass(ci, ch.title)}">
            <span class="cb-icon">${h2IconFor(ch.title)}</span>
            <span class="cb-info">
              <span class="cb-title">${ACP.esc(ch.title)}</span>
              <span class="cb-meta">${ch.kps.length} 个知识点 · 已掌握 ${st.done}</span>
            </span>
            <span class="cb-pct">${pct}%</span>
          </div>
        </div>

        ${ch.html ? `<div class="card chap-intro">${ch.html}</div>` : ''}

        <div class="kp-list">
          ${ch.kps.map((kp, i) => {
            const key = ch.id + '|' + i;
            const isDone = !!done[key];
            return `
            <div class="kp-card card ${isDone ? 'done' : ''}">
              <div class="kp-head">
                <span class="kp-num">${String(i + 1).padStart(2, '0')}</span>
                <span class="kp-title">${ACP.esc(kp.title)}</span>
                <button class="kp-done ${isDone ? 'on' : ''}" data-kp="${key}" title="掌握这个知识点">${isDone ? '✓' : '○'}</button>
              </div>
              <div class="kp-body">${kp.html}</div>
            </div>`;
          }).join('')}
        </div>

        <div class="chap-nav">
          <button class="btn" onclick="ACP.openStudyChapter(${ci - 1})" ${ci === 0 ? 'disabled' : ''}>← 上一章</button>
          <button class="btn" onclick="ACP.backToGallery()">回到知识宇宙</button>
          <button class="btn btn-primary" onclick="ACP.openStudyChapter(${ci + 1})" ${ci === chapters.length - 1 ? 'disabled' : ''}>下一章 →</button>
        </div>
        <button class="study-top" id="studyTop" onclick="ACP.studyTop()" title="回到顶部">↑</button>
      </div>`;

        // 交互化：白话/原理/实战/误区 → 可折叠 <details>
        root.querySelectorAll('.kp-body .plain-block, .kp-body .deep-block, .kp-body .practice-block, .kp-body .pitfall-block').forEach(el => {
            let label = '展开';
            if (el.classList.contains('plain-block')) label = '💬 白话解释';
            else if (el.classList.contains('deep-block')) label = '📚 深入原理';
            else if (el.classList.contains('practice-block')) label = '🎯 实战 / 考试要点';
            else if (el.classList.contains('pitfall-block')) label = '⚠️ 常见误区';
            const details = document.createElement('details');
            const summary = document.createElement('summary');
            summary.textContent = label;
            details.open = true; // 默认展开，可手动收起
            el.parentNode.insertBefore(details, el);
            details.appendChild(summary);
            details.appendChild(el);
        });

        // scroll-to-top button
        const content = document.getElementById('content');
        const topBtn = document.getElementById('studyTop');
        content.onscroll = () => {
            if (topBtn) topBtn.classList.toggle('show', content.scrollTop > 420);
        };
    }

    function openStudyChapter(i) {
        if (i < 0 || i >= chapters.length) return;
        chapterMode = i;
        ACP.renderStudy(document.getElementById('contentInner'));
        document.getElementById('content').scrollTop = 0;
    }

    function backToGallery() {
        chapterMode = null;
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

        // 深链支持：#study?ch=0 直达第 N 章（参数在 hash 内）
        if (chapterMode === null) {
            const m = location.hash.match(/[?&]ch=(\d+)/);
            if (m) chapterMode = Math.min(parseInt(m[1], 10), chapters.length - 1);
        }

        if (studyClickHandler) root.removeEventListener('click', studyClickHandler);
        studyClickHandler = e => {
            const btn = e.target.closest('.kp-done');
            if (btn) {
                const d = loadDone();
                d[btn.dataset.kp] = !d[btn.dataset.kp];
                saveDone(d);
                btn.classList.toggle('on', d[btn.dataset.kp]);
                btn.textContent = d[btn.dataset.kp] ? '✓' : '○';
                btn.closest('.kp-card').classList.toggle('done', d[btn.dataset.kp]);
                // 更新 banner 进度
                const ci = chapterMode;
                if (ci !== null) {
                    const st = chapterStats(chapters[ci]);
                    const pctEl = root.querySelector('.cb-pct');
                    const metaEl = root.querySelector('.cb-meta');
                    if (pctEl) pctEl.textContent = (st.total ? Math.round(st.done / st.total * 100) : 0) + '%';
                    if (metaEl) metaEl.textContent = `${st.total} 个知识点 · 已掌握 ${st.done}`;
                }
                return;
            }
        };
        root.addEventListener('click', studyClickHandler);

        if (chapterMode === null) renderGallery(root);
        else renderChapterView(root, chapterMode);
    }

    ACP.mdToHtml = mdToHtml;
    ACP.renderStudy = renderStudy;
    ACP.openStudyChapter = openStudyChapter;
    ACP.backToGallery = backToGallery;
    ACP.studyTop = studyTop;

})(window.ACP);
