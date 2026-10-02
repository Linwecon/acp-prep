/** Supabase 数据库保活；先在 SQL Editor 执行 supabase/keepalive_ping.sql。 */
import fs from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import process from 'node:process';

const CONFIG_PATH = fileURLToPath(new URL('../../config/supabase.js', import.meta.url));
const CHECKS = [
    { path: '/auth/v1/health', label: 'Auth 服务' },
    { path: '/rest/v1/rpc/ping', label: '数据库', pong: true }
];
function readConfig() {
    const src = fs.readFileSync(CONFIG_PATH, 'utf8');
    const url = (src.match(/url:\s*['"]([^'"]+)['"]/) || [])[1];
    const anonKey = (src.match(/anonKey:\s*['"]([^'"]+)['"]/) || [])[1];
    if (!url || !anonKey || /YOUR-/.test(url + anonKey)) throw new Error('请填写公开配置');
    if (new URL(url).protocol !== 'https:') throw new Error('项目地址必须使用 HTTPS');
    return { url: url.replace(/\/+$/, ''), anonKey };
}
export async function checkEndpoint(config, check, {
    fetchFn = fetch,
    sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
    timeoutMs = 15000
} = {}) {
    for (let attempt = 1; attempt <= 3; attempt++) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), timeoutMs);
        let result;
        try {
            const headers = { apikey: config.anonKey };
            // publishable key 不是 JWT，不能作为 Bearer token。
            if (config.anonKey.startsWith('eyJ')) headers.Authorization = `Bearer ${config.anonKey}`;
            const res = await fetchFn(config.url + check.path, { headers, signal: ctrl.signal });
            result = { ok: res.ok, status: res.status };
            if (res.ok && check.pong) {
                result.ok = (await res.text()).trim() === '"pong"';
                if (!result.ok) result.error = '数据库返回内容不是预期的 pong';
            }
        } catch (e) {
            result = { ok: false, status: 0, error: e.cause?.code || e.code || e.message };
        } finally {
            clearTimeout(timer);
        }
        const retryable = result.status === 0 || result.status === 408 || result.status === 429 || result.status >= 500;
        if (result.ok || !retryable || attempt === 3) return result;
        await sleep(1000 * 2 ** (attempt - 1));
    }
}
export async function runChecks(config, options = {}) {
    return Promise.all(CHECKS.map(async check => ({ ...check, ...await checkEndpoint(config, check, options) })));
}
async function main() {
    const config = readConfig();
    console.log(`项目地址：${config.url}`);
    const results = await runChecks(config);
    for (const r of results) {
        console.log(`${r.ok ? 'OK' : 'FAIL'} ${r.label}：${r.error || `HTTP ${r.status}`}`);
        if (r.pong && r.status === 404) console.error('请在 Supabase SQL Editor 执行 supabase/keepalive_ping.sql，再重新运行。');
        if (r.status === 401 || r.status === 403) console.error('请核对公开密钥和 ping() 的执行权限。');
    }
    const ok = results.every(r => r.ok);
    const summary = ok
        ? '本次 Auth 和数据库检查通过，已执行数据库查询。此结果不保证平台不会暂停项目。'
        : '保活检查失败。请检查项目状态、网络、配置和上述错误；已暂停项目需在控制台恢复。';
    console.log(summary);
    if (process.env.GITHUB_STEP_SUMMARY) {
        fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY,
            `## Supabase 保活检查\n\n${results.map(r => `- ${r.label}: ${r.ok ? '通过' : '失败'} (HTTP ${r.status})`).join('\n')}\n\n${summary}\n`);
    }
    if (!ok) process.exitCode = 1;
}
if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
    main().catch(() => {
        console.error('保活脚本无法启动：请检查 config/supabase.js 格式及运行环境。');
        process.exitCode = 1;
    });
}
