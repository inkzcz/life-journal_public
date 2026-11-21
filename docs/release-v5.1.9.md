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
维护分支及本地最新结果将在本 PR 验收后填写，未完成项目不记为通过。

## 正式发布门禁

- [ ] 所有者审核并合并维护 PR，确认正确的正式发布提交；CI 实际成功。
- [ ] 解决或明确接受 UPGRADE-001 的风险及支持范围；不能把新安装成功作为历史升级成功。
- [ ] Docker 全新安装、四容器健康、初始化/登录、重启、备份和独立恢复结果完整。
- [ ] Windows Docker Desktop 与 NAS 的平台验收分别完成，Linux 不替代。
- [ ] 二进制对应源码、LGPL 替换、版权/NOTICE、构建对应完成，见 third_party/REDISTRIBUTION.md。
- [ ] 单一业务镜像、Linux/amd64、全部引用层无不必要私钥、单 TAR 和重复 docker load、SHA256/源码身份复核。
- [ ] 经所有者另行批准创建不覆盖历史的 Annotated Tag、正式 Release；本 PR 不执行。

安装见 install.md；升级与回滚见 upgrade.md；完整备份恢复见 backup-restore.md。数据库镜像必须由部署者提前准备，本地发布工具不查询、构建或交付数据库镜像。
