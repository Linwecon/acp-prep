/* ============================================================
   Supabase 配置 —— 仅使用公开的 anon key（设计上可安全暴露在浏览器）
   ⚠️ 严禁在这里放置 service_role key 或任何私密 key！
   获取方式：Supabase Dashboard → Project Settings → API
   ============================================================ */
window.SUPABASE_CONFIG = {
  // 替换成你的项目地址，例如 https://abcd1234.supabase.co
  url: 'https://YOUR-PROJECT-ID.supabase.co',
  // 替换成你的 anon（public）key，以 eyJ... 开头
  anonKey: 'YOUR-SUPABASE-ANON-KEY'
};
