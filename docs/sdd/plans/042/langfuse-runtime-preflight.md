# Langfuse 运行时预检与 loopback 恢复方案

## 当前运行状态：主会话持有（2026-10-23）

子任务曾启动的前台会话停止后，3000/8123实际返回HTTP000；旧PID和历史健康不能代表当前部署。主会话重新启动并持有进程，所有命令均复用既有组件、数据和配置，无安装、迁移、数据库清理或凭据修改：

- ClickHouse：工作目录`/Users/wjh/opt/clickhouse`，显式`--config-file=/Users/wjh/opt/clickhouse/config.xml -- --path=/Users/wjh/opt/clickhouse/data/ --listen_host=127.0.0.1`；session20709/PID83740，ping为Ok.。
- PostgreSQL：保留既有PID79169，未重启；监听127.0.0.1:5432。
- Redis：显式`--bind 127.0.0.1 --port 6379 --protected-mode yes --dir /tmp`；session84985/PID83764，PONG。
- MinIO：显式`--address 127.0.0.1:9002 --console-address 127.0.0.1:9003`及既有数据目录；session61216/PID83782。环境值仅从已有部署脚本安全注入，无输出或落盘；IPv4与IPv6监听均loopback，health成功。
- Worker：Node24路径及`HOSTNAME=127.0.0.1 PORT=3030 pnpm --filter worker run dev`；session49556/PID83835，health HTTP200。
- Web：在`vendor/langfuse/web`下使用Node24和已有dotenv/Next，`dotenv -e ../.env -- next dev --hostname 127.0.0.1`；session71694/PID83862，public health及ready均HTTP200。

已明确交接：子Agent不再启动、停止或清理上述主会话会话。Spec043的8000服务独立保持ready，不受本次恢复影响。旧错误工作目录生成的仓库根`access/`、`preprocessed_configs/`经确认无活动进程使用后，可恢复归档到`/private/tmp/spec042-startup-leftovers-6Y1edd/`，未提交、未删除既有ClickHouse专用目录或业务数据。

以下保留历史预检与恢复证据，PID/session不再作为当前在线证明。

> 执行角色：`backend-tester` / 部署诊断
> 执行日期：2026-10-23（Asia/Shanghai）
> 分支：`codex/spec042-offline-evaluation`
> 约束：预检阶段只读；随后按根会话授权以前台方式恢复既有服务。全程未安装依赖、未下载文件、未执行迁移、未修改仓库配置，未读取或打印 `.env` 内容及凭据。

## 1. 结论摘要

- 预检时 Langfuse web/worker 的 `3000/3030` 与四个基础设施端口 `8123/5432/6379/9002` 均未监听；授权恢复后见第 7 节，所有必要服务均已就绪。
- 源码、`.env`、锁文件、`node_modules`、Node 24.20.0、ClickHouse 二进制与数据目录、PostgreSQL 数据目录均存在；Redis、MinIO、pnpm 二进制也存在，因此没有“缺少安装包/二进制”的硬阻塞。
- `vendor/langfuse/.nvmrc` 是 `v24.6.0`，而 `deploy/langfuse/README.md` 与 `start-langfuse.sh` 要求并固定使用已存在的 `v24.20.0`。按启动脚本运行时不阻塞，但不能直接依赖 `nvm use` 的 `.nvmrc` 默认值。
- 现有启动脚本不满足“仅 loopback 监听”要求：MinIO 使用 `--address :9002`，Next.js `next dev` 默认 `0.0.0.0`，worker 的 `HOSTNAME` 默认 `0.0.0.0`。因此在获得根会话授权后，应按本文的显式绑定方案逐个启动，不能直接运行现有 `start-infra.sh` / `start-langfuse.sh`。

## 2. 依据与只读检查结果

### 2.1 部署前提

已读取：

- `deploy/langfuse/README.md`
- `deploy/langfuse/start-infra.sh`
- `deploy/langfuse/start-langfuse.sh`
- `deploy/README.md`

脚本声明的端口与前置：

