# Life Journal v5.1.10

- 新建文章默认日常记录，可直接切换旅行记录，不必先配置内容类型或模板；高级内容类型和历史模板能力保留。
- 地点、美食、电影、演出、礼物、交通使用共享紧凑卡片；可选照片、长文字、浅深色和移动布局保持一致。
- 保留卡片/媒体 UUID、动态字段、原正文及 Markdown 往返、旅行行程和旧记录。
- 管理员通知 URL 可见可编辑；支持 WxPusher 路径变量与查询值分别安全编码。保留固定 origin、HTTPS、SSRF/DNS、白名单、超时、禁止重定向和有限重试，不回显凭据。

## 下载与安装

`life-journal-app-v5.1.10-amd64.tar` 是唯一 Linux/amd64 业务镜像，标签 `life-journal:v5.1.10`。
API、Web/Caddy、Maintenance 三个独立容器共用它；PostgreSQL17 是独立第四容器，镜像由 NAS 管理员提前准备，不在 TAR 中且不隐式拉取。
下载同处的 SHA256SUMS.txt、manifest.json、images.json、部署 ZIP 和对应源码/许可证包并核验，按 INSTALL.md 或 UPGRADE.md 导入和启动；无需在 Windows/NAS 编译。
配套源码包含实际原生依赖、补丁、版权/NOTICE、构建及 LGPL 替换/重链接材料，绑定本次 TAR 与构建提交。原创 GPL-3.0-or-later；第三方许可和署名不改授。

## 升级与回滚

v5.1.9→v5.1.10 不增加迁移，Head 仍为 0021_anniversary_calendar。保留原 Compose、卷映射、UID/GID 和所有迁移/备份保护。
先停止写入，用旧版本创建并验证完整备份，另存配置和旧镜像；核验并导入新版 TAR，只更改原项目 IMAGE_TAG，等待 DB→Maintenance→API→Web 并核对实际版本、旧记录/媒体和备份。
失败立即停止写入，保留原始数据和日志；同Schema且未写入时可回用保留旧镜像。存在新写入或不确定时，使用精确旧构建和升级前备份恢复到另一个新空目标、独立验证后人工切换；不执行 downgrade、stamp、down -v 或跳过门禁。旧备份不含升级后新增内容。

## 实际证据与已知限制

正式 Actions 对本次 Tag 验证完整 PG17/SQLite、前端/类型/构建、Windows 启动器自动化、Linux浏览器合成、单TAR/重复导入/全层密钥、四容器/持久化、完整备份和独立恢复、5.1.9同Schema升级、Psycopg/Pillow替换及精确源码。最终结果以工作流和逐构建收据为准，失败不会公开Release。
**Windows Docker Desktop、极空间 Z4S、真实用户数据库升级及真实 WxPusher 终端投递均待所有者本地验收。** 自动化/合成数据不冒充这些结果；所有者接受其为发布后验收。
**UPGRADE-001：历史 v5.1.8→v5.1.9 Maintenance 故障根因未确认，未宣称修复。** 0018→0021合成演练与5.1.9同Schema升级是不同证据，不能证明历史故障已解决。
普通备份仍要求精确构建/Schema/PG主版本匹配；保留原镜像和配置。未访问任何NAS、生产数据库、媒体或真实备份。
