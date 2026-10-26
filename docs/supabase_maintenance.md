# Supabase 暂停、恢复与保活

## 本次同步功能升级

模拟考试交卷后保存完整题目快照（含选项、正确答案和解析）及本次作答。成绩继续写入 `exam_records`，试卷写入已有的 `user_meta`，键为 `exam_paper:<考试 ID>`，沿用账号隔离策略，无需新增数据库字段。登录后交卷自动上传；失败可点击“同步”重试，重新联网及再次登录也会同步。未登录考试仅保存在访客档案，不会自动归入其他账号。

模拟考试页的“历史试卷”支持查看成绩和逐题回顾，超过八条可展开更早记录。旧版仅有成绩的记录保留展示，无法还原此前未保存的试卷。云端读取不再截断为最近 100 次。

已有数据库需要在 SQL Editor 执行 `supabase/sync_upgrade.sql`，再部署新版网页。脚本可重复执行，不删除历史记录；它新增 `user_progress.wrong_updated_at`、保护较新的错题/学习状态，并补齐收藏和模考记录 upsert 所需的 UPDATE 权限策略。

如果数据库尚未升级，新版网页会在确认 `wrong_updated_at` 字段不存在后自动兼容：作答仍写入 `user_progress`，独立的错题状态和时间写入现有 `user_meta` 的 `progress_wrong:<题号>` 条目。收藏和已提交成绩遇到重复记录时跳过插入，不要求旧版数据库额外提供 UPDATE 策略。该兼容不创建新表，也不清空历史记录。

仍建议执行升级脚本，以启用数据库层的并发冲突保护；兼容模式无法替代数据库触发器对同时写入的保护。权限、网络或其他字段错误不会被当作旧版结构忽略，页面会显示具体失败原因并保留本地记录。首次安装数据库则依次执行 `schema.sql` 和 `sync_upgrade.sql`。

## 已经无法连接时

1. 登录 Supabase Dashboard，打开 `config/supabase.js` 对应的项目，确认状态。如果显示 Paused，执行 Restore 并等待恢复完成。不要因为暂时无法连接而删除项目或清空浏览器学习记录。
2. 在 SQL Editor 执行仓库中的 `supabase/keepalive_ping.sql`。该脚本可重复执行，只创建返回 `pong` 的只读函数，并允许公开客户端执行；无需暴露 service_role 或数据库密码。
3. 打开 GitHub 仓库的 Actions → Supabase Keep-Alive；如果工作流已停用，先 Enable workflow，再 Run workflow。确认 Auth 服务和数据库检查都通过。也可以在项目根目录运行：

   ```sh
   node .github/scripts/supabase-keepalive.mjs
   ```

4. 刷新网站并重新检测连接，确认登录与同步恢复。

域名解析失败也可能来自网络、DNS 或配置错误，不能仅据此判定项目被暂停。以 Dashboard 项目状态为准。

## 如何判断保活是否生效

工作流默认每 6 小时运行一次，使用 `config/supabase.js` 中的公开项目地址和公开密钥，同时检查 Auth 与数据库 RPC。相关配置或探针在 main 分支更新时也会触发检查。

- 两项都通过：本次成功执行了数据库查询。
- RPC 返回 404：确认已经安装 `keepalive_ping.sql`，且该 SQL 与网站配置指向同一项目。
- 401 / 403：核对公开密钥、函数授权与项目访问限制。
- DNS、超时或 5xx：检查 Dashboard 状态、网络及 Supabase 服务状态；脚本会对暂时性错误重试，最终失败会让工作流显示失败。

仅 Auth 健康检查成功不足以证明数据库可用。不要把工作流的绿色状态视为永不暂停的保证。

## 长期运行的限制

Supabase 官方说明：免费项目可能在连续 7 天低活跃后暂停；付费计划项目不因不活跃自动暂停。如果需要长期无人维护且保持可用，应选择符合需求的付费计划。

GitHub 公共仓库连续 60 天无活动时，定时工作流会被自动停用。需要定期查看 Actions；若使用独立服务器或外部调度器运行相同检查，还需监测调度器本身的失败。外部定时请求同样不构成 Supabase 免费计划的可用性保证。

本仓库不通过制造空提交维持定时任务，也不在前端保存 Supabase 管理令牌。恢复项目是控制台管理操作，公开 anon key 无法执行。

参考：

- [Supabase 项目暂停说明](https://supabase.com/docs/guides/platform/free-project-pausing)
- [Supabase 生产环境检查清单](https://supabase.com/docs/guides/deployment/going-into-prod)
- [GitHub 工作流启用、停用与 60 天限制](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)
