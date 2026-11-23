# 升级与回滚

**未解决：此前 v5.1.8 → v5.1.9 Maintenance 升级失败，原因及位置待确认；不宣称历史故障已修复。所有者接受其不阻塞正式发行，但这不代表现有数据库已通过升级验收。** 分析、保护机制及复现边界见 [UPGRADE-001](upgrade-001.md)。真实旧库须先在独立副本验证，Windows Docker Desktop 和极空间 Z4S 仍待本地验收。

完整 v5.1.9 功能和迁移链保留，目标为 0021_anniversary_calendar。原有 0016/0017/0018 → Head 的哈希授权、完整保护包、独立 PG17 恢复/试迁移、事务升级和 API 门禁不变；代码存在不代表此前故障已解决。

由部署者完成副本验证并决定生产操作后，顺序为：停止写入；保存原配置/Compose/镜像/精确数据映射；用原版本制作完整备份并在独立空目标恢复；核对正式单业务 TAR 的身份、架构和 SHA256；保留数据库镜像和原目录，只更换经审核业务镜像/配套 Compose；等待四容器门禁并验证旧文章、媒体、行程、模板、权限、日历和备份。

不把原命名卷换成空 bind 目录，不换数据库镜像冒充应用升级，不执行 down -v、stamp 或关闭门禁。失败保留日志、升级保护包和原库；查明原因后再由管理员改重试令牌，仍须完成全部保护检查。

新无历史仓库产生新的构建身份。版本号相同不代表普通备份可跨构建恢复；普通备份要求原构建、Schema、PG 主版本匹配。升级 bundle 与普通备份格式不同。保留旧镜像/私密配置，不能依赖新公开仓库重建原私有构建。

回滚不做破坏性 downgrade：停止新写入并保全新增内容，用升级前备份及匹配旧镜像恢复到新空数据库/媒体，独立验证后人工切换。旧备份不含升级后新增内容，不能声称无损回退；原库、原媒体和可恢复副本保留。

## v5.1.9 → v5.1.10（同 Schema）

正式公开 v5.1.9 的合成数据演练保留非空文章/动态字段/卡片/媒体/行程和 UUID，升级后仍为
`0021_anniversary_calendar`；v5.1.10 不新增表、迁移或修改历史迁移。此证据不是实际用户库或 UPGRADE-001 的验收。

1. 在原部署项目停止外部写入，私下另存 `.env`、完整 Compose/override、项目名、镜像 ID 和精确目录映射；保留 `life-journal:v5.1.9`，不删/重标旧镜像。
2. 用仍在运行的旧版本执行下列命令，保存返回的备份 ID，并将整份备份、媒体和私密配置另存到独立存储。完整备份包含 DB 与媒体；配置不在其中，必须另存。已有备份不要覆盖。

   ```sh
   docker compose --env-file .env exec --user 10001:10001 -T maintenance python -m app.backup create
   docker compose --env-file .env exec --user 10001:10001 -T maintenance python -m app.backup verify --id BACKUP_UUID
   ```

   依 backup-restore.md 使用**精确旧镜像**在独立项目、新空库/媒体目标验证恢复，不能让副本外联真实通知。
3. 从 v5.1.10 Release 下载唯一业务 TAR、SHA256SUMS、manifest/images、部署 ZIP、对应源码/法律包和说明。用 `Get-FileHash` 或 `sha256sum --check SHA256SUMS.txt` 核对下载；后者要求已下载清单中全部附件。
4. 在 NAS Docker 界面导入 `life-journal-app-v5.1.10-amd64.tar`，或在部署者本地执行 `docker load -i life-journal-app-v5.1.10-amd64.tar`。核对标签/来源；`docker image inspect life-journal:v5.1.10 --format '{{.Os}}/{{.Architecture}}'` 应为 `linux/amd64`。不要构建三个角色镜像，不更换 DB 镜像。
5. 在原部署目录/同一 Compose 项目，仅将私密配置的 `IMAGE_TAG` 从 `v5.1.9` 改为 `v5.1.10`。不直接用新部署 ZIP 覆盖已有配置、override、卷或项目名；保留原 PostgreSQL17 镜像和全部 DB/MEDIA/BACKUP 路径。清除 shell 中非预期同名覆盖值，私下核对，不公开打印配置。
6. 用原项目执行（如原来指定了 `-p` 或多个 `-f`，继续使用相同参数）：

   ```sh
   docker compose --env-file .env config --quiet
   docker compose --env-file .env stop web api maintenance
   docker compose --env-file .env up -d --pull never
   docker compose --env-file .env ps
   ```

   已导入正式镜像，无需 `build`。等待 DB → Maintenance → API → Web；若 Maintenance 失败，保留脱敏错误并停止，不强启 API，不清空数据，不关闭版本校验。
7. 核对三个业务容器的实际镜像均为 `life-journal:v5.1.10`；在站点“版本更新”及 管理员登录后的 `/api/blog/build-info` 核对 `version` 为 `5.1.10`、`revision` 与 Release 来源一致，`/api/health` 成功。用原数据库用户名/库名在 DB 容器只读查询 `SELECT version_num FROM alembic_version;`，应仍为 `0021_anniversary_calendar`。逐项检查旧文章/模板/字段/卡片、图片、行程、模式切换、新文章默认类型和通知编辑，再用新版创建并验证新备份。

## v5.1.10 回滚至 v5.1.9

- 立即停止外部写入和业务服务，保留当前库、媒体、新写入和脱敏日志；不得 `down -v`、删目录、`stamp`、关闭迁移检查或做破坏性 downgrade。
- **只有已确认 Schema 相同且升级后没有任何写入**时，才能将原配置 `IMAGE_TAG` 改回保留的精确 v5.1.9 镜像，再按原健康门禁启动。若有新写入、维护任务修改或状态不明，不把直接回用当作安全恢复方案。
- 状态不明时使用升级前完整备份、精确旧构建和匹配 PG17，在新的空 DB/媒体目录及独立项目恢复，按 backup-restore.md 先验证、审核恢复配置，再人工切换；保持原目标可恢复。旧备份不包含升级后新增内容，需另行保全/评估，不能承诺无损。
- 不将新版普通备份强制导入旧构建；构建/Schema/PG匹配门禁继续生效。真实生产操作由所有者决定和执行，自动发布不连接 NAS。
