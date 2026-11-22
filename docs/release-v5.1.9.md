# v5.1.9 Release 准备（草稿）

## 本轮正式候选准备（优先于下方历史验收记录）

起点是公开 main `e00b80e866d9686458963efe3ade2d658b9c56b0`，维护 PR #1 已由所有者合并。
本轮在 `release/prepare-v5.1.9` 修改，待独立 PR 审核，不修改 main、原私有仓库或生产部署。
版本仍为 v5.1.9 候选；正式发布尚未批准。Linux CI 使用提交限定的候选标签，避免覆盖已有同名镜像。
最终受审构建才使用 `life-journal:v5.1.9` / `life-journal-app-v5.1.9-amd64.tar`。

| 当前范围 | 状态 |
| --- | --- |
| Linux 源码/后端/前端/敏感信息/许可证测试 | 本分支实际结果以 PR Checks 与报告为准；不能复用 main 或旧候选的绿色记录 |
| Linux 单业务 TAR/全部镜像层/重复 load/四容器/备份/独立恢复 | 本分支 CI 实际生成和验证临时产物，不上传；本地可留存最终产物仍受存储限制 |
| LGPL 替换 | 新增修改后 Psycopg 的真实 PG17 查询探针，须本分支 Docker CI 实际完成 |
| Windows Docker Desktop | **待本地验收**；本正式候选没有实机结果，不沿用旧版测试 |
| 极空间 Z4S | **待本地验收**；不连接 NAS，不操作现有数据库/媒体 |
| UPGRADE-001 | 历史失败原因未确认；合成迁移证据不构成历史路径已修复 |
| 二进制许可/对应源码 | 通知及部分验证/源码收集已补齐；精确对应源码、内附库/构建配方及与可留存最终 TAR 绑定仍为发布阻塞，见 REDISTRIBUTION.md |
| 正式发布权限 | **待最终产物再次批准**；本轮不创建 Tag/Release、不上传 TAR、不推送 Registry |

本地可复现命令（需充足磁盘、一个空交付父目录及本地 Linux Docker；不加默认 `--pull`）：

```sh
revision=$(git rev-parse HEAD)
python scripts/release_local.py --version v5.1.9 --revision "$revision" --output-dir /PRIVATE/NEW/delivery
python scripts/image_private_keys.py --archive /PRIVATE/NEW/delivery/v5.1.9/life-journal-app-v5.1.9-amd64.tar
```

交付工具只构建/校验/导出一个业务镜像，不查询或打包 PostgreSQL 镜像。
隔离 Docker 验收另外要求已预备的官方 PG17 测试镜像；这不是交付内容，也不是生产部署步骤。
空间不足、对应源码不全或产物未留存时，不能把 CI 的临时 TAR 哈希写成已具备下载条件的最终产物。

正式批准前还须：合并已通过 CI 的发行 PR、确定最终源码提交、留存并绑定业务 TAR/完整源码法律包及其全部 SHA256，
逐项解除许可证义务；完成平台验收或由所有者在最终审核中明确接受该缺口；明确 UPGRADE-001 支持范围/风险。
最终批准必须针对实际产物，不能沿用源码首次公开的 A/B 授权。安装及恢复继续遵守原迁移/备份门禁。

<details>
<summary>公开后首次维护的历史验收记录（不替代本次候选）</summary>

尚未创建 Tag、Release 或发布任何镜像。本轮基于首次公开提交 cd3182450f6163d40f1e5221c9e4483850546884，通过 maintenance/post-publication-v5.1.9 分支和 PR 审核。

## Release Notes 草稿

- 首次独立开源源码：v5.1.9 候选的文章、旅行、相册、纪念日、主题和后台完整功能；原创 GPL-3.0-or-later 及第三方许可边界明确。
- 一个 Debian Linux/amd64 业务镜像运行 API/Web/Maintenance 三个独立角色，PostgreSQL17 官方数据库镜像独立管理；只交付一个业务 TAR。
- 更新开源后的安装、权限、备份、升级和回滚文档；测试用照片包改为内存合成，不污染源码目录。
- 保留全部迁移/恢复/权限和失败重试安全门禁。UPGRADE-001 未经历史精确证据确认不得标记解决。

## 版本与维护差异

5.1.9 尚无正式 Tag/Release，因此文档、测试和验收修复可以继续使用 5.1.9 候选版本号；构建使用带提交身份的 candidate 标签，不能当作已正式发布。
未修改已发布版本、原数据库迁移或业务功能。本轮更新的清单属于后续维护，不沿用首次快照哈希；首次提交/身份单独保留。

## 验收记录

首次公开 main 的 Actions 44915676538 已真实成功完成：PostgreSQL/SQLite 全量回归、前端测试/类型检查/生产构建、Compose 配置及源码/许可/Gitleaks。
本地实际结果：

