# Life Journal · 私人生活档案

**v5.1.9 源码候选，尚非正式Tag/Release。** 所有者已明确批准并执行A阶段：有权许可的原创源码以GPL-3.0-or-later授权，见[LICENSE](LICENSE)和[COPYRIGHT.md](COPYRIGHT.md)。
拟议仓库为 `inkzcz/life-journal_public`；仓库名和本文件不构成创建、上传或公开权限。

Life Journal 是可自行部署的私人Blog，提供文章与草稿、TipTap/Markdown、旅行/地点/行程、照片流与独立相册、
公历/农历纪念日及提醒、主题外观和后台管理。前端Vue3，后端FastAPI，数据库PostgreSQL17。
登录与角色权限、迁移保护、完整备份和独立空目标恢复机制保留，个人内容不会随源码公开。

## 首次源码范围与已激活的原创授权

Copyright (C) 2026 inkzcz。GPL-3.0-or-later仅覆盖所有者有权许可、受版权保护的原创源码，包括改编文件中有权许可的原创增量。
本轮正式授权记录见[PHASE_A_AUTHORIZATION.json](licensing/PHASE_A_AUTHORIZATION.json)；历史激活方案与通知草案保留作审核背景，当前法律通知以根LICENSE和COPYRIGHT.md为准。
Alembic模板保留MIT，Lucide图标保留ISC及适用Feather MIT；其他第三方既有许可/版权不被项目候选许可覆盖。
[来源审核](third_party/SOURCE_REVIEW.md)、[逐文件记录](third_party/source-review.json)和[第三方声明](THIRD_PARTY_NOTICES.md)应一并保留。

首次只准备完整源码、迁移、测试、构建/Compose配置、虚构示例与法律文本，不提供预构建镜像、Docker TAR、wheel或编译前端。
不复制原Git历史、私人配置、密钥、真实数据库/文章/媒体/备份、旧图片或未经审核素材。
生产lunardate0.2.2及农历行为不变。源码清单/哈希已按新增LICENSE、COPYRIGHT和A授权记录重新生成；不得沿用激活前888文件预览的旧哈希。

## 自行构建和新安装

以下步骤仅供所有者批准并建立新源码仓库后使用；本轮未创建该仓库或执行部署。
从 `https://github.com/inkzcz/life-journal_public` 获取获准的固定提交，使用干净Git checkout。
新仓库初始提交会产生新构建身份，不能把清单中的原准备SHA当成新仓库HEAD。
候选没有正式Annotated Tag，下载ZIP不能绕过来源校验；优先使用Git checkout。

一个Debian Linux/amd64业务镜像 `life-journal:<候选标签>` 通过 `api`、`web`、`maintenance` 三个启动命令运行独立容器。
PostgreSQL17官方镜像由部署者独立准备，不打入业务TAR，Compose不会隐式拉取缺失镜像。
Windows需要Git、Python3.10+、Docker Desktop Linux Containers/Buildx；Linux使用本机Docker Engine与Buildx。

Windows PowerShell：

```powershell
$Revision = (git rev-parse HEAD).Trim()
$Version = "v5.1.9-candidate.$($Revision.Substring(0,7))"
.\scripts\release-local.cmd -Version $Version -Revision $Revision
```

Linux Bash：

```sh
candidate_revision=$(git rev-parse HEAD)
python scripts/release_local.py --version "v5.1.9-candidate.${candidate_revision:0:7}" --revision "$candidate_revision"
```

工具仅允许本地Docker连接，联网获取构建依赖，不默认加`--pull`，保留源码身份、SHA256、架构、镜像完整性、
重复load和已有资源冲突保护；只输出一个业务TAR及校验/元数据，不推送镜像或自动连接NAS。
这是部署者自行构建产物，不是本次源码发布附带的二进制。

新安装时私下复制`.env.example`为`.env`，自行设置数据库密码、至少32字符随机SETUP_KEY、候选业务标签、
已有PG17镜像和新持久目录。Compose默认仅发布Web回环端口，等待DB→Maintenance→API→Web健康门禁。
通过受控HTTPS初始化自己的管理员，完成后移除SETUP_KEY；项目无默认管理员账号或密码。
具体步骤见[安装指南](docs/install.md)，不要将新安装目录直接映射到原生产数据。

## 文档与已知限制

- [安装](docs/install.md)、[升级与回滚](docs/upgrade.md)、[备份恢复](docs/backup-restore.md)。
- [开源声明](docs/open-source.md)、[已知限制](docs/known-limitations.md)、[许可证候选](docs/licensing.md)、[第三方再分发](third_party/REDISTRIBUTION.md)。
- [安全](SECURITY.md)、[贡献](CONTRIBUTING.md)、[本地验收](docs/local-validation.md)、[虚构演示](examples/demo.md)。

**UPGRADE-001：v5.1.8→v5.1.9的历史Maintenance升级失败仍未解决，本轮不复现；不要据源码整理直接生产升级。**
原仓库Actions受付款/支出限制未启动，不记为通过；Linux本地结果不替代新仓库CI、Windows Docker Desktop或NAS验收。
未来二进制对应源码/NOTICE/替换及平台验收仍单独保留，不能因源码公开自动宣称完成。

本快照组装时A阶段已批准并执行，准备任务的B阶段公开操作尚未批准；须按精确提交、目标仓库、清单及源码树哈希另行批准。
B状态描述本准备任务的操作授权，不给GPL接收者附加许可之外的分发限制。B记录留在快照外，避免修改已批准字节造成哈希自引用。
本任务不会创建公开仓库、改变原私有仓库可见性或合并准备PR。
