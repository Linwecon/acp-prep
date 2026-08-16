/* ============================================================
   ACP — Study view (knowledge reader)
   Renders window.KNOWLEDGE_MD (markdown from
   docs/ACP高频知识点总结.md) into a polished reading UI.
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

            // fenced code block
            if (/^```/.test(line.trim())) {
                const buf = [];
                i++;
                while (i < lines.length && !/^```/.test(lines[i].trim())) { buf.push(lines[i]); i++; }
                i++; // skip closing fence
                out.push('<pre><code>' + esc(buf.join('\n')) + '</code></pre>');
                continue;
            }

            // table
            if (/^\s*\|/.test(line)) {
                const buf = [line];
                i++;
                while (i < lines.length && /^\s*\|/.test(lines[i])) { buf.push(lines[i]); i++; }
                out.push(tableHTML(buf));
                continue;
            }

            // blockquote
            if (/^\s*>/.test(line)) {
                const buf = [line];
                i++;
                while (i < lines.length && /^\s*>/.test(lines[i])) { buf.push(lines[i]); i++; }
                out.push(blockquoteHTML(buf));
                continue;
            }

            // list
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

            // heading
            const h = line.match(/^(#{1,4})\s+(.*)$/);
            if (h) {
                const level = h[1].length;
                const id = slugify(h[2]);
                out.push(`<h${level} id="${id}">${inline(h[2])}</h${level}>`);
                i++;
                continue;
            }

            // horizontal rule
            if (/^\s*---+\s*$/.test(line)) { out.push('<hr>'); i++; continue; }

            // paragraph (accumulate until blank line)
            const buf = [];
            while (i < lines.length && lines[i].trim() !== '') { buf.push(lines[i]); i++; }
            if (buf.length) {
                const joined = buf.join('<br>');
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

    /* ---------- study view ---------- */

    let studyClickHandler = null;

    function studyJump(id) {
        const el = document.getElementById(id);
        if (!el) return;
        const content = document.getElementById('content');
        const top = el.getBoundingClientRect().top + content.scrollTop - 96;
        content.scrollTo({ top: Math.max(top, 0), behavior: 'smooth' });
    }

    function studyTop() {
        document.getElementById('content').scrollTo({ top: 0, behavior: 'smooth' });
    }

    function renderStudy(root) {
        ACP.setCrumb('知识点', '高频考点系统复习');
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

        const html = mdToHtml(md);

        // collect chapter-level TOC from <h2>
        const toc = [];
        const re = /<h2 id="([^"]+)">([^<]*)<\/h2>/g;
        let m;
        while ((m = re.exec(html)) !== null) {
            if (m[2] === '目录') continue;
            toc.push({ id: m[1], title: m[2] });
        }

        root.innerHTML = `
      <div class="study">
        <div class="study-sticky">
          <div class="study-progress"><i id="studyProg"></i></div>
          <div class="study-toc">
            <span class="study-toc-label">章节</span>
            ${toc.map(t =>
                `<button class="study-chip" data-target="${t.id}" onclick="ACP.studyJump('${t.id}')">${ACP.esc(t.title)}</button>`
            ).join('')}
          </div>
        </div>
        <div class="study-meta">
          <span class="sm-chip">📚 ${toc.length} 个章节</span>
          <span class="sm-chip">⏱ 已读 <b id="studyPct">0%</b></span>
        </div>
        <article class="study-article card">${html}</article>
        <button class="study-top" id="studyTop" onclick="ACP.studyTop()" title="回到顶部">↑</button>
      </div>`;

        // 给每个 h2 章节标题加上主题图标
        const H2_ICONS = [
            ['易混', '⚖️'], ['应试', '💪'], ['陷阱', '🎯'],
            ['大模型基础', '🧠'], ['提示工程', '✍️'], ['RAG', '🔎'],
            ['Agent', '🤖'], ['微调', '🔧'], ['部署', '🚀'],
            ['评估', '📊'], ['安全', '🛡️'], ['API', '🔌'],
            ['阿里云', '☁️'], ['多模态', '🎨'], ['框架', '🧩'], ['附录', '🎓']
        ];
        root.querySelectorAll('.study-article h2[id]').forEach(h => {
            const txt = h.textContent || '';
            for (const [kw, icon] of H2_ICONS) {
                if (txt.includes(kw)) {
                    h.innerHTML = `<span class="h2-icon">${icon}</span>` + h.innerHTML;
                    break;
                }
            }
        });

        // smooth scroll for in-document anchors (rebind to avoid duplicates)
        if (studyClickHandler) root.removeEventListener('click', studyClickHandler);
        studyClickHandler = e => {
            const a = e.target.closest('a[href^="#"]');
            if (a) {
                e.preventDefault();
                studyJump(decodeURIComponent(a.getAttribute('href').slice(1)));
            }
        };
        root.addEventListener('click', studyClickHandler);

        // scroll progress + scrollspy
        const content = document.getElementById('content');
        const prog = document.getElementById('studyProg');
        const pct = document.getElementById('studyPct');
        const topBtn = document.getElementById('studyTop');
        const heads = root.querySelectorAll('.study-article h2[id]');
        const chips = root.querySelectorAll('.study-chip');

        const sync = () => {
            const sc = content.scrollTop;
            const sh = content.scrollHeight - content.clientHeight;
            const ratio = sh > 0 ? Math.min(100, (sc / sh) * 100) : 0;
            if (prog) prog.style.width = ratio + '%';
            if (pct) pct.textContent = Math.round(ratio) + '%';
            if (topBtn) topBtn.classList.toggle('show', sc > 420);
            let cur = toc.length ? toc[0].id : null;
            heads.forEach(h => {
                if (h.getBoundingClientRect().top - 110 <= 0) cur = h.id;
            });
            chips.forEach(ch => ch.classList.toggle('active', ch.dataset.target === cur));
        };
        content.onscroll = sync;
        sync();
    }

    ACP.mdToHtml = mdToHtml;
    ACP.renderStudy = renderStudy;
    ACP.studyJump = studyJump;
    ACP.studyTop = studyTop;

})(window.ACP);
