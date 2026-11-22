# v5.1.9 正式发行门禁

所有者于本次对话明确授权：完成必要法律条件和最终CI后，将PR #2转为Ready、普通Merge commit合并，
在合并后的main创建新Annotated Tag v5.1.9，并由Actions构建、保存、创建非预发行Release和上传附件。
本记录不伪造签名或精确确认时间；授权范围见 licensing/BINARY_RELEASE_AUTHORIZATION.json。
原私有仓库、NAS及生产数据库/媒体/备份不在操作范围；不推送Registry、不覆盖历史Tag/Release。

Windows Docker Desktop、极空间Z4S为**待本地验收**，由所有者发布后自行验证，不再是前置条件。
UPGRADE-001保留为历史已知问题，不阻塞发行，也不宣称已修复。数据库版本/Alembic/备份恢复门禁仍强制。

## 每次实际构建必须通过

1. 公开源码/原许可证/逐文件来源与敏感信息检查；最终PR HEAD与合并main的真实CI成功。
2. 固定Linux/amd64基础镜像digest与运行依赖版本，单业务镜像构建、单业务TAR、源码及配置身份、SHA256、重复load、全部镜像层扫描。
3. Debian/Python/PG17工具/Caddy、四容器健康、登录/持久化、完整备份与独立恢复。PG数据库镜像只作为独立CI设施，不在业务交付。
4. Psycopg C扩展从其sdist编译并动态链接系统libpq；实际修改库执行PG17查询。Pillow保留图片功能，LGPL shim必须实际修改源码、重编译/重链接后加载并验证接口。
5. 每个实际安装Debian/PGDG包的精确.dsc及orig/补丁源码，Python sdist和原生构建收据，Rust锁定源码，实际Go模块/通知及浏览器首选源码；任何组件缺失就失败。
6. sources.json与实际目录逐文件相符；拒绝额外ZIP、配置、数据库或未登记文件。输出仅白名单10附件，原始日志、合成DB、备份/媒体不进入Artifact。
7. 对应源码包DISTRIBUTION_MANIFEST绑定本次TAR SHA256、镜像config、源码提交和依赖版本；SHA256SUMS记录实际所有附件。成对保存源码与二进制，不能用上游URL或旧410参考目录替代。

## Actions与正式发行

ci.yml对准备分支和main保存已完成上述门禁的成对候选附件；PR运行验证相同步骤但不上传。
release.yml响应本仓库v5.1.9标签，或从已通过CI的main手动恢复同一标签发行：只读预检验证远端Annotated Tag正好指向PR #2的普通合并提交及已成功main CI；
然后复用同一Docker验收/源码门禁，构建正式 life-journal:v5.1.9 和 life-journal-app-v5.1.9-amd64.tar。
只有最后的publish作业持有contents:write，且不执行业务代码，核验所有附件后创建Release。
随后重新下载附件、核对全部SHA256和实际TAR架构，完成后才可报告成功。
CI源代码门禁对这两份工作流采用独立所有者授权与逐字节审核哈希，不对其他写权限/上传/发布放行。

首次正式运行45014259648在预检误拒了合法标签：checkout把本地tag引用展开为commit；远端标签
`bb3be1cf163e8ce2a75d3cfe01c0b80da261b45c`仍正确指向PR #2合并提交
`2db730b1bad683e5056f3f096987074bdfe5e02a`，没有Release或正式TAR被上传。
恢复流程通过修复PR交付，核验远端Git ref和tag对象而不是本地便捷引用；只从main的已通过CI的
工作流调度原有tag提交的独立工作区。不会更新、删除或强推标签，也不会用新main业务源码冒充tag。
应用源码提交和工作流修复提交分别登记并提供源码，所有原发布门禁继续执行。
发行安装/升级说明来自已审核的工作流修复提交，不沿用早期源码候选措辞；部署ZIP中的Compose、空白配置、LICENSE与COPYRIGHT仍逐字节来自原正式应用Tag，并附带UPGRADE-001说明。

发行附件：唯一业务TAR、完整源码与许可证包、部署ZIP、manifest/images、SHA256SUMS和安装/升级/限制/Release说明。
SHA与提交以实际附件为准，测试候选标签/哈希不能冒充正式发行。既有Linux结果不做无意义重复；原生库形态变化所影响的回归和最终构建必须真实执行。

具体分发义务见 third_party/REDISTRIBUTION.md、SOURCE_BUILD.md；安装/升级/恢复分别见 install.md、upgrade.md、backup-restore.md。
下面保留旧准备阶段的历史限制与验证结果，仅作背景，已被本轮明确发布授权更新的阻塞不再适用。

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
