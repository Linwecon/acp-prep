// 临时：验证 HTML→Markdown 转换后的渲染结果
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');
const read = p => fs.readFileSync(path.join(ROOT, p), 'utf8');

global.window = { ACP: {}, addEventListener: () => {}, location: { hash: '' } };
global.document = { getElementById: () => null, addEventListener: () => {} };
['js/acp.js', 'js/utils.js', 'js/study.js', 'js/notebook.js'].forEach(f =>
    new Function('window', 'document', read(f))(window, document));
const ACP = window.ACP;

const count = (re, s) => (s.match(re) || []).length;
let totalTable = 0, totalQa = 0, leaked = 0, imgs = 0;

// 全部 24 篇正文渲染检查
const files = fs.readdirSync(path.join(ROOT, 'data/notebooks')).filter(f => f.endsWith('.js'));
for (const f of files) {
    eval(read('data/notebooks/' + f));
}
const all = window.NOTEBOOK_CONTENT;
for (const id of Object.keys(all)) {
    const d = all[id];
    for (const b of d.blocks) {
        if (b.t !== 'md') continue;
        const html = ACP.nbBlockHtml(b, 0);
        totalTable += count(/<table>/g, html);
        totalQa += count(/class="tb tb-qa"/g, html);
        imgs += count(/<img /g, html);
        // 源码外泄检测：正文不应出现未渲染的标签文本
        if (/&lt;(?:table|div|td|tr|details|summary|p|ul|li)\b/i.test(html)) leaked++;
        if (/&lt;div style/.test(html)) leaked++;
    }
}
console.log('教程篇数:', Object.keys(all).length);
console.log('渲染出的表格:', totalTable);
console.log('渲染出的自测题折叠块:', totalQa);
console.log('渲染出的图片:', imgs);
console.log('源码外泄的正文块:', leaked);

// 抽样：打印一段折叠块渲染结果
const d = all['c2-2-1'];
for (const b of d.blocks) {
    if (b.t === 'md' && b.md.includes(':::qa')) {
        const html = ACP.nbBlockHtml(b, 0);
        const i = html.indexOf('tb-qa');
        console.log('折叠块渲染样例:', html.slice(Math.max(0, i - 40), i + 160).replace(/\n/g, ' '));
        break;
    }
}
console.log(leaked === 0 ? 'PASS' : 'FAIL');
process.exitCode = leaked === 0 ? 0 : 1;