| 组件 | 端口 | 脚本/说明中的前置 |
|---|---:|---|
| Langfuse web | 3000 | Node 24、源码、`.env`、基础设施已就绪 |
| Langfuse worker | 3030 | 同上 |
| ClickHouse HTTP | 8123 | `~/opt/clickhouse/clickhouse`、数据目录 |
| ClickHouse native | 9000 | 迁移/授权脚本的本地依赖端口，非四个主预检端口之一 |
| PostgreSQL | 5432 | `/opt/homebrew/opt/postgresql@17/bin/pg_ctl`、初始化的 `PGDATA` |
| Redis | 6379 | PATH 中的 `redis-server` |
| MinIO API | 9002 | PATH 中的 `minio`、MinIO 数据目录 |
| MinIO Console | 9003 | `start-infra.sh` 的附加 console 端口 |

### 2.2 预检时端口状态

只读命令使用 `lsof -nP -iTCP:<port> -sTCP:LISTEN -t` 检查。结果：

| 端口 | 状态 |
|---:|---|
| 3000 | `NOT_LISTENING` |
| 3030 | `NOT_LISTENING` |
| 8123 | `NOT_LISTENING` |
| 5432 | `NOT_LISTENING` |
| 6379 | `NOT_LISTENING` |
| 9002 | `NOT_LISTENING` |
| 9003 | `NOT_LISTENING` |

### 2.3 文件、目录与版本

仅检查路径存在性和版本，不输出 `.env` 内容：

| 项目 | 结果 |
|---|---|
| `vendor/langfuse` | 目录存在 |
| `vendor/langfuse/.env` | 文件存在；内容未读取 |
| `vendor/langfuse/package.json` / `pnpm-lock.yaml` | 均存在 |
| `vendor/langfuse/node_modules` | 目录存在；root `.pnpm`、`.bin/prisma`、`.bin/turbo` 存在 |
| `vendor/langfuse/web/node_modules/.bin/next` | 存在 |
| Node | `/Users/wjh/.nvm/versions/node/v24.20.0/bin/node` → `v24.20.0` |
| pnpm | `/Users/wjh/.nvm/versions/node/v24.20.0/bin/pnpm` → `11.22.0`，与 `package.json` 的 `packageManager` 一致 |
| Corepack | `0.35.0` 存在；未调用可能触发下载的 `corepack pnpm` |
| ClickHouse | `/Users/wjh/opt/clickhouse/clickhouse` → `26.4.6.3 (official build)` |
| ClickHouse data | `/Users/wjh/opt/clickhouse/data` 存在 |
| PostgreSQL | `pg_ctl` → `17.11 (Homebrew)` |
| PostgreSQL data | `/Users/wjh/opt/pgdata` 存在，`PG_VERSION=17` |
| Redis | `/opt/homebrew/bin/redis-server` → `8.10.1` |
| MinIO | `/opt/homebrew/bin/minio` → `RELEASE.2025-10-15T17-29-55Z` |
| MinIO data | `/Users/wjh/opt/minio-data` 存在 |
| `.nvmrc` | `v24.6.0`，与部署脚本固定的 `v24.20.0` 不同 |

依赖目录只做了存在性核对，没有运行安装、构建或包完整性修复；若启动时出现包缺失，应单独取得授权后再处理。

## 3. 现有脚本的 loopback 风险

### 3.1 `start-infra.sh`

- ClickHouse 启动命令只覆盖 `--path`，仓库内 `opt/clickhouse/config.xml` 没有 `<listen_host>`；不能据此保证仅监听 loopback。
- PostgreSQL 启动参数未显式指定 `-h 127.0.0.1`。
- Redis 命令未显式指定 `--bind 127.0.0.1`。
- MinIO 使用 `--address :9002` 和 `--console-address :9003`，明确是通配地址，不能在本任务约束下直接运行。
- ClickHouse 二进制缺失时脚本会执行外部 `curl` 下载；当前二进制已存在，但为避免误触发，本文没有运行该脚本。

### 3.2 `start-langfuse.sh`

