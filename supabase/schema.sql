-- ============================================================
-- ACP 备考助手 — Supabase 数据库初始化脚本
-- 用法：Supabase Dashboard → SQL Editor → 整段粘贴执行
-- 说明：所有表都启用 RLS，用户只能读写自己的数据（auth.uid() = user_id）
-- ============================================================

-- ---------- 1) 做题进度（每道题一行） ----------
-- 学习进度 / 章节完成状态 / 做题记录 / 错题本，都由此表派生：
--   错题本 = wrong > 0；做题记录 = done/wrong/correct/answer 聚合
create table if not exists public.user_progress (
  user_id     uuid not null references auth.users(id) on delete cascade,
  question_id text not null,
  done        integer not null default 0,   -- 做题次数
  wrong       integer not null default 0,   -- 答错次数（>0 即错题）
  correct     integer not null default 0,   -- 最近一次 1=对 0=错
  answer      jsonb,                         -- 最近一次作答选项，如 ["A","B"]
  answered_at timestamptz,                   -- 最近一次作答时间
  updated_at  timestamptz not null default now(),
  primary key (user_id, question_id)
);

-- ---------- 2) 收藏题目 ----------
create table if not exists public.favorites (
  user_id     uuid not null references auth.users(id) on delete cascade,
  question_id text not null,
  created_at  timestamptz not null default now(),
  primary key (user_id, question_id)
);

-- ---------- 3) 模拟考试成绩 ----------
create table if not exists public.exam_records (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  score      integer,
  correct    integer,
  wrong      integer,
  pass       boolean,
  time_used  integer,                       -- 用时（秒）
  weak_by_ch jsonb,                          -- 薄弱章节分布 {章: 错题数}
  created_at timestamptz not null default now()
);

-- ---------- 4) 用户元信息（续做位置 last 等） ----------
create table if not exists public.user_meta (
  user_id    uuid not null references auth.users(id) on delete cascade,
  key        text not null,
  value      jsonb,
  updated_at timestamptz not null default now(),
  primary key (user_id, key)
);

-- 索引
create index if not exists idx_progress_user on public.user_progress(user_id);
create index if not exists idx_fav_user on public.favorites(user_id);
create index if not exists idx_exam_user on public.exam_records(user_id, created_at desc);

-- ---------- 权限 ----------
-- 客户端使用 anon key + 登录后的 access token（role=authenticated）访问；
-- 只需给 authenticated 授权，anon 不需要（RLS 会拦到 auth.uid()）。
grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on
  public.user_progress,
  public.favorites,
  public.exam_records,
  public.user_meta
  to authenticated;

-- ---------- RLS ----------
alter table public.user_progress enable row level security;
alter table public.favorites enable row level security;
alter table public.exam_records enable row level security;
alter table public.user_meta enable row level security;

-- user_progress
create policy "progress_select_own" on public.user_progress
  for select using (auth.uid() = user_id);
create policy "progress_insert_own" on public.user_progress
  for insert with check (auth.uid() = user_id);
create policy "progress_update_own" on public.user_progress
  for update using (auth.uid() = user_id);
create policy "progress_delete_own" on public.user_progress
  for delete using (auth.uid() = user_id);

-- favorites
create policy "fav_select_own" on public.favorites
  for select using (auth.uid() = user_id);
create policy "fav_insert_own" on public.favorites
  for insert with check (auth.uid() = user_id);
create policy "fav_delete_own" on public.favorites
  for delete using (auth.uid() = user_id);

-- exam_records
create policy "exam_select_own" on public.exam_records
  for select using (auth.uid() = user_id);
create policy "exam_insert_own" on public.exam_records
  for insert with check (auth.uid() = user_id);
create policy "exam_delete_own" on public.exam_records
  for delete using (auth.uid() = user_id);

-- user_meta
create policy "meta_select_own" on public.user_meta
  for select using (auth.uid() = user_id);
create policy "meta_insert_own" on public.user_meta
  for insert with check (auth.uid() = user_id);
create policy "meta_update_own" on public.user_meta
  for update using (auth.uid() = user_id);
