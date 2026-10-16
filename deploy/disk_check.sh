#!/bin/bash
# What is taking the disk on this server - looks only, deletes nothing.
#   bash deploy/disk_check.sh
set -u
say() { printf '\n== %s\n' "$*"; }

say "Disk"
df -h / | tail -1

say "Biggest folders on the disk (top 12)"
sudo du -xh --max-depth=2 / 2>/dev/null | sort -rh | head -12

say "Logs"
sudo journalctl --disk-usage 2>/dev/null
sudo du -sh /var/log 2>/dev/null
sudo du -sh /var/log/nginx 2>/dev/null

say "App folder"
du -sh ~/infinia-labour-tool 2>/dev/null
du -sh ~/infinia-labour-tool/.git 2>/dev/null
du -sh ~/.cache 2>/dev/null

say "Database"
sudo du -sh /var/lib/postgresql 2>/dev/null
DB=$(systemctl show infinia -p Environment --value 2>/dev/null | grep -o 'DATABASE_URL=[^ ]*' | sed 's/.*\///; s/?.*//')
DB=${DB:-infinia}
sudo -u postgres psql -d "$DB" -At -F ' | ' -c "
  select 'whole database', pg_size_pretty(pg_database_size(current_database()));
  select relname, pg_size_pretty(pg_total_relation_size(relid)) from pg_catalog.pg_statio_user_tables
   order by pg_total_relation_size(relid) desc limit 8;
  select 'backups kept: ' || count(*) || ' (' || coalesce(string_agg(distinct trigger, ', '), '') || ')',
         'oldest ' || coalesce(min(created_at)::date::text, '-') || ', newest ' || coalesce(max(created_at)::date::text, '-') from backups;
  select 'backups by day (last 7)', string_agg(d || ': ' || n, '  ') from
   (select created_at::date d, count(*) n from backups where created_at > now() - interval '7 days' group by 1 order by 1) x;
  select 'space freed but not yet reused (dead rows)', pg_size_pretty(sum(n_dead_tup * 100)::bigint) from pg_stat_user_tables;" 2>/dev/null \
  || echo "  (could not open the database as postgres - send me the lines above)"

say "Done - nothing was changed. Send me this output."
