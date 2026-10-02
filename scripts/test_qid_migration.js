/* 学习记录迁移冒烟测试：node scripts/test_qid_migration.js */
const fs = require('fs');
const path = require('path');
global.window = {};
const ROOT = path.resolve(__dirname, '..');
const src = fs.readFileSync(path.join(ROOT, 'data', 'quiz_qid_migration.js'), 'utf8');
eval(src);
const map = window.ACP_QID_MIGRATION;
let pass = 0, fail = 0;
function ok(cond, msg) { if (cond) { pass++; } else { fail++; console.log('FAIL:', msg); } }

ok(Object.keys(map).length >= 50, '映射应覆盖两轮移章（54 条），实际 ' + Object.keys(map).length);

// 模拟 ACP 环境
const ID_MAP = {};
// 新库中存在 2-0080（1-0080 移章而来）与 7-0186
ID_MAP['2-0080'] = { id: '2-0080', ch: 2 };
ID_MAP['7-0186'] = { id: '7-0186', ch: 7 };
const ACP = {
  ID_MAP,
  state: {},
  migrateMovedQids: null,
  STORE_KEY: 'test_store'
};
// 从 store.js 提取 migrateMovedQids（IIFE 无法直接 require，用正则截取函数体）
const storeSrc = fs.readFileSync(path.join(ROOT, 'js', 'store.js'), 'utf8');
const m = storeSrc.match(/function migrateMovedQids\(s\) \{[\s\S]*?\n    \}/);
ok(m, 'store.js 中应存在 migrateMovedQids');
eval('ACP.migrateMovedQids = ' + m[0].replace('function migrateMovedQids(s)', 'function(s)'));

global.window = { ACP_QID_MIGRATION: map };

// 用例1：旧记录无冲突 → 原样迁移
let s = { p: { '1-0080': { d: 2, w: 1, c: 0, t: 100 } }, fav: ['1-0080'], last: { id: '1-0080', ch: 1 } };
ACP.migrateMovedQids(s);
ok(s.p['2-0080'] && s.p['2-0080'].d === 2 && s.p['2-0080'].w === 1, '旧记录应迁移到新题号且保留统计');
ok(!s.p['1-0080'], '旧键应移除（记录已迁移，非清空）');
ok(s.fav.includes('2-0080') && !s.fav.includes('1-0080'), '收藏应同步迁移');
ok(s.last.id === '2-0080' && s.last.ch === 2, '继续学习应指向新题号');

// 用例2：两边都有记录 → 合并不丢失
s = { p: { '1-0080': { d: 3, w: 2, c: 1, t: 200 }, '2-0080': { d: 1, w: 0, c: 1, t: 100 } }, fav: [], last: null };
ACP.migrateMovedQids(s);
ok(s.p['2-0080'].d === 3 && s.p['2-0080'].w === 2, 'd/w 取较大值合并');
ok(s.p['2-0080'].c === 1 && s.p['2-0080'].t === 200, '最近作答状态优先');

// 用例3：幂等 —— 重复执行无变化
const snap = JSON.stringify(s.p);
ACP.migrateMovedQids(s);
ok(JSON.stringify(s.p) === snap, '迁移应幂等');

// 用例4：无映射的记录原样保留（不清空）
s = { p: { '9-9999': { d: 1, w: 1, c: 0 } }, fav: [], last: null };
ACP.migrateMovedQids(s);
ok(s.p['9-9999'] && s.p['9-9999'].d === 1, '无映射记录不得清空');

// 用例5：新题号在当前数据中不存在 → 保留原记录（数据版本较旧）
s = { p: { '1-0177': { d: 1, w: 0, c: 1 } }, fav: [], last: null };  // 2-0177 不在测试 ID_MAP 中
ACP.migrateMovedQids(s);
ok(s.p['1-0177'], '目标题号缺失时保留原记录不丢失');

console.log(`迁移冒烟测试: ${pass} 通过, ${fail} 失败`);
process.exit(fail ? 1 : 0);