- Node 路径固定为 `/Users/wjh/.nvm/versions/node/v24.20.0/bin`，该路径存在。
- 根目录 `pnpm run dev` 会启动 web 与 worker。`web/package.json` 的 `dev` 是 `next dev`，通过 `next dev --help` 核实其默认 hostname 为 `0.0.0.0`。
- `worker/src/env.ts` 的默认 `HOSTNAME` 为 `0.0.0.0`、默认 `PORT` 为 3030。
- 脚本不带 `--migrate` 时跳过迁移；本次恢复方案仍明确禁止 `--migrate`，不触碰数据库迁移。

## 4. 不下载、不迁移、不改配置的 loopback 恢复方案

以下是取得根会话授权后的操作顺序；第 7 节记录了本次实际执行结果。命令使用现有二进制与数据目录，所有监听参数显式指向 `127.0.0.1`；MinIO 凭据应从已授权的本地环境来源注入，本文不重复任何凭据。

1. 启动前再次用 `lsof` 确认 3000、3030、8123、5432、6379、9002、9003 均未占用；保留现有数据目录，不运行清理或迁移。

2. 分别启动基础设施，不运行 `deploy/langfuse/start-infra.sh`：

   - ClickHouse：从 `/Users/wjh/opt/clickhouse` 启动现有二进制，沿用 `--path=/Users/wjh/opt/clickhouse/data/`，并用 ClickHouse 的命令行配置覆盖显式设置 `listen_host=127.0.0.1`、HTTP 8123、native 9000；不下载二进制。
   - PostgreSQL：使用现有 `pg_ctl` 和 `/Users/wjh/opt/pgdata`，启动参数显式包含 `-p 5432 -h 127.0.0.1 -k /tmp`，并保留脚本要求的 `LC_ALL=C LANG=C`。
   - Redis：使用现有 `/opt/homebrew/bin/redis-server`，显式设置 `--bind 127.0.0.1 --protected-mode yes --port 6379`，日志仍写入本地临时路径。
   - MinIO：使用现有 `/opt/homebrew/bin/minio`，显式设置 `--address 127.0.0.1:9002 --console-address 127.0.0.1:9003`；数据目录使用 `/Users/wjh/opt/minio-data`，凭据从本地授权来源注入，不打印、不写入仓库。

3. 每个进程启动后只用 `lsof -nP -iTCP:<port> -sTCP:LISTEN` 核对监听地址为 `127.0.0.1`；若出现 `0.0.0.0`、`::` 或其他地址，立即停止该进程，不继续启动 Langfuse。

4. 基础设施全部通过 loopback 核验后，进入 `/Users/wjh/ResearchAgent/vendor/langfuse`，显式使用 `/Users/wjh/.nvm/versions/node/v24.20.0/bin` 在 PATH 前面，并分别启动：

   - web：使用 `pnpm --filter web run dev --hostname 127.0.0.1`，利用 Next 的显式 `--hostname`，不要使用根目录 `pnpm run dev` 的默认绑定。
   - worker：使用 `HOSTNAME=127.0.0.1 PORT=3030 pnpm --filter worker run dev`，覆盖 worker 默认的通配 hostname；其脚本仍从现有 `.env` 加载配置，但不改写该文件。

   两个进程均跳过 `--migrate` 和任何数据库迁移命令。

5. 最后核对 3000/3030 的监听地址均为 `127.0.0.1`，再从本机访问 `http://127.0.0.1:3000` 做最小就绪检查；不要访问外部地址或把端口暴露到局域网。

## 5. 预检时阻塞与放行条件

| 项目 | 状态 | 处理 |
|---|---|---|
| 服务未运行 | 预检时事实，不是安装缺失 | 已获根会话授权并按第 4 节逐个启动，结果见第 7 节 |
| Node 24.20.0 | 满足 | 使用启动脚本固定路径，不使用 `.nvmrc` 的 v24.6.0 |
| pnpm / node_modules | 预检满足 | 不执行安装；若启动时报缺包，另行授权处理 |
| ClickHouse / PostgreSQL / Redis / MinIO 二进制 | 均满足 | 不下载；使用现有版本 |
| 仅 loopback 监听 | 现有脚本不满足 | 已采用第 4 节显式 host/address 参数；MinIO 另有 `[::1]` IPv6 loopback，未发现非 loopback 地址 |
| 迁移 | 未执行 | 本次恢复不带 `--migrate`，仍未执行迁移 |

