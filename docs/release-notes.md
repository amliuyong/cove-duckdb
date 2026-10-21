# Cove DuckDB 1.0.0 发行说明与支持矩阵

首次正式发行。本文只列出已在实际 AWS 中验收的当前合同与能力。安装见[安装部署手册](installation.md)，使用见[用户手册](user-guide.md)，验收用例见 [UAT 测试用例](uat/test-cases.md)。计划中、尚未实现的能力单独列出。

## Changes after 1.0.0

Current source, not a new release: [#5](https://github.com/amliuyong/cove-duckdb/issues/5) replaces row-by-row loading of `after_write` / `after_ingestion` snapshots with typed Arrow batches. Both query and writer images install the same hash-locked pyarrow 24.0.0 wheel. Before fetching any rows, the writer checks row counts and a conservative JSON byte estimate in the original read transaction; oversized sources return `QUERY_SOURCE_QUOTA`. Limits remain 100,000 rows / 2 MiB / five seconds for capture. Exact encoding, receipt authority, no-recapture and sealed SQL isolation remain enforced.

Targeted AWS regression passed on 2026-10-21 in a fresh `us-west-2` environment at source `69201586e526ca5a2c507919a49cd9ba52587eba`, with the query task at 2 vCPU / 4 GiB. Public API queries over 10,210 four-column rows returned independently verified aggregates: `after_write` in 6.751 seconds, `after_ingestion` in 3.839 seconds, and `current` in 2.884 seconds. A source exceeding 2 MiB returned `QUERY_SOURCE_QUOTA` in 2.766 seconds. These observations include client polling and are not latency guarantees. Local native checks separately cover 100,000-row capture/load budgets, exact types and rejection before copying rows.

The 1.0.0 measurements and limitations below describe the published tag.

[#8](https://github.com/amliuyong/cove-duckdb/issues/8) makes the deployment region explicit (`COVE_REGION` / `AWS_REGION`), rejects conflicting settings and other partitions, uses the stack region for AWS resources and injects it into runtime services and native S3 secrets. Runtime resource namespaces include region to isolate account-global IAM roles; CloudFront OAC and policy names include the stack region to allow the same environment name in multiple regions. Executor contracts accept regional commercial ARNs/ECR addresses. Price snapshots are indexed by their actual region; an absent snapshot produces `UNKNOWN`, no borrowed or zero prices. The namespace change requires a fresh installation when moving from tag `v1.0.0`; use the original version's tools to uninstall its runtime resources first (see the installation guide's destructive-upgrade procedure).

Multi-region acceptance of this current source is pending. Only the published tag's `us-west-2` acceptance is established below; no additional region is marked supported until fresh installation, functional UAT, backup/isolated restore, uninstall and the original-region regression are complete. Regional prerequisites and source-version selection are described in the [installation guide](installation.md#33-区域前置条件).

## 发行身份

| 项目 | 值 |
| --- | --- |
| 版本 | `1.0.0`（`src/cove_duckdb/_version.py`） |
| Git tag | `v1.0.0` |
| GitHub Release | [v1.0.0](https://github.com/amliuyong/cove-duckdb/releases/tag/v1.0.0) |
| 源码 | tag 指向的提交；release `manifest.json` 记录其 commit / tree |
| 构建 | `scripts/build_product.py`，见[安装部署手册](installation.md#5-构建-release) |

release `manifest.json` 记录以下内容：

- 产品版本与源码 commit / tree；
- 每个组件 manifest 的 SHA-256 与镜像 ID；
- 原生存储镜像的仓库名与 digest。

组件包括：

- control ZIP：control / intake / writer / query 与流水线套件；
- writer 和 query 镜像；
- 环境构建器源码；
- Web：Query Editor 与 Admin Console。

GitHub Release 附带这些 manifest。镜像和 ZIP 本体由安装工具发布到目标账号的 ECR 与制品桶。

## 支持矩阵

| 维度 | 支持 | 说明 |
| --- | --- | --- |
| AWS 账号 | 单个账号 | 账号 ID 不写在源码中，由部署环境决定（`AWS::AccountId` / `COVE_ACCOUNT`）。1.0.0 在一个账号中完成验收，其他账号未单独验证 |
| 区域 | `us-west-2` | 写在模板和服务代码中；其他区域未验证 |
| CPU 架构 | ARM64（Graviton） | writer、query、计算 Task、Lambda 与运行环境构建都只构建 ARM64 |
| 原生存储 | DuckDB 1.5.6、duckdb-object-storage `f096ca1`、httpfs、aws 扩展 | 二进制 hash 固定于 [storage-lock.json](../runtime/storage-lock.json) |
| Python 运行环境 | CPython 3.12，linux_arm64 wheel | 依赖在发布前解析、按 hash 锁定，只接受 wheel |
| 执行器 | writer（`writer_short`）、标准 Lambda、ECS Fargate Task | Lambda Managed Instances 与 Durable Functions 尚未实现 |
| 浏览器 | Chromium 148（Playwright 1.60.0） | Query Editor 与 Admin Console 在该浏览器中验收；其他浏览器未验证 |
| 部署 | 每个环境一组栈，同一账号可装多个环境 | 见[安装部署手册](installation.md#2-部署组成) |

## 规格

| 组件 | 规格 |
| --- | --- |
| 写者 | ECS Fargate，每个环境 1 个 Task，2 vCPU / 4 GiB / 21 GiB 工作盘；DuckDB `memory_limit` 512 MB、2 线程；每个进程最多同时打开 2 个数据库 |
| 查询 | ECS Fargate Service，2 vCPU / 4 GiB / 21 GiB；每条查询在新进程、新原生实例中执行，不跨查询保留缓存 |
| 同步写代理 | VPC Lambda，256 MB，28 秒 |
| 接入 | Lambda，256 MB，60 秒；SQS FIFO |
| API | API Gateway HTTP API，默认路由限流 10 rps，突发 20 |
| 计算 profile | `writer_short` 30 秒；`*_lambda_standard` 900 秒；`*_ecs_medium` 1 vCPU / 4 GiB，最长 86,400 秒 |

## 能力

| 领域 | 能力 | 文档 |
| --- | --- | --- |
| 存储 | S3 上的原生 DuckDB 数据库、事务恢复、唯一写者与接管 | [AWS 产品设计](design/aws-product-design.md) |
| 访问 | Bearer API Key、空间与 scope 授权、委派、轮换、吊销 | [用户手册](user-guide.md)、[API 合同](design/api-contract.md) |
| 接入 | 不可变接入、ODS 幂等账本、接入状态、背压、DLQ 与受控重放 | [用户手册](user-guide.md) |
| 同步写 | 直接写表的 insert / upsert / update / delete、原生约束、原回执与 UNKNOWN 核对 | [同步写](design/synchronous-writes.md) |
| 查询 | 私网查询服务；current / published / 指定 release / after_write / after_ingestion 一致性 | [用户手册](user-guide.md) |
| 流水线 | SQL / Python DAG、固定输入、增量 / 分区重算、调度、取消、重试、Airflow | [流水线设计](design/pipeline-design.md)、[Python 任务合同](design/python-task-contract.md) |
| 控制台 | Query Editor、Admin Console | [用户手册](user-guide.md) |
| 治理 | 审计与诊断、保留与回收、配额、公平调度、成本 | [用户手册](user-guide.md) |
| 运维 | 安装、破坏性升级、开放 / 关闭、卸载；一致性备份与隔离还原；分段计时 | [安装部署手册](installation.md)、[性能报告](performance.md) |

## 限制

- **单一写者**：每个数据库只有一个写者。接入提交、同步写、导入和发布都在这个写者上排队，按公平调度交替执行。
- **活动空间上限**：每个环境只有一个写者进程，它在进程生命周期内最多打开 2 个空间的数据库。第三个空间的写入、接入提交或流水线导入返回 `503 WRITER_DATABASE_LIMIT`，直到写者重启（`admission.py close` 后再 `open`）。需要更多活动空间时，请部署多个环境。
- **外键与索引**：DuckDB 1.5.6 中，被外键引用的行，其索引列（显式索引、PRIMARY KEY、UNIQUE）和 LIST 列（`VARCHAR[]`）的值不能改变。这类更新以 `NATIVE_CONSTRAINT` 整批拒绝，其他列可以正常更新（见[同步写](design/synchronous-writes.md#2-注册权限与原生约束)）。
- **请求上限**：
  - API 请求体 1 MiB；
  - 一次接入最多 10,000 条记录；
  - 一次同步写最多 1,000 项，`timeout_ms` 最大 20,000；
  - SQL 文本最多 64 KiB。
- **查询**：
  - 每次查询只暂存 SQL 引用的数据集，暂存上限 2,000,000 行，按被引用数据集的全部行计算（与 `WHERE` 无关），超出返回 `QUERY_STAGING_LIMIT`；
  - 每个空间同时只执行 1 条查询，最多 8 条排队或执行中；整个环境最多 32 条排队、4 条同时执行；
  - 结果最多 10,000 行，保留 10 分钟；
  - `after_write` / `after_ingestion` 快照名义上限为 100,000 行、2 MiB，并有 5 秒复制预算。但 1.0.0 的沙箱逐行装载快照，约 1 万行、4 列的表就会超过 30 秒查询时限，返回 `QUERY_TIMEOUT`。这两种一致性只适合小表的写后读，大表请用 `current`。
- **查询结果保留配额**：整个环境最多保留 64 个结果（合计 64 MiB，每个空间 32 MiB），每个结果保留 10 分钟后回收。配额已满时，查询执行完会以 `429 QUERY_RESULT_RETENTION_QUOTA` 失败，所以持续查询吞吐约为每 10 分钟 64 个。
- **流水线输入**：每个任务最多 16 个输入；每个输入最多 100,000 行，一次输入导出最多 32 MiB，超出时以 `PARQUET_ROWS_QUOTA` / `PARQUET_BYTES_QUOTA` 失败。
- **备份**：备份在原生锁下导出全部表，期间写入需要等待；不支持跨产品版本还原。
- **升级**：不提供向后兼容、旧数据自动迁移或零停机升级。升级时先关闭，再部署新版本；已发布的流水线版本需要重新发布（`PIPELINE_VERSION_BINDING_CHANGED`）。
- **写入高峰下的查询**：写入高峰期间或刚结束时，读取同一张表的分析查询会明显变慢，可能超过 30 秒的默认时限（`QUERY_TIMEOUT`）。这时应设置更长的 `timeout_ms`（最大 300,000），或者错开写入高峰。
- **逐行执行**：同步写和长任务导入仍逐行执行语句，1,000 行的同步写约 5 秒，导入约 150 行/秒。
- **无服务目标**：没有约定的 SLA、RPO 或 RTO 目标。实测值只是上述规格下的基线，见[性能与容量基线](performance.md)。

## 测得基线（摘要）

以下是上述规格下的实测值，详见[性能报告](performance.md)：

- **同步写**：
  - 单行请求约 1.0 秒；
  - 写者串行提交，吞吐饱和在约 2.0–2.4 次提交/秒；
  - 每批 1,000 行时约 240–280 行/秒。
- **异步接入**：
  - 每批 1,000–5,000 条时约 570–1,970 条/秒，事务单元 0.6–1.9 秒；
  - 1 条一批时每秒 1–2 个批次。
- **查询**：
  - 每条查询使用新进程，服务端耗时 p50 约 4.2–5.7 秒，其中原生打开约 3 秒；
  - 结果保留配额实测为 64 个。
- **备份与还原**：
  - 备份约 15 秒（6.3 万行）；
  - 隔离还原约 3.5 分钟后可以查询，约 6 分钟后流水线重新发布。
- **成本**：写者与查询两个常驻 Task 约 0.158 USD/小时（公开单价，不含共享基础设施）。按数据档位的每月估算见[成本估算](cost-estimate.md)。

## 计划中，尚未实现

- Lambda Managed Instances 执行 profile。
- Durable Functions 多步骤任务。
- 按实测压力评估 core / serving 拆库。
- 多 DuckDB 分片与独立写者（只是方向，尚未设计）。

## 许可

项目源码、文档与品牌资产使用 [Apache-2.0](../LICENSE)。第三方组件（DuckDB、扩展、Python 依赖、基础镜像、Archify 等）保留各自的许可，见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。构建产物另附所含 Python 发行包自带的许可文件。
