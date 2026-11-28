# Life Journal · 私人生活档案

当前版本为 **v5.1.12**：六类紧凑生活卡片、显式插入与取消保护、三种阅读模式、安全永久删除与引用维护，以及可选 AI 服务商/多模型管理，保留旧文章、模板 API、媒体 UUID、行程与迁移保护。
正式可部署附件以 [v5.1.12 Release](https://github.com/inkzcz/life-journal_public/releases/tag/v5.1.12) 实际内容为准；页面或业务 TAR 尚不存在时不代表已发布。
验收边界见 [v5.1.12 验收](docs/development/v5.1.12-progress.md)，正式流程见 [发布规范](docs/release-policy.md)。

Life Journal 是可自行部署的私人 Blog，包含文章与草稿、TipTap/Markdown 编辑、旅行/地点/行程、照片流与相册、公历/农历纪念日、主题及后台管理。
前端 Vue 3，后端 FastAPI，数据库 PostgreSQL 17。一个 Debian Linux/amd64 业务镜像通过 `api`、`web`、`maintenance` 三个命令运行三个独立容器，数据库为独立第四容器。

v5.1.12 采用一个 Debian 业务镜像。正式附件以 [v5.1.12 Release](https://github.com/inkzcz/life-journal_public/releases/tag/v5.1.12) 为准；若页面或附件尚不存在，表示发行工作流还未完成，测试候选不能当作正式镜像。
公开仓库：https://github.com/inkzcz/life-journal_public 。首次公开提交为 `cd3182450f6163d40f1e5221c9e4483850546884`，以全新历史发布；维护变更通过分支和 PR 审核。

## 安装

使用正式附件无需在 Windows 安装 Git 或本地构建：下载业务 TAR、SHA256SUMS 和部署 ZIP，核验后在 NAS Docker 中导入。PostgreSQL17 镜像需自行提前准备。
Windows Docker Desktop 和极空间Z4S 实机验收由所有者在发布后完成，当前均为**待本地验收**，不是已通过的测试。

从本仓库取得已审核的固定提交，在干净 Git checkout 中自行构建。源码 ZIP 没有正式 Annotated Tag 身份时不能用手填 SHA 绕过校验。

```sh
git clone https://github.com/inkzcz/life-journal_public.git life-journal-source
cd life-journal-source
git checkout --detach YOUR_REVIEWED_FULL_PUBLIC_SHA
candidate_revision=$(git rev-parse HEAD)
candidate_product=$(cat VERSION)
candidate_version=$(cat VERSION)
python scripts/release_local.py --version "v${candidate_version}-candidate.${candidate_revision:0:7}" --revision "$candidate_revision"
```

Windows PowerShell（需 Git、Python 3.10+、Docker Desktop Linux Containers/Buildx）：

```powershell
$Revision = (git rev-parse HEAD).Trim()
$ProductVersion = (Get-Content VERSION -Raw).Trim()
$Version = "v$ProductVersion-candidate.$($Revision.Substring(0,7))"
.\scripts\release-local.cmd -Version $Version -Revision $Revision
```

构建需要依赖网络，工具仅连接本地 Docker，不默认添加 `--pull`，不推送镜像。
工具只生成一个业务 TAR 及身份/校验文件，保留源码、架构、SHA256、镜像完整性、重复 load 和资源冲突保护。
PostgreSQL 17 镜像由部署者另行准备，不放入业务 TAR；Compose 使用 `pull_policy: never`，镜像缺失会停止。

在新的部署目录私下复制 `.env.example` 为 `.env`，自行设置数据库密码、至少 32 字符随机 `SETUP_KEY`、镜像引用和新的持久目录。
只运行 `docker compose --env-file .env config --quiet`，不要公开展开后的配置。
导入业务镜像并准备数据库镜像后，`docker compose --env-file .env up -d --pull never` 等待 DB → Maintenance → API → Web 健康门禁。
Web 默认绑定 `127.0.0.1:18080`，没有默认管理员账号或密码。通过受控 HTTPS 完成初始化后移除 `SETUP_KEY`；隔离回环 HTTP 验收才设置 `COOKIE_SECURE=false`。
详见[安装指南](docs/install.md)。不要将新安装映射到现有生产数据目录。

## 许可证与第三方

Copyright (C) 2026 inkzcz。所有者有权许可的原创源码及改编文件中的原创增量按 **GPL-3.0-or-later** 授权，见 [LICENSE](LICENSE) 与 [COPYRIGHT.md](COPYRIGHT.md)。
第三方 MIT、ISC、GPLv3-only 等原有许可、版本选择和署名保留，不被重新授权。
见[第三方声明](THIRD_PARTY_NOTICES.md)、[逐文件来源](third_party/source-review.json)、[再分发义务](third_party/REDISTRIBUTION.md)。生产 lunardate 及农历行为保留。
源码不含私人配置、真实文章/照片/数据库/备份、原 Git 历史或预构建二进制。[源码范围](SOURCE_DISTRIBUTION.md)区分首次快照和后续维护。

## 验证状态和文档

首次公开提交的 [GitHub Actions](https://github.com/inkzcz/life-journal_public/actions/runs/44915676538) 已成功完成 PostgreSQL/SQLite 回归、前端测试/类型检查/构建及 Compose 配置检查。这不代表 Docker 运行、Windows 或 NAS 验收通过。
当前正式发布门禁见 [v5.1.12 交付](docs/release-v5.1.12.md)；历史 v5.1.9 发行记录保留。

**UPGRADE-001：历史 v5.1.8 → v5.1.9 Maintenance 失败原因尚未确认，不能直接据新安装成功宣称生产升级已通过。**
请先阅读[升级/回滚](docs/upgrade.md)、[隔离分析](docs/upgrade-001.md)、[备份恢复](docs/backup-restore.md)和[已知限制](docs/known-limitations.md)。
其他文档：[开源说明](docs/open-source.md)、[安装](docs/install.md)、[贡献](CONTRIBUTING.md)、[安全](SECURITY.md)、[本地验收](docs/local-validation.md)、[虚构示例](examples/demo.md)、[变更记录](CHANGELOG.md)。