## 6. 诊断边界

预检阶段没有启动进程；授权后仅启动本报告第 7 节列出的既有 Langfuse 依赖和 web/worker 前台会话。全程没有安装包、下载文件、执行迁移、读取真实用户 trace、写 score 或修改仓库配置；`.env` 内容和凭据未读出到报告。未启动 ResearchAgent、Qdrant、Ollama 或 8000 端口服务。

进展日志：`.codebuddy/agent-logs/spec-042/task-04/backend-tester/20261023-005736.md`

## 7. 授权后实际恢复记录（2026-10-23）

根会话随后授权按本文方案恢复既有服务。以下命令均以前台 session 保持，使用既有二进制/数据；命令中的 MinIO 凭据只从现有 `deploy/langfuse/start-infra.sh` 部署来源注入子进程环境，值不落盘、不打印，本文不展示。

### 7.1 基础设施

| 组件 | 实际命令（去敏） | session / PID | 实际监听 | 健康结果 |
|---|---|---|---|---|
| ClickHouse | `cd /Users/wjh/opt/clickhouse && exec ./clickhouse server -- --path=/Users/wjh/opt/clickhouse/data/ --listen_host=127.0.0.1 --http_port=8123 --tcp_port=9000 --logger.log=/tmp/langfuse-clickhouse.log` | session `99803` / PID `70310` | `127.0.0.1:8123`, `127.0.0.1:9000`；另有同 PID 的 loopback `9004/9005` | `GET http://127.0.0.1:8123/ping` → body `Ok.`, HTTP 200 |
| PostgreSQL | `LC_ALL=C LANG=C exec /opt/homebrew/opt/postgresql@17/bin/postgres -D /Users/wjh/opt/pgdata -p 5432 -h 127.0.0.1 -k /tmp` | session `90435` / PID `70348` | `127.0.0.1:5432` | `pg_isready -h 127.0.0.1 -p 5432` → accepting connections |
| Redis | `exec /opt/homebrew/bin/redis-server --bind 127.0.0.1 --protected-mode yes --port 6379 --dir /tmp` | session `38535` / PID `70413` | `127.0.0.1:6379` | `redis-cli -h 127.0.0.1 -p 6379 ping` → `PONG` |
| MinIO | `env MINIO_ROOT_USER=<existing deployment value> MINIO_ROOT_PASSWORD=<existing deployment value> exec /opt/homebrew/bin/minio server --address 127.0.0.1:9002 --console-address 127.0.0.1:9003 /Users/wjh/opt/minio-data`（输出重定向到 `/tmp/langfuse-minio.log`） | session `85342` / PID `70434` | `127.0.0.1:9002`, `127.0.0.1:9003`；同 PID 另有 `[::1]:9002`（IPv6 loopback） | `GET http://127.0.0.1:9002/minio/health/live` → HTTP 200 |

逐项顺序为 ClickHouse → PostgreSQL → Redis → MinIO；每项在下一项启动前均已核对端口和健康状态。没有运行 `start-infra.sh`，没有下载、安装或迁移。

启动日志中的既有数据提示：PostgreSQL 检测到上次非正常停止并完成自动 WAL 恢复后进入 accepting connections；ClickHouse 报告既有数据的 unclean restart，并忽略若干旧 statistics 文件格式告警，但 HTTP `/ping` 成功。未执行任何修复、清理或迁移。

### 7.2 Langfuse web / worker

| 组件 | 实际命令 | session / PID | 实际监听 | 健康结果 |
|---|---|---|---|---|
| web | `env PATH="/Users/wjh/.nvm/versions/node/v24.20.0/bin:$PATH" /Users/wjh/.nvm/versions/node/v24.20.0/bin/pnpm --filter web run dev --hostname 127.0.0.1` | session `15358` / PID `70864` | `127.0.0.1:3000` | `GET http://127.0.0.1:3000` → HTTP 200 |
| worker | `env PATH="/Users/wjh/.nvm/versions/node/v24.20.0/bin:$PATH" HOSTNAME=127.0.0.1 PORT=3030 /Users/wjh/.nvm/versions/node/v24.20.0/bin/pnpm --filter worker run dev` | session `76146` / PID `71085` | `127.0.0.1:3030` | `GET http://127.0.0.1:3030/` → HTTP 200；日志明确 `Listening: http://127.0.0.1:3030` |

