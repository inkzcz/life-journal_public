# 备份与空目标恢复

运行数据、应用完整备份和独立存储副本分开。备份含数据库导出、媒体、构建/Schema 版本和哈希，默认不加密。配置及匹配镜像另行私密保管，不提交 Git。

自己的正常部署可执行：

```sh
docker compose --env-file .env exec --user 10001:10001 -T maintenance python -m app.backup create
docker compose --env-file .env exec --user 10001:10001 -T maintenance python -m app.backup verify --id BACKUP_UUID
```

用实际返回编号替换 BACKUP_UUID。必须显式指定 UID/GID：`exec` 不会重新执行入口的降权逻辑，省略 `--user` 会以镜像默认 root 身份生成备份，之后 UID10001 恢复容器可能无法读取。
不要递归 chown 已有备份来掩盖问题；已有错误属主的备份须保留并由管理员另行审核处理。
创建、文件校验、真实恢复是不同结果；首次真实恢复前不淘汰旧副本，之后保护最后一次验证副本。外部复制任务独立核验。

恢复必须是另一个项目名和新的空 DB/媒体目录；业务镜像与备份 app_version 完全匹配。设置自己的私密 .env，确认 DB_DATA_DIR、MEDIA_DATA_DIR 不指向原目录；RESTORE_INPUT_DIR 指向已核验备份根目录，通过 compose.restore.yaml 只读提供给 Maintenance。
请在干净终端核对实际绑定目录和镜像引用；已导出的 shell 变量优先于 `--env-file`，不能假定指定新 .env 就隔离了原部署。`config --quiet` 只验证配置语法，不证明目录是新空目标。

```sh
# 以下命令仅用于已核验的独立新项目，不能套用到生产项目。
docker compose -p restore-check -f compose.yaml -f compose.restore.yaml up -d --pull never --wait db
# 仅准备新的空媒体目录后降权，不启动 API。
docker compose -p restore-check -f compose.yaml -f compose.restore.yaml run --rm --no-deps api python -c 'print("new empty media directory prepared")'
docker compose -p restore-check -f compose.yaml -f compose.restore.yaml run --rm --no-deps maintenance python -m app.backup restore --id BACKUP_UUID --confirm-empty-target
```

核对 DB/媒体指纹与恢复报告。在启动常驻服务前，由管理员在隔离的新目标中审核恢复的清理/备份/通知配置；需要停用的真实通知目标应先处理，验收环境不允许外联真实服务。
注意：本 Compose 中 API 依赖 Maintenance，Web 又依赖 API；`up api web` 也会启动 Maintenance，不能把它当作“只启动 API/Web、不运行 worker”。不要通过 `--no-deps` 或修改健康门禁绕过协调。
确认配置和隔离条件后，再移除恢复 override、保持新的目标映射，启动完整健康门禁栈并验证登录、文章、图片及权限。未经人工审核不要启动恢复后的 worker，也不要复用原生产项目。

原库不参与目标恢复连接。普通备份只接受原构建；跨构建升级走获批保护机制。此前 Maintenance 故障仍未解决，这里不提供绕过保护的升级命令。
