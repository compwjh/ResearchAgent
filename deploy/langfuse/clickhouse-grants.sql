-- Langfuse v4 所需的 ClickHouse 权限
-- 关联：spec-013 / docs/sdd/plans/013/task-02-deploy-langfuse.md
--
-- v4 比 v3 需要更多权限。缺少时 schema 迁移会报：
--   "Not enough privileges. To execute this query, it's necessary to have the grant ..."
--
-- 执行方式（用 default 用户执行，因为建用户与授权需要更高权限）：
--   curl 'http://127.0.0.1:8123/' --data-binary @deploy/langfuse/clickhouse-grants.sql
--   或逐条：curl 'http://127.0.0.1:8123/' --data-binary "CREATE USER ..."

-- 1. 创建专用用户（本地开发口令，可按需修改）
CREATE USER IF NOT EXISTS langfuse IDENTIFIED WITH plaintext_password BY 'langfuse_dev';

-- 2. 库级权限：建表/改表/读写
GRANT ALL ON default.* TO langfuse;

-- 3. 表引擎权限（关键）
--    注意：TABLE ENGINE 是全局权限，GRANT ALL ON default.* 不包含它。
--    迁移脚本会依次用到 MergeTree / ReplacingMergeTree / 物化视图等，
--    缺少时报错形如 "... necessary to have the grant TABLE ENGINE ON ReplacingMergeTree"。
GRANT TABLE ENGINE ON MergeTree TO langfuse;
GRANT TABLE ENGINE ON ReplacingMergeTree TO langfuse;
GRANT TABLE ENGINE ON AggregatingMergeTree TO langfuse;
GRANT TABLE ENGINE ON SummingMergeTree TO langfuse;
GRANT TABLE ENGINE ON CollapsingMergeTree TO langfuse;
GRANT TABLE ENGINE ON VersionedCollapsingMergeTree TO langfuse;
GRANT TABLE ENGINE ON Distributed TO langfuse;
GRANT TABLE ENGINE ON ReplicatedMergeTree TO langfuse;
GRANT TABLE ENGINE ON Log TO langfuse;
GRANT TABLE ENGINE ON Memory TO langfuse;
GRANT TABLE ENGINE ON Null TO langfuse;

-- 4. v4 新增：视图与列/索引变更（schema 迁移会替换视图、加列、加索引）
GRANT DROP VIEW ON default.* TO langfuse;
GRANT ALTER ADD COLUMN, ALTER MODIFY COLUMN, ALTER VIEW MODIFY QUERY ON default.* TO langfuse;
GRANT ALTER ADD INDEX, ALTER DROP INDEX, ALTER MATERIALIZE INDEX ON default.* TO langfuse;

-- 5. v4 新增：系统表读取（事件传播、后台回填、用量检测依赖）
GRANT SELECT ON system.parts TO langfuse;
GRANT SELECT ON system.mutations TO langfuse;
GRANT SELECT ON system.tables TO langfuse;
GRANT SELECT ON system.processes TO langfuse;
GRANT SELECT ON system.query_log TO langfuse;

-- 6. 合并控制（历史回填用到）
GRANT SYSTEM MERGES ON *.* TO langfuse;
GRANT SYSTEM SYNC REPLICA ON *.* TO langfuse;

-- 说明：官方升级文档中还有一条针对中间表的授权
--   GRANT SYSTEM SYNC REPLICA, SYSTEM MERGES, ALTER SETTINGS ON default.observations_pid_tid_sorting TO langfuse;
-- 该表由 v4 迁移创建，需在迁移完成后执行；全新部署无需历史回填，可暂不执行。