web 首次尝试因多传一个 pnpm 分隔符而退出（`next dev -- --hostname`，退出码 1），未留下监听；随后用上表命令成功启动。未运行根目录 `pnpm run dev`，未使用 `--migrate`。worker 日志显示 `No background migrations to run`，没有执行迁移命令。

### 7.3 最终汇总

最终 `lsof` 核对：

- 3000 → PID 70864，`127.0.0.1:3000`；
- 3030 → PID 71085，`127.0.0.1:3030`；
- 8123/9000/9004/9005 → PID 70310，均为 `127.0.0.1`；
- 5432 → PID 70348，`127.0.0.1:5432`；
- 6379 → PID 70413，`127.0.0.1:6379`；
- 9002/9003 → PID 70434，IPv4 为 `127.0.0.1`，另有 `[::1]:9002` IPv6 loopback。

最终本地健康：web=200、worker=200、ClickHouse=`Ok.`/200、PostgreSQL=accepting、Redis=`PONG`、MinIO=200。未访问真实用户 trace，未运行评测或 score 写回，未启动 ResearchAgent、Qdrant、Ollama 或 8000 端口服务。

## 8. Spec-042 真实验收授权后的追加记录（2026-10-23 04:27–04:30 Asia/Shanghai）

本节覆盖第 7 节之后、根会话明确授权的同一分支运行。第 7 节是历史预检/恢复记录；本节的最新 PID、session 和 HTTP 结果以实际验收时刻为准。命令未包含凭据值，既有 `vendor/langfuse/.env` 只在子进程内存中映射需要的环境变量。

### 8.1 实际启动与监听

| 组件 | 实际命令（去敏） | session / PID | 最终监听 |
|---|---|---|---|
| ClickHouse | `/Users/wjh/opt/clickhouse/clickhouse server --config-file=/Users/wjh/opt/clickhouse/config.xml -- --path=/Users/wjh/opt/clickhouse/data/ --listen_host=127.0.0.1`，工作目录 `/Users/wjh/opt/clickhouse` | foreground session `84204` / PID `79822` | `127.0.0.1:8123`（另有 native/兼容协议 loopback 端口） |
| PostgreSQL | `LC_ALL=C LANG=C pg_ctl -D /Users/wjh/opt/pgdata -l /tmp/langfuse-postgres.log -o '-p 5432 -k /tmp -h 127.0.0.1' -w start` | command exit 0 / PID `79169` | `127.0.0.1:5432` |
| Redis | `/opt/homebrew/bin/redis-server --bind 127.0.0.1 --port 6379 --protected-mode yes --dir /tmp --logfile /tmp/langfuse-redis.log` | foreground session `84659` / PID `79184` | `127.0.0.1:6379` |
| MinIO | `MINIO_ROOT_USER=<existing> MINIO_ROOT_PASSWORD=<existing> minio server --address 127.0.0.1:9002 --console-address 127.0.0.1:9003 /Users/wjh/opt/minio-data` | foreground session `22494` / PID `79197` | IPv4 `127.0.0.1:9002/9003`，IPv6 `[::1]:9002`（loopback） |
| Langfuse worker | `HOSTNAME=127.0.0.1 PORT=3030 pnpm --filter worker run dev`，Node 24.20.0 | foreground session `87762` / PID `79363` | `127.0.0.1:3030` |
| Langfuse web | `dotenv -e ../.env -- next dev --hostname 127.0.0.1`，Node 24.20.0 | foreground session `16179` / PID `80339` | `127.0.0.1:3000` |
| Ollama | pre-existing process, not started/changed | PID `2882` | existing `11434` listener; accessed only via `127.0.0.1` |

