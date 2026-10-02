// 官方实战教程模块冒烟测试：node scripts/test_notebook_render.js
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');
const read = p => fs.readFileSync(path.join(ROOT, p), 'utf8');

// 1. 最小浏览器环境
global.window = { ACP: {}, addEventListener: () => {}, location: { hash: '' } };
global.document = { getElementById: () => null, addEventListener: () => {} };

// 2. 依次加载依赖模块（utils → study 提供 mdToHtml → notebook）
//    注意：js/acp.js 会整体重新赋值 window.ACP，因此 ACP 引用须在加载后取得
new Function('window', 'document', read('js/acp.js'))(window, document);
new Function('window', 'document', read('js/utils.js'))(window, document);
new Function('window', 'document', read('js/study.js'))(window, document);

// 3. 教程数据（索引 + 一篇正文）
eval(read('data/notebooks.js'));
const slug = window.NOTEBOOK_INDEX.chapters[1].items[1].id;
eval(read('data/notebooks/' + slug + '.js'));

new Function('window', 'document', read('js/notebook.js'))(window, document);

const ACP = window.ACP;
const fails = [];
const ok = (cond, msg) => { if (!cond) fails.push(msg); };
const has = (s, sub) => s.indexOf(sub) >= 0;

// ---- 代码高亮 ----
const hl = ACP.nbHighlight('def f(x):\n    return "a<b>c"  # 注释\n!pip install x');
ok(has(hl, 'tok-k'), '高亮缺少关键字 span');
ok(has(hl, 'tok-s'), '高亮缺少字符串 span');
ok(has(hl, 'tok-c'), '高亮缺少注释 span');
ok(has(hl, 'tok-sh'), '高亮缺少 shell 行 span');
ok(!has(hl, '<b>'), '高亮未转义 HTML 标签');
ok(has(hl, '&lt;b&gt;'), '高亮应转义为实体');
ok(!/<span class="tok-k">[^<]*<span/.test(hl), '高亮出现嵌套破坏（二次替换）');

// ---- 单元渲染 ----
const mdBlock = ACP.nbBlockHtml({ t: 'md', md: '# 标题\n## 二级\n正文' }, 7);
ok(has(mdBlock, 'id="nb-h-7-0"'), 'Markdown 标题缺少锚点 id');
ok(has(mdBlock, 'id="nb-h-7-1"'), '第二个标题缺少锚点 id');
ok(has(mdBlock, 'id="nb-b-7"'), '单元缺少块 id');

const codeBlock = ACP.nbBlockHtml({
    t: 'code', src: 'print("hi")', exec: 3,
    outs: [{ t: 'out', kind: 'stream', text: 'hi' }, { t: 'img', src: 'assets/x.png' }]
}, 2);
ok(has(codeBlock, 'lx-copy'), '代码块缺少复制按钮');
ok(has(codeBlock, '<pre><code>'), '代码块结构异常');
ok(has(codeBlock, '运行输出'), '缺少运行输出区');
ok(has(codeBlock, 'assets/x.png'), '缺少图片输出');
ok(has(codeBlock, '执行 #3'), '缺少执行序号');
// 复制按钮位于 lx-code 内（教材终端风格标题栏右侧）
ok(/<div class="lx-code">[\s\S]*lx-copy[\s\S]*<\/div>/.test(codeBlock), '复制按钮应在代码框标题栏内');
ok(has(codeBlock, 'nb-code-head'), '缺少代码标签行');

// ---- 目录 ----
const toc = ACP.nbTocHtml([{ lvl: 1, text: '一', b: 0, h: 0 }, { lvl: 2, text: '二', b: 4, h: 1 }]);
ok(has(toc, 'data-b="4"') && has(toc, 'data-h="1"'), '目录项缺少定位属性');
ok(has(toc, 'lvl2'), '目录项缺少层级样式');
ok(has(ACP.nbTocHtml([]), 'nb-toc-empty'), '空目录未给提示');

// ---- 列表行（横框，一行一篇，不放难度徽标） ----
const row = ACP.nbRowHtml({ id: 'x', title: '标题', desc: '简介', difficulty: '进阶', order: '2-3', minutes: 30, cells: 10, code: 4, outs: 2, blocks: 10 }, { d: 1, b: 3 });
ok(has(row, 'nb-row'), '列表行缺少 nb-row 结构');
ok(has(row, '2.3'), '列表行缺少顺序编号');
ok(!has(row, 'nb-diff'), '列表行不应显示难度徽标');
ok(has(row, '约 30 分钟'), '列表行缺少预计时长');
ok(has(row, '已学完'), '列表行缺少学习状态');

// ---- 目录切换 / 浮动返回键 ----
ok(typeof ACP.nbToggleToc === 'function', '缺少 nbToggleToc');

// ---- 列表页渲染 ----
let crumb = null;
ACP.setCrumb = (t, s) => { crumb = t + '|' + s; };
ACP.openChapter = () => {};
ACP.state.store = { p: {}, fav: [] };
const root = { innerHTML: '', querySelectorAll: () => [] };
ACP.renderTutorial(root);
ok(root.innerHTML.length > 500, '列表页渲染为空');
ok(has(root.innerHTML, 'nb-hero-title'), '列表页缺少 Hero');
ok(has(root.innerHTML, 'nb-list'), '列表页缺少横框列表容器');
ok(!has(root.innerHTML, 'nb-diff'), '列表页不应出现难度徽标');
ok(!has(root.innerHTML, 'undefined'), '列表页出现 undefined');
window.NOTEBOOK_INDEX.chapters.forEach(c => {
    ok(has(root.innerHTML, c.title), '列表页缺少分组：' + c.title);
    c.items.forEach(it => ok(has(root.innerHTML, it.title), '列表页缺少教程：' + it.title));
});
ok(crumb && crumb.indexOf('官方实战教程') === 0, '面包屑未设置');

// ---- 正文中顺序与完整性 ----
const d = window.NOTEBOOK_CONTENT[slug];
const article = d.blocks.map(ACP.nbBlockHtml).join('');
const mdCount = d.blocks.filter(b => b.t === 'md').length;
const codeCount = d.blocks.filter(b => b.t === 'code').length;
ok((article.match(/nb-block nb-md/g) || []).length === mdCount, '讲解块数量不符');
ok((article.match(/nb-code-block/g) || []).length === codeCount, '代码块数量不符');
// 顺序：正文拼接中块 id 必须递增出现
let last = -1, ordered = true;
for (const m of article.matchAll(/id="nb-b-(\d+)"/g)) {
    const n = parseInt(m[1], 10);
    if (n <= last) ordered = false;
    last = n;
}
ok(ordered, '内容块顺序被破坏');
ok(!has(article, 'undefined'), '正文出现 undefined');

console.log('--- 教程模块冒烟测试 ---');
console.log('高亮/单元/目录/列表行/正文：共 24 篇索引，样本', slug,
    '| 块', d.blocks.length, '（讲解', mdCount, '· 代码', codeCount, '）');
console.log(fails.length ? 'FAIL: ' + fails.join('; ') : 'PASS');
process.exit(fails.length ? 1 : 0);
