# Life Journal v5.1.9

独立开源版本：私人文章/草稿、TipTap与Markdown编辑、旅行与地点、照片流/相册、公历/农历纪念日、主题及后台管理。
原创源码采用 GPL-3.0-or-later；第三方保留各自原有许可、版权和署名。Copyright (C) 2026 inkzcz。

## 下载与导入

- `life-journal-app-v5.1.9-amd64.tar`：唯一 Linux/amd64 业务镜像，标签 `life-journal:v5.1.9`。
- `life-journal-source-and-licenses-v5.1.9.tar.gz`：本次实际构建的应用源码、精确对应源码/补丁、构建及库替换说明、版权/NOTICE和验证收据。
- `SHA256SUMS.txt`、`manifest.json`、`images.json`：资产SHA256及构建/镜像身份。
- `life-journal-deploy-v5.1.9.zip`：Compose、空白配置示例及部署文档。
- `INSTALL.md`、`UPGRADE.md`、`KNOWN_LIMITATIONS.md`：安装、升级与限制。

API、Web/Caddy、Maintenance 是使用同一个业务镜像的三个独立容器。数据库是第四个容器；
**PostgreSQL 17 官方镜像由 NAS 环境独立准备，不包含在业务 TAR，也不会隐式拉取。**

在下载目录核对SHA256，然后在极空间Docker界面导入TAR（或在已授权的本地Docker运行
`docker load -i life-journal-app-v5.1.9-amd64.tar`）。确认标签和架构后，在新的部署目录解压部署包、
复制 `.env.example` 为私有 `.env`，填写自己的密码、随机初始化密钥及数据路径。
设置 `IMAGE_TAG=v5.1.9` 和 NAS 已有的 PostgreSQL17 镜像引用。
只对本机执行 `docker compose --env-file .env config --quiet`，不要公开展开后的私有配置。
启动使用 `docker compose --env-file .env up -d --pull never`，等待 DB → Maintenance → API → Web。
Web默认绑定回环地址，按安装说明配置受控访问与HTTPS；没有默认管理员账号或密码。

## 构建与分发

- Debian12 / Python3.12 / PostgreSQL17完整维护工具，Node仅参与前端构建。
- Psycopg C扩展从公开源码编译并动态链接系统libpq，未打包psycopg-binary的独立原生库。
- 原始通知/当前包身份随镜像与Web `/legal/` 提供；对应源码包绑定本次TAR的SHA256和构建提交。
- 同处提供完整适用源码，不签发未准备履行的书面source offer，不限制用户GPL/LGPL修改或库替换权利。
- Linux验证包括单TAR/重复导入、全部镜像层、四容器健康、持久化、备份及独立恢复、Psycopg动态替换与Pillow LGPL shim实际重编译/重链接。
  具体实际结果与版本在附件内的验证收据中；没有执行的项目不记为通过。

## 已知限制

- Windows Docker Desktop、极空间Z4S：**待所有者本地验收**。所有者明确接受不将这两项作为正式发布前置条件；Linux不替代实机结果。
- **UPGRADE-001**：历史 v5.1.8 → v5.1.9 Maintenance 失败原因仍未确认，不宣称已修复。
  合成0018→0021数据库的备份/恢复/试迁移成功，不等同于真实历史故障已复现或所有旧库都可升级。
- 现有 v5.1.8 用户先备份数据库与媒体，在独立副本验证。保留所有版本、Alembic、恢复演练和迁移安全门禁；
  Maintenance失败时保留日志并停止升级，不删除数据卷、不绕过Alembic、不强行启动API。
- 普通备份可能严格匹配构建、Schema及PG主版本；仅版本号相同不保证旧私有镜像备份与新公开构建互换。
- 本次发布未访问或更改任何 NAS、生产数据库、照片、媒体或真实备份。

安装及升级路径以随附文档为准；正式附件仅在本次已授权发布工作流完成后存在。
