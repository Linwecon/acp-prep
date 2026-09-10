-- ============================================================
-- ACP 备考助手 — Supabase 保活增强（可选，非必需）
-- 用法：Supabase Dashboard → SQL Editor → 整段粘贴执行
-- ------------------------------------------------------------
-- 作用：提供一个 anon 可调用的 ping() 函数，让保活脚本能够真正
--       触达数据库，而不只是打 Auth 服务的健康检查接口。
--
-- 为什么需要：schema.sql 只给 authenticated 授了表权限，anon 无法
--             查询任何业务表；而 /rest/v1/ 根路径（OpenAPI 文档）
--             现在只允许 service_role 访问。因此若要让保活请求落到
--             数据库层，需要一个显式的、只读的 RPC 出口。
--
-- 安全性：函数仅返回固定字符串 'pong'，不读取任何业务数据、
--         不接收任何参数、无副作用。标记为 stable，PostgREST 允许
--         用 GET 调用（GET /rest/v1/rpc/ping）。
--
-- 不执行本脚本也可以：保活任务仍会以 /auth/v1/health 作为判定依据，
--                     只是少了"触达数据库"这一层保险。
-- ============================================================

create or replace function public.ping()
returns text
language sql
stable          -- 无副作用，允许 PostgREST 以 GET 方式调用
security definer
set search_path = ''   -- 不依赖任何 schema，避免 search_path 注入
as $$
  select 'pong'::text
$$;

-- 允许匿名（anon）与登录用户调用，保活脚本使用 anon key
grant execute on function public.ping() to anon, authenticated;