| 项目 | 状态与范围 |
| --- | --- |
| PostgreSQL17 全量回归 | 843 passed / 2 skipped；跳过的是 SQLite 参数的 PG advisory-lock 项和需显式临时 BuildKit 的 context 项 |
| SQLite 全量回归 | 753 passed / 92 skipped；PG 专用项与显式 Docker context 项不算 SQLite 已验证 |
| 前端 | 311 tests passed；TypeScript/生产构建通过；相同参数两次构建 73 文件字节一致（本地 Node24.19.0/npm11.9.0，CI Node22 独立验证） |
| 来源/许可证/公开契约专项 | 40 passed；410 份法律文本哈希有效且原样保留；无新增第三方实现或运行依赖 |
| Compose 配置 | 本地仅合成配置 config --quiet 通过 |
| 本地 Docker | 初次只读客户端状态目录失败；使用独立状态目录后因磁盘不足失败。未宣称本地构建/运行通过，未删除旧镜像/交付文件 |
| 首轮本地 PG | 与 Docker 共享盘耗尽后出现失败并中止（exit130），不记通过；仅清理本轮合成容器/匿名卷后，使用新内存临时卷取得上面的独立通过结果 |
| 维护 CI | 以本 PR 对应提交的 Checks 为准，不用首次 main 的绿色状态替代维护提交；完整结果在 PR 中记录 |

首轮维护 CI 的 Docker 构建、单 TAR/重复 load、全层密钥扫描和 Debian/PG17/Caddy 探针已实际通过。
构建探针观察到 Python3.12.16、PG17.12、Caddy2.11.9 和 libpq19；这些浮动依赖版本的对应源码/许可证证据不能由旧二进制清单自动代替，正式二进制分发前仍须重新核对。
首轮新安装/初始化/登录/重启成功后，独立恢复在读取备份时失败：验收脚本用 docker compose exec 默认 root 创建备份，而恢复入口降权为 UID10001。
维护提交 ea27bc5c6f8c5adf03adab067e04c4755612c378 已将维护 CLI 和文档改为显式 --user 10001:10001；不递归修改已有数据、不改变入口权限策略。
该提交的 [Docker 验收作业](https://github.com/inkzcz/life-journal_public/actions/runs/44922304391/job/136900841023) 已实际成功完成：
- 单业务镜像构建、单 TAR、完整身份/架构/SHA256、重复 load 和全部引用层私钥扫描。
- Debian/Python/PG17/Caddy/UID10001 探针；真实 BuildKit context 的隐私排除测试 1 passed。
- 四容器健康、API HTTP200、Caddy 静态资源及代理、首次初始化/登录、重启和持久化。
- 完整备份、独立空目标实际恢复及恢复后登录。
- 0018_content_exchange → 0021_anniversary_calendar 合成库：真实 PG17 dump/restore/试迁移、原值/序列及 3 个媒体文件保留，第二次启动为 current。
后续提交仅继续维护文档和清单；其完整 CI 仍须以对应提交 Checks 的真实结果确认，不把上述 Docker 作业等同于整条后续 CI 已成功。
已加入真实 BuildKit context 合成验证；当前运行证据不等同于 Windows/NAS，也不把独立恢复或合成升级通过当成 UPGRADE-001 历史根因已确认。

## 正式发布门禁

- [ ] 所有者审核并合并维护 PR，确认正确的正式发布提交；CI 实际成功。
- [ ] 解决或明确接受 UPGRADE-001 的风险及支持范围；不能把新安装成功作为历史升级成功。
- [x] Linux Docker 全新安装、四容器健康、初始化/登录、重启、备份和独立恢复结果完整（上述实际作业证据；Windows/NAS 另列）。
- [ ] Windows Docker Desktop 与 NAS 的平台验收分别完成，Linux 不替代。
- [ ] 二进制对应源码、LGPL 替换、版权/NOTICE、构建对应完成，见 third_party/REDISTRIBUTION.md。
- [x] 验收镜像为单业务 Linux/amd64；全部引用层无不必要私钥，单 TAR/重复 docker load、SHA256/源码身份通过。正式发布提交需再次绑定构建。
- [ ] 经所有者另行批准创建不覆盖历史的 Annotated Tag、正式 Release；本 PR 不执行。

安装见 install.md；升级与回滚见 upgrade.md；完整备份恢复见 backup-restore.md。数据库镜像必须由部署者提前准备，本地发布工具不查询、构建或交付数据库镜像。

二进制 C 类具体未完成项：当前 Dockerfile 没有显式把项目 LICENSE/COPYRIGHT、前端编译资源及单独复制的 Caddy 二进制的适用声明一起装入镜像；不能把源码目录中有法律文本当成镜像已包含。
还须针对实际构建的 wheel/内附库与系统包重新固定版本和对应源码，完成 Psycopg/LGPL 替换或重组验证及适用 NOTICE/源码获取方式。当前验收镜像没有被发布，这些缺口继续阻止未来镜像分发，不撤销已有源码公开。

</details>
