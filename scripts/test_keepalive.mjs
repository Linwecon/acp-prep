import test from 'node:test';
import assert from 'node:assert/strict';
import { checkEndpoint, runChecks } from '../.github/scripts/supabase-keepalive.mjs';
const config = { url: 'https://example.invalid', anonKey: 'sb_publishable_test' };
const rpc = { path: '/rest/v1/rpc/ping', pong: true };
const reply = (status, body = '"pong"') => ({ status, ok: status === 200, text: async () => body });

test('Auth 200 cannot mask missing database RPC', async () => {
    const results = await runChecks(config, { fetchFn: async url => reply(url.endsWith('/ping') ? 404 : 200) });
    assert.equal(results.every(r => r.ok), false);
    assert.equal(results[0].ok, true);
    assert.equal(results[1].status, 404);
});
test('both endpoints succeed; publishable key is not a Bearer JWT', async () => {
    const results = await runChecks(config, { fetchFn: async (url, opts) => {
        assert.equal(opts.headers.Authorization, undefined);
        assert.equal(opts.headers.apikey, config.anonKey);
        return reply(200);
    } });
    assert.ok(results.every(r => r.ok));
});
test('reject unexpected HTTP 200 payload', async () => {
    const r = await checkEndpoint(config, rpc, { fetchFn: async () => reply(200, '<html>proxy</html>') });
    assert.equal(r.ok, false);
});
test('retry transient failure and stop after recovery', async () => {
    let calls = 0; const delays = [];
    const r = await checkEndpoint(config, rpc, {
        fetchFn: async () => { if (++calls === 1) throw new Error('network'); return reply(calls === 2 ? 503 : 200); },
        sleep: async ms => delays.push(ms)
    });
    assert.equal(r.ok, true); assert.equal(calls, 3); assert.deepEqual(delays, [1000, 2000]);
});
test('permanent authorization failure is not retried', async () => {
    let calls = 0;
    const r = await checkEndpoint(config, rpc, { fetchFn: async () => { calls++; return reply(403); } });
    assert.equal(r.ok, false); assert.equal(calls, 1);
});
test('timeout aborts and retries are bounded', async () => {
    let calls = 0;
    const r = await checkEndpoint(config, rpc, {
        fetchFn: async (url, { signal }) => new Promise((resolve, reject) => {
            calls++; signal.addEventListener('abort', () => reject(new Error('timeout')), { once: true });
        }), timeoutMs: 5, sleep: async () => {}
    });
    assert.equal(r.ok, false); assert.equal(calls, 3);
});
