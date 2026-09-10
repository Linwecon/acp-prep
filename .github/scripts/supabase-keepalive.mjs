/**
 * Supabase 保活脚本
 * ------------------------------------------------------------
 * 背景：Supabase 免费版项目连续 7 天无任何活动会被自动暂停；
 *       暂停后 <project_ref>.supabase.co 的 DNS 记录会被移除，
 *       前端表现为登录 / 注册失败（域名解析失败）。
 *
 * 做法：从 config/supabase.js 读取公开的 url / anonKey（保持单一数据源，
 *       换项目时无需改本脚本），请求项目接口制造"活动"。
 *
 * 检查项：
 *   [必需] GET /auth/v1/health    Auth 服务健康检查，200 即判定项目活跃
 *   [可选] GET /rest/v1/rpc/ping  触达数据库，需先执行 supabase/keepalive_ping.sql
 *
 * 说明：anon key 没有表的 GRANT（见 schema.sql 第 60-66 行），
 *       且 /rest/v1/ 根路径（OpenAPI 文档）只允许 service_role，
 *       因此这里用 /auth/v1/health 作为判定依据，不查业务表。
 *
 * 安全说明：anonKey 是设计上可公开的密钥，仓库里本来就有，不构成泄密。
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const CONFIG_PATH = path.resolve(process.cwd(), 'config/supabase.js');
const TIMEOUT_MS = 15000;

const CHECKS = [
    { path: '/auth/v1/health', label: 'Auth 服务健康检查', required: true },
    { path: '/rest/v1/rpc/ping', label: '数据库触达', required: false }
];

function readConfig() {
    if (!fs.existsSync(CONFIG_PATH)) {
        throw new Error(`找不到配置文件：${CONFIG_PATH}`);
    }
    const src = fs.readFileSync(CONFIG_PATH, 'utf8');
    const url = (src.match(/url:\s*['"]([^'"]+)['"]/) || [])[1];
    const anonKey = (src.match(/anonKey:\s*['"]([^'"]+)['"]/) || [])[1];
    if (!url || !anonKey) {
        throw new Error('无法从 config/supabase.js 解析出 url / anonKey');
    }
    return { url: url.replace(/\/+$/, ''), anonKey };
}

async function request(base, anonKey, endpoint) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
        const res = await fetch(base + endpoint, {
            headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` },
            signal: ctrl.signal
        });
        return { status: res.status, ok: res.ok };
    } catch (e) {
        return { status: 0, ok: false, error: (e && e.message) || String(e) };
    } finally {
        clearTimeout(timer);
    }
}

/* 可选检查项的友好解释：不阻断流程，只做提示 */
function explainOptional(status) {
    if (status === 404) return '未创建 ping() 函数 —— 可选增强，见 supabase/keepalive_ping.sql';
    if (status === 401 || status === 403) return 'anon 无执行权限 —— 检查 keepalive_ping.sql 里的 grant 语句';
    return '未达预期，但不影响保活判定';
}

async function main() {
    const { url, anonKey } = readConfig();
    console.log(`项目地址：${url}`);
    console.log('');

    let requiredFailed = 0;

    for (const check of CHECKS) {
        const r = await request(url, anonKey, check.path);
        const tag = check.required ? '[必需]' : '[可选]';

        if (r.ok) {
            console.log(`  ✅ ${tag} ${check.label} → HTTP ${r.status}`);
        } else if (check.required) {
            requiredFailed++;
            console.error(`  ❌ ${tag} ${check.label} → ${r.error ? r.error : 'HTTP ' + r.status}`);
        } else {
            console.log(`  ➖ ${tag} ${check.label} → ${r.error ? r.error : 'HTTP ' + r.status}｜${explainOptional(r.status)}`);
        }
    }

    console.log('');

    if (requiredFailed > 0) {
        console.error('保活失败：Supabase 项目当前不可达。');
        console.error('常见原因：项目已被暂停（免费版 7 天无活动会自动暂停）。');
        console.error('处理方式：到 https://supabase.com/dashboard/projects 点 Resume project 恢复。');
        process.exit(1);
    }

    console.log('保活成功：项目处于活跃状态，暂停计时已重置。');
}

main().catch(err => {
    console.error('保活脚本异常：' + ((err && err.message) || err));
    process.exit(1);
});
