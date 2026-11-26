# v5.1.11 正式交付契约

六项功能已通过PR #5合并，后续PR #6/#7/#8补齐打包、草稿安全和中文视觉验收。所有者明确批准仅对尚未正式发行的v5.1.11 Tag执行一次身份修复，最终来源绑定PR #9普通main合并与精确HEAD/main CI。当前授权见licensing/BINARY_RELEASE_v5.1.11_REPAIR_AUTHORIZATION.json；原授权文件保留不变。发布完成前不得声称已有正式附件。

必要门禁：PG17、SQLite、前端/类型/构建、原生Windows工具自动化、生产组件Chromium合成视觉、源码/秘密/许可、Debian镜像全部层/私钥/重复load、四容器/初始化/重启/持久化/备份独立恢复、精确正式v5.1.10至v5.1.11同Schema升级、原0018至0021演练、Psycopg替换/Pillow重链接及精确对应源码。不得绕过或放宽失败门禁。

源码和当前依赖法律包、镜像配置/TAR哈希、源码提交、标签对象与构建收据绑定；一个业务镜像和一个TAR，PG17独立。十附件白名单，先草稿、回下载全部校验、正式公开后匿名校验。无Registry推送，保留旧Tag/Release/镜像。

Artifacts仅保留必要发行中转及少量PR合成截图，禁止数据库、媒体、原始日志及重复候选业务TAR上传；已公开并复核的本次发行中转可按精确run/id/name清理，其他运行和历史资产不受影响。

真实Windows Docker Desktop、Z4S、用户库及通知终端为发布后待本地验收；UPGRADE-001历史未解决。未访问NAS、真实数据或原私有仓库。


发行调度修复：首次正式运行45618008729因步骤环境作用域使正式Tag误走候选校验，未上传附件。修复通过独立PR，不移动v5.1.11 Tag，不改业务/许可证/Schema或历史授权。`licensing/v5.1.11-release-orchestration-review.json`仅为既有授权下的精确CI字节技术补充；运行时仍比较Tagged应用关键文件并验证原Tag/main及调度main CI。法律包的application源自固定Tag，build-orchestration源自实际调度提交，均有逐文件校验与TAR绑定。

本次未发行Tag修复严格执行[身份修复记录](v5.1.11-unreleased-tag-repair.md)；原953a945→3c3a465仅供追溯，不可复用其产物。新Tag直接对应包含所有修复的新main，正式镜像重新构建。正式发行后该Tag永久不可变；不改用v5.1.12。
