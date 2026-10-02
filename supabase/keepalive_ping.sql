-- 在 Supabase Dashboard → SQL Editor 执行一次；可重复执行。
-- 只读数据库查询，不读取业务数据，不需要 service_role 密钥。
create or replace function public.ping()
returns text
language sql
stable
security invoker
set search_path = ''
as $$
  select 'pong'::text
$$;

revoke all on function public.ping() from public;
grant usage on schema public to anon, authenticated;
grant execute on function public.ping() to anon, authenticated;
notify pgrst, 'reload schema';
