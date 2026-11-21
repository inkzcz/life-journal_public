# v5.1.9 Release 准备（草稿）

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
本 PR 已将维护 CLI 和文档改为显式 --user 10001:10001；不递归修改已有数据、不改变入口权限策略，必须由后续实际 CI 验证修正。
已加入真实 BuildKit context 合成验证；当前运行证据不等同于 Windows/NAS，也不把独立恢复或合成升级通过当成 UPGRADE-001 历史根因已确认。

## 正式发布门禁

- [ ] 所有者审核并合并维护 PR，确认正确的正式发布提交；CI 实际成功。
- [ ] 解决或明确接受 UPGRADE-001 的风险及支持范围；不能把新安装成功作为历史升级成功。
- [ ] Docker 全新安装、四容器健康、初始化/登录、重启、备份和独立恢复结果完整。
- [ ] Windows Docker Desktop 与 NAS 的平台验收分别完成，Linux 不替代。
- [ ] 二进制对应源码、LGPL 替换、版权/NOTICE、构建对应完成，见 third_party/REDISTRIBUTION.md。
- [ ] 单一业务镜像、Linux/amd64、全部引用层无不必要私钥、单 TAR 和重复 docker load、SHA256/源码身份复核。
- [ ] 经所有者另行批准创建不覆盖历史的 Annotated Tag、正式 Release；本 PR 不执行。

安装见 install.md；升级与回滚见 upgrade.md；完整备份恢复见 backup-restore.md。数据库镜像必须由部署者提前准备，本地发布工具不查询、构建或交付数据库镜像。
