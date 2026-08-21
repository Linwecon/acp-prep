/* ============================================================
   Supabase 配置 —— 仅使用公开的 anon key（设计上可安全暴露在浏览器）
   ⚠️ 严禁在这里放置 service_role key 或任何私密 key！
   获取方式：Supabase Dashboard → Project Settings → API
   ============================================================ */
window.SUPABASE_CONFIG = {
  // 项目地址（已按你的 project_ref 填好）
  url: 'https://uzeyrcmzbbpdhxgdmtgr.supabase.co',
  // anon（public）key，可安全暴露在浏览器
  anonKey: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InV6ZXlyY216YmJwZGh4Z2RtdGdyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODczMDM3NjIsImV4cCI6MjEwMjg3OTc2Mn0.LWbgM_Ct6mYGKGDUQd_2-mmuyzGtJpD4v2l4c2VTIUE'
};