初次 ClickHouse 启动时因工作目录不匹配相对 `access/` 路径，既有用户认证返回 403；仅停止本次启动的 PID `79491`，未改配置或数据，随后从现有配置目录重启并认证成功。Web 初次默认绑定通配地址，已停止本次 PID 并以 `--hostname 127.0.0.1` 重启；当前 `lsof` 仅显示上述 loopback 地址。没有运行 `start-infra.sh`，没有安装、下载、迁移、清理数据或停止无关进程。

### 8.2 实际健康与认证结果

| 请求/检查 | 真实结果 |
|---|---|
| `GET http://127.0.0.1:8123/ping` | HTTP 200，body `Ok.` |
| ClickHouse existing `.env` account auth | HTTP 200；仅打印状态，未打印凭据 |
| `GET http://127.0.0.1:9002/minio/health/live` | HTTP 200 |
| `GET http://127.0.0.1:3030/api/health` | HTTP 200，`status=ok` |
| `GET http://127.0.0.1:3000/` | HTTP 200，7373 bytes（正文只写入临时私有路径用于字节数核对） |
| `GET http://127.0.0.1:3000/api/public/health` | HTTP 200 |
| `GET http://127.0.0.1:3000/api/public/ready` | HTTP 200 |
| authenticated `GET http://127.0.0.1:3000/api/public/traces?limit=1` | HTTP 200，真实 trace 列表元数据可读 |
| `GET http://127.0.0.1:11434/api/tags` | HTTP 200；qwen3.5:9b 与 qwen3.8:27b 已存在 |

### 8.3 真实验收 session 产物

- chat-quality run：`docs/sdd/plans/042/runs/20261023-0431-real-e2e/`；canonical CLI exit `1`，score POST 已写入但 bounded exact verify 失败，终态报告为 `failed`。
- memory skip run：`docs/sdd/plans/042/runs/20261023-0435-memory-skip/`；canonical CLI exit `0`，真实 `no_prior_context` 被 `SKIPPED`，`written=0`，无 score POST。
- 详细 API artifact：[20261023-0431-real-e2e/api-e2e.md](runs/20261023-0431-real-e2e/api-e2e.md)。
- 本追加仅记录命令、PID、监听地址、session 和健康/认证状态；没有写入凭据、trace 正文或隐藏模型输出。

## 9. Root-owned acceptance runtime handoff (2026-10-23 04:42 Asia/Shanghai)

本节是根会话重新持有服务后的最新运行时记录。当前验收任务未启动、停止或清理这些进程；仅读取健康状态并使用其 loopback API。

| 组件 | root-owned session / PID | 监听与健康 |
|---|---|---|
| ClickHouse | session `20709` / PID `83740` | 既有 config/data，`127.0.0.1:8123`，HTTP `/ping` 200 |
| PostgreSQL | existing PID `79169` | `127.0.0.1:5432` |
| Redis | session `84985` / PID `83764` | `127.0.0.1:6379` |
| MinIO | session `61216` / PID `83782` | `127.0.0.1:9002/9003`，loopback live health 200 |
| Langfuse worker | session `49556` / PID `83835` | `127.0.0.1:3030`，`/api/health` 200 |
| Langfuse web | session `71694` / PID `83862` | `127.0.0.1:3000`，`/`, `/api/public/health`, `/api/public/ready` 200 |

启动命令边界仍为：ClickHouse 从 `/Users/wjh/opt/clickhouse` 使用既有 config/data；worker 使用 `HOSTNAME=127.0.0.1 PORT=3030 pnpm --filter worker run dev`；web 使用 `dotenv -e ../.env -- next dev --hostname 127.0.0.1`。项目密钥只从既有 `vendor/langfuse/.env` 的 `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `LANGFUSE_INIT_PROJECT_SECRET_KEY` 在子进程内存中映射，未打印或写入报告。

本次新 run：`docs/sdd/plans/042/runs/20261023-0442-real-e2e-145f9d6/`。CLI exit `0`，一条真实 `chat_quality` score 写入并 canonical verified；同一 score 的六次 exact GET 均 HTTP 200。UI 回看因 macOS 锁屏未完成，详见 run 内 `api-e2e.md`；不把 API 成功冒充 UI 可见。
