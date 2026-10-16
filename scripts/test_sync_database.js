// Real PostgreSQL regression tests via PGlite. Requires @electric-sql/pglite in NODE_PATH.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { PGlite } = require('@electric-sql/pglite');
const read = name => fs.readFileSync(path.join(__dirname, '..', 'supabase', name), 'utf8');
const user = '00000000-0000-4000-8000-000000000001';
const other = '00000000-0000-4000-8000-000000000002';

test('sync migration and conflict protection execute in PostgreSQL', async t => {
    const db = new PGlite();
    try {
        await db.exec(`
            create role anon; create role authenticated;
            create schema auth;
            create table auth.users (id uuid primary key);
            insert into auth.users values ('${user}'), ('${other}');
            create function auth.uid() returns uuid language sql as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
            grant usage on schema auth to authenticated;
        `);
        await db.exec(read('schema.sql'));
        // Simulate an existing deployment before the new column was installed.
        await db.exec('alter table public.user_progress drop column wrong_updated_at');
        await db.query(`insert into user_progress(user_id,question_id,done,wrong,correct,answer,answered_at) values ($1,'q',4,3,0,'["A"]','2026-01-01')`, [user]);
        await db.exec(read('sync_upgrade.sql'));
        await db.exec(read('sync_upgrade.sql'));

        await t.test('migration backfills timestamps and is repeatable', async () => {
            const { rows } = await db.query('select wrong_updated_at = answered_at as backfilled from user_progress');
            assert.equal(rows[0].backfilled, true);
        });
        await db.exec(`set role authenticated; set request.jwt.claim.sub = '${user}'`);
        await t.test('clearing wrong is preserved against stale new and legacy clients', async () => {
            await db.query(`update user_progress set wrong=0,wrong_updated_at='2026-02-01' where question_id='q'`);
            await db.query(`update user_progress set done=2,wrong=3,wrong_updated_at='2026-01-01' where question_id='q'`);
            await db.query(`update user_progress set wrong=3 where question_id='q'`);
            await db.query(`update user_progress set wrong=3,correct=1,answered_at='2026-02-15' where question_id='q'`);
            const { rows } = await db.query('select done,wrong from user_progress');
            assert.equal(rows[0].done, 4);
            assert.equal(rows[0].wrong, 0);
        });
        await t.test('later wrong answers can add the question again', async () => {
            await db.query(`update user_progress set wrong=1,correct=0,answer='["B"]',answered_at='2026-03-01',wrong_updated_at='2026-03-01' where question_id='q'`);
            assert.equal((await db.query('select wrong from user_progress')).rows[0].wrong, 1);
        });
        await t.test('stale answer snapshots cannot overwrite a recent exam answer', async () => {
            await db.query(`update user_progress set correct=1,answer='["A"]',answered_at='2026-01-01',wrong_updated_at='2026-01-01' where question_id='q'`);
            const { rows } = await db.query('select correct,answer,wrong from user_progress');
            assert.equal(rows[0].correct, 0);
            assert.deepEqual(rows[0].answer, ['B']);
            assert.equal(rows[0].wrong, 1);
        });
        await t.test('new knowledge cancellation survives an older upsert', async () => {
            await db.query(`insert into user_meta(user_id,key,value,updated_at) values ($1,'study_done:kp','false','2026-03-01')`, [user]);
            await db.query(`insert into user_meta(user_id,key,value,updated_at) values ($1,'study_done:kp','true','2026-02-01') on conflict(user_id,key) do update set value=excluded.value,updated_at=excluded.updated_at`, [user]);
            assert.equal((await db.query(`select value from user_meta where key='study_done:kp'`)).rows[0].value, false);
        });
        await t.test('favorites and exam records can be upserted twice under authenticated RLS', async () => {
            for (let i = 0; i < 2; i++) {
                await db.query(`insert into favorites(user_id,question_id) values ($1,'q') on conflict(user_id,question_id) do update set question_id=excluded.question_id`, [user]);
                await db.query(`insert into exam_records(id,user_id,score) values ($1,$2,90) on conflict(id) do update set score=excluded.score`, [user, user]);
            }
            assert.equal((await db.query('select count(*)::int as n from exam_records')).rows[0].n, 1);
        });
        await t.test('users still cannot read or insert another account records', async () => {
            await db.exec(`set request.jwt.claim.sub = '${other}'`);
            assert.equal((await db.query('select * from user_progress')).rows.length, 0);
            await assert.rejects(db.query(`insert into favorites(user_id,question_id) values ($1,'forbidden')`, [user]), /row-level security/);
        });
    } finally { await db.close(); }
});
