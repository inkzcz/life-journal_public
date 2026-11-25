# 新安装指南（v5.1.11）

正式附件以 [v5.1.11 Release](https://github.com/inkzcz/life-journal_public/releases/tag/v5.1.11) 实际内容为准；工作流完成前不要把测试候选当作正式产物。原创许可证与第三方权利边界见随附 LICENSE、COPYRIGHT.md 和对应源码包。
[已知限制](known-limitations.md)尤其UPGRADE-001仍适用，不将本指南用于覆盖已有生产目录。

## 下载正式附件，无需在 Windows 构建

下载 `life-journal-app-v5.1.11-amd64.tar`、`SHA256SUMS.txt`、`manifest.json`、
`life-journal-deploy-v5.1.11.zip`，并保存同处提供的对应源码与许可证包。
在 PowerShell 中用 `Get-FileHash .\life-journal-app-v5.1.11-amd64.tar -Algorithm SHA256`
核对 SHA256SUMS 中该文件的实际值，部署 ZIP 也须核对。
极空间 Docker 界面导入唯一业务 TAR，或在部署者自己的本地 Docker 执行
`docker load -i life-journal-app-v5.1.11-amd64.tar`。确认镜像为 `life-journal:v5.1.11`、Linux/amd64。
解压部署 ZIP 到新的目录；按下文配置 `IMAGE_TAG=v5.1.11` 及已经准备好的 PG17 镜像。
此路径不需要 Windows 安装 Git、Python 或 Docker Desktop 来构建镜像。

Windows Docker Desktop 与极空间 Z4S 均为**待所有者本地验收**，不是已通过的实机结果。

## 可选：取得源码并自行构建

在隔离的新部署目录执行：

```sh
git clone https://github.com/inkzcz/life-journal_public.git life-journal-source
cd life-journal-source
git checkout --detach v5.1.11
```

使用公开仓库的正式 Annotated Tag，并核对 Release 的来源提交。只使用该新仓库自身的历史；不添加原私有remote或导入旧refs。
清单里的准备来源SHA不是新仓库的初始提交身份。源码 ZIP 身份校验以既有工具为准，不接受手填SHA绕过。

按README的PowerShell或Bash命令用干净Git checkout构建。目标固定linux/amd64，业务标签为v5.1.11-candidate.加新仓库短SHA。
Windows需Git/Python/Docker Desktop；Linux需本地Engine/Buildx。构建需要依赖网络；构建和运行验证状态以 release-v5.1.11.md 为准。
工具保留本地连接限制、实时脱敏日志、默认不加--pull、原生退出码和冲突保护，不覆盖/删除旧镜像或交付目录。

本地工具只生成一个life-journal-app-候选标签-amd64.tar及SHA256SUMS、.sha256、images.json、manifest.json。
保留完整输出目录。用scripts/image_private_keys.py对TAR全部镜像层扫描，按工具--verify-only入口核对来源、SHA256、单镜像身份及两次真实docker load。
新仓库名只影响来源URL/身份权威；业务镜像仍叫life-journal，不能改成三个分别发布的角色镜像。

## 数据库与新部署目录

1. 管理员独立准备一个官方PostgreSQL17本地镜像，记录精确镜像引用（优先digest）。缺失时先自行准备；业务工具不处理数据库镜像。
2. 在新部署目录保存Compose及私下的.env（从.env.example复制）。自行填写POSTGRES_PASSWORD、随机SETUP_KEY、IMAGE_TAG、已有POSTGRES_IMAGE。
3. DB_DATA_DIR、MEDIA_DATA_DIR、BACKUP_DATA_DIR指定各自新目录，不互相包含。不要把旧命名卷换成空bind目录；不要递归修改旧目录权限。
4. 用`docker compose --env-file .env config --quiet`检查；不要公开完整展开的配置或凭据。
5. 导入/验证唯一业务TAR后，用`docker compose --env-file .env up -d --pull never`启动新栈，等待DB→Maintenance→API→Web健康门禁。

三个业务角色共用life-journal同一标签。数据库/API/Maintenance不发布宿主端口，Web默认127.0.0.1:18080。
PG17镜像若不在本地，pull_policy:never必须停止；不得移除限制或声称它已经离线就绪。
目录初始准备后业务以UID/GID10001运行，保持已有权限策略。

## 初始化和验证

通过受控HTTPS创建自己的管理员，验证登录、文章/照片权限、容器重启和完整备份，完成后移除SETUP_KEY。
如只在本机HTTP回环验收，显式设置COOKIE_SECURE=false；正式HTTPS恢复true。不要把回环验收端口直接暴露公网。
恢复演练只用新空库/媒体目标，见backup-restore.md。已有站点升级必须另循upgrade.md，不能假定同版本号跨新构建兼容。

首次公开提交的云端 CI 已通过；Windows Docker Desktop 与 NAS 验收独立记录，不能由 Linux 结果替代。安装操作由部署者确认目标后自行执行，不自动访问任何NAS或真实数据。
