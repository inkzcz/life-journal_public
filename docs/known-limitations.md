# 已知限制与验证边界

- v5.1.9 仍为源码候选，尚无正式 Tag/Release 或预构建业务镜像。原始快照已公开，维护变更通过 PR 审核。
- UPGRADE-001 历史 Maintenance 失败原因未确认；本轮仅允许合成隔离分析。不要据新安装或合成回归直接生产升级，见 upgrade-001.md。
- 首次公开提交的 Actions 已成功；维护分支 CI、本地 Docker、Windows Docker Desktop 和 NAS 的结果分别记录在 release-v5.1.9.md，未执行项不记通过。
- 新公开仓库有新的构建身份。普通备份要求匹配构建、Schema 与 PG 主版本，不能把旧私有镜像和新构建仅凭版本号视为可互换。
- PostgreSQL17 镜像独立提前准备，不随业务 TAR 交付，不隐式拉取；不得用空卷替换旧数据来冒充升级。
- 二进制分发的对应源码、LGPL 替换、适用版权/NOTICE 和平台验收仍须独立处理，见 third_party/REDISTRIBUTION.md。
- 敏感信息扫描只识别已知模式，不是所有未知秘密或个人信息均不存在的证明。
- 本次正式候选未在 Windows Docker Desktop 或极空间 Z4S 实机验收，均标记为**待本地验收**；所有者尚未决定是否接受缺口。Linux CI 与旧版实机结果不替代这两项。
- 对应源码/NOTICE/LGPL 的完成度必须绑定本次实际可留存产物；CI 临时生成未上传的业务 TAR 不是最终可下载交付。
