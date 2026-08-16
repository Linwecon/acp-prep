// Quick smoke test for js/study.js markdown renderer (run with node)
const fs = require('fs');

// 1. load knowledge data (sets window.KNOWLEDGE_MD)
global.window = { ACP: {} };
eval(fs.readFileSync('data/knowledge.js', 'utf8'));

// 2. load study.js module into window.ACP
const src = fs.readFileSync('js/study.js', 'utf8');
new Function('window', src)(window);

const ACP = window.ACP;
const md = window.KNOWLEDGE_MD;
const html = ACP.mdToHtml(md);

const count = (re, s) => (s.match(re) || []).length;

console.log('--- stats ---');
console.log('md chars       :', md.length);
console.log('html chars     :', html.length);
console.log('h1             :', count(/<h1/g, html));
console.log('h2             :', count(/<h2/g, html));
console.log('h3             :', count(/<h3/g, html));
console.log('tables         :', count(/<table>/g, html));
console.log('table rows     :', count(/<tr>/g, html));
console.log('blockquotes    :', count(/<blockquote/g, html));
console.log('code blocks    :', count(/<pre><code>/g, html));
console.log('inline code    :', count(/<code>/g, html) - count(/<\/code><\/pre>/g, html));
console.log('ul/ol          :', count(/<ul>|<ol>/g, html));
console.log('links          :', count(/<a href=/g, html));
console.log('hr             :', count(/<hr>/g, html));

// 3. content sanity checks
const fails = [];
if (count(/<h2/g, html) < 13) fails.push('h2 count < 13');
if (md.includes('undefined') && html.includes('undefined')) fails.push('contains undefined');
if (/<table><\/div>/.test(html)) fails.push('broken table');
if (!/prompt \| model/.test(html)) fails.push('escaped pipe not unescaped');
if (/class="study-bq\s+"/.test(html)) fails.push('blockquote class issue');
if (count(/<td/g, html) < 100) fails.push('too few cells');
if (/<p><\/p>/.test(html)) fails.push('empty paragraph');
if (html.includes('&lt;script&gt;') && !html.includes('&amp;')) fails.push('escaping issue');

// anchor round-trip: every in-doc link target must exist as an id
const ids = new Set([...html.matchAll(/id="([^"]+)"/g)].map(m => m[1]));
let missing = 0;
for (const m of html.matchAll(/href="#([^"]+)"/g)) {
    if (!ids.has(m[1])) { missing++; if (missing < 6) console.log('  missing anchor:', m[1]); }
}
console.log('missing anchors:', missing);

// nested list present
console.log('sub list items :', count(/class="sub"/g, html));

console.log('---', fails.length ? 'FAIL: ' + fails.join('; ') : 'PASS');
