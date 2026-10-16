-- 在现有项目的 SQL Editor 执行一次；可重复执行，不清空业务记录。
alter table public.user_progress add column if not exists wrong_updated_at timestamptz;
update public.user_progress
set wrong_updated_at = coalesce(answered_at, updated_at)
where wrong_updated_at is null;

-- 所有客户端（包括旧版网页）写入时都保留较新的错题状态和作答快照。
create or replace function public.merge_progress_update()
returns trigger language plpgsql security invoker set search_path = '' as $$
declare
  old_wrong_time timestamptz;
  new_wrong_time timestamptz;
begin
  old_wrong_time := coalesce(old.wrong_updated_at, old.answered_at, '-infinity'::timestamptz);
  new_wrong_time := coalesce(new.wrong_updated_at, new.answered_at, '-infinity'::timestamptz);
  -- 旧客户端不提交新字段：只有更新的作答可以改变错题状态。
  if new.wrong_updated_at is not distinct from old.wrong_updated_at
     and new.correct = 0 and new.wrong > old.wrong
     and new.answered_at > old_wrong_time then
    new_wrong_time := new.answered_at;
  end if;
  new.done := greatest(old.done, new.done);
  if old_wrong_time > new_wrong_time then
    new.wrong := old.wrong;
    new.wrong_updated_at := old_wrong_time;
  elsif old_wrong_time = new_wrong_time then
    if old.wrong = 0 or new.wrong = 0 then new.wrong := 0;
    else new.wrong := greatest(old.wrong, new.wrong); end if;
    new.wrong_updated_at := old.wrong_updated_at;
  else
    new.wrong_updated_at := new_wrong_time;
  end if;
  if coalesce(old.answered_at, '-infinity'::timestamptz) > coalesce(new.answered_at, '-infinity'::timestamptz) then
    new.correct := old.correct;
    new.answer := old.answer;
    new.answered_at := old.answered_at;
  end if;
  return new;
end;
$$;
drop trigger if exists merge_progress_update on public.user_progress;
create trigger merge_progress_update before update on public.user_progress
for each row execute function public.merge_progress_update();

-- 教程、知识点按条目同步。旧设备的全量回推不能撤销较新的掌握/取消状态。
create or replace function public.merge_meta_update()
returns trigger language plpgsql security invoker set search_path = '' as $$
begin
  if old.updated_at > new.updated_at then return old; end if;
  return new;
end;
$$;
drop trigger if exists merge_meta_update on public.user_meta;
create trigger merge_meta_update before update on public.user_meta
for each row execute function public.merge_meta_update();

-- 客户端对已存在记录使用 upsert，需要相应 UPDATE policy。
drop policy if exists fav_update_own on public.favorites;
create policy fav_update_own on public.favorites
for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists exam_update_own on public.exam_records;
create policy exam_update_own on public.exam_records
for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
notify pgrst, 'reload schema';
