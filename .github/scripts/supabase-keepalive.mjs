/**
 * Supabase 保活脚本
 * ------------------------------------------------------------
 * 背景：Supabase 免费版项目连续 7 天无任何活动会被自动暂停；
 *       暂停后 <project_ref>.supabase.co 的 DNS 记录会被移除，
 *       前端表现为登录 / 注册失败（域名解析失败）。
 *
 * 做法：从 config/supabase.js 读取公开的 url / anonKey（保持单一数据源，
 *       换项目时无需改本脚本），请求两个端点制造"活动"：
 *         - /auth/v1/health  Auth 服务健康检查
 *         - /rest/v1/        PostgREST 根路径，会触达数据库
 *
 * 安全说明：anonKey 是设计上可公开的密钥，仓库里本来就有，不构成泄密。
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const CONFIG_PATH = path.resolve(process.cwd(), 'config/supabase.js');
const ENDPOINTS = ['/auth/v1/health', '/rest/v1/'];
const TIMEOUT_MS = 15000;

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

async function ping(base, anonKey, endpoint) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
        const res = await fetch(base + endpoint, {
            headers: { apikey: anonKey, Authorization: `Bearer ${anonKey}` },
            signal: ctrl.signal
        });
        return { endpoint, ok: res.ok, status: res.status };
    } catch (e) {
        return { endpoint, ok: false, status: 0, error: (e && e.message) || String(e) };
    } finally {
        clearTimeout(timer);
    }
}

async function main() {
    const { url, anonKey } = readConfig();
    console.log(`项目地址：${url}`);

    const results = await Promise.all(ENDPOINTS.map(p => ping(url, anonKey, p)));

    let failed = 0;
    for (const r of results) {
        if (r.ok) {
            console.log(`  ✅ ${r.endpoint} → HTTP ${r.status}`);
        } else {
            failed++;
            console.error(`  ❌ ${r.endpoint} → ${r.error ? r.error : 'HTTP ' + r.status}`);
        }
    }

    if (failed > 0) {
        console.error('');
        console.error('保活失败：Supabase 项目当前不可达。');
        console.error('常见原因：项目已被暂停（免费版 7 天无活动会自动暂停）。');
        console.error('处理方式：到 https://supabase.com/dashboard/projects 点 Resume project 恢复。');
        process.exit(1);
    }

    console.log('');
    console.log('保活成功：项目处于活跃状态，暂停计时已重置。');
}

main().catch(err => {
    console.error('保活脚本异常：' + ((err && err.message) || err));
    process.exit(1);
});
