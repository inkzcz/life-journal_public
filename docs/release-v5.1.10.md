# v5.1.10 正式交付

所有者已授权 PR #4 的安全发布准备修复、普通合并、main CI、Annotated Tag 和完整单镜像正式 Release。
独立授权见 licensing/BINARY_RELEASE_v5.1.10_AUTHORIZATION.json；长期规则见 release-policy.md。
本文件是发布契约，实际成功、提交和 SHA256 以 Actions/Release 附件为准；工作流尚未完成时不能称已发布。

- Debian、Linux/amd64；唯一镜像 life-journal:v5.1.10，唯一业务 TAR life-journal-app-v5.1.10-amd64.tar。
- API、Web、Maintenance 共用镜像；第四个容器 PostgreSQL17 由用户提前独立准备。无 Registry 发布。
- Alembic Head 0021_anniversary_calendar；无新表/迁移，UUID、正文/Markdown、字段、模板 API、媒体引用、卷、Compose 和 UID/GID 不变。
- 原 b07da2f 的分支/PR CI 已成功：PG976/2、SQLite886/92、前端325，实测镜像/独立恢复、LGPL 和同Schema升级。发行门禁改动后的最终 HEAD、main 和正式 Tag 仍须有各自实际通过证据。
- 正式构建重新执行必要回归、Windows 启动器自动化、浏览器合成、全部层、重复导入、四容器/持久化、备份独立恢复、5.1.9→5.1.10同Schema和原0018→0021隔离演练、Psycopg和Pillow替换、精确对应源码。
- 同Schema升级收据与正式镜像标签及源码提交绑定，随源码/许可证包交付。来源/法律材料严格逐文件校验，不用旧410文本目录替代实际依赖源码。
- 发布作业不checkout或执行业务代码，只接收白名单附件；先草稿、上传、回下载所有SHA256与镜像架构/来源复核，再正式公开。

Windows Docker Desktop、Z4S、真实数据库升级及真实通知投递仍待本地验收，所有者已接受不单独作为前置阻塞。UPGRADE-001 保持历史已知未解决，不宣称修复，迁移/备份保护不变。
安装见 install.md；v5.1.9升级、备份和回滚见 upgrade.md、backup-restore.md；限制见 known-limitations.md。
