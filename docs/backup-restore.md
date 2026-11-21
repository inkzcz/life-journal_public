# 备份与空目标恢复

运行数据、应用完整备份和独立存储副本分开。备份含数据库导出、媒体、构建/Schema 版本和哈希，默认不加密。配置及匹配镜像另行私密保管，不提交 Git。

自己的正常部署可执行：

```sh
docker compose --env-file .env exec -T maintenance python -m app.backup create
docker compose --env-file .env exec -T maintenance python -m app.backup verify --id BACKUP_UUID
```

用实际返回编号替换 BACKUP_UUID。创建、文件校验、真实恢复是不同结果；首次真实恢复前不淘汰旧副本，之后保护最后一次验证副本。外部复制任务独立核验。

恢复必须是另一个项目名和新的空 DB/媒体目录；业务镜像与备份 app_version 完全匹配。设置自己的私密 .env，确认 DB_DATA_DIR、MEDIA_DATA_DIR 不指向原目录；RESTORE_INPUT_DIR 指向已核验备份根目录，通过 compose.restore.yaml 只读提供给 Maintenance。

```sh
# 以下命令仅用于已核验的独立新项目，不能套用到生产项目。
docker compose -p restore-check -f compose.yaml -f compose.restore.yaml up -d --pull never --wait db
# 仅准备新的空媒体目录后降权，不启动 API。
docker compose -p restore-check -f compose.yaml -f compose.restore.yaml run --rm --no-deps api python -c 'print("new empty media directory prepared")'
docker compose -p restore-check -f compose.yaml -f compose.restore.yaml run --rm --no-deps maintenance python -m app.backup restore --id BACKUP_UUID --confirm-empty-target
```

核对 DB/媒体指纹与恢复报告。完成后移除恢复 override，保持新目标映射，先只启动 API/Web 验证登录、文章、图片及权限。复核恢复的清理/备份/通知配置后才启动 worker，避免验收连接真实通知目标。

原库不参与目标恢复连接。普通备份只接受原构建；跨构建升级走获批保护机制。此前 Maintenance 故障仍未解决，这里不提供绕过保护的升级命令。
