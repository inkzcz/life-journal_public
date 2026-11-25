# Life Journal v5.1.11 — 生活记录体验与高级通知

正式发布状态以本版本GitHub Release及完整十附件为准，候选构建不能冒充正式产物。

- 日常/旅行模式跨首页、归档、搜索、时间线、统计和旅行来源统一；显式日常优先于历史类型、模板与行程，旧数据保留。
- 六类卡片可文章内复制、跨文章复制/移动，目标文章可搜索；事务、版本冲突、持久幂等及共享媒体保护，UUID按复制/移动语义处理。
- 地点明信片、美食图文、电影海报、演出票根、礼物收藏和交通路线专属布局，共用主题和三点菜单。无图、长字段、手机及深色兼容。
- 日期/时间和IANA时区可视化输入，默认站点时区；夏令时缺失时间拒绝，重复时间需选偏移；跨日/跨区实际耗时。历史值打开时不自动重写。
- 万年历通知兼容旧GET，新增POST、Headers、JSON/嵌套JSON、表单和纯文本；复杂GET JSON与空{}支持。安全预览不发送；POST不确定结果不盲重发。HTTPS、DNS固定IP/TLS主机校验、SSRF、限量、CSRF等保护保留。

## 部署和数据

唯一业务镜像 `life-journal:v5.1.11` / Linux amd64 / Debian；API、Web、Maintenance复用。唯一业务TAR为 `life-journal-app-v5.1.11-amd64.tar`，PG17镜像由用户提前独立准备，不在业务TAR中，不推Registry。
Schema仍为 `0021_anniversary_calendar`，不新增表或迁移，不改NAS卷、UID/GID、媒体UUID或历史模板。升级前完整备份、以旧构建独立恢复、保留旧镜像；仅更换业务标签，等待DB→Maintenance→API→Web。详见同处UPGRADE.md、INSTALL.md及KNOWN_LIMITATIONS.md。

## 验收边界

最终PR/main/正式发行Actions及对应源码法律包中的逐构建收据为证据。Windows Docker Desktop、极空间Z4S、真实用户旧库及真实通知终端投递均待所有者发布后本地验收。合成浏览器响应与Linux自动化不替代这些项目。UPGRADE-001历史根因未确认，不宣称修复，数据库迁移/备份/恢复保护不变。

对应源码、410历史法律文本、当前依赖NOTICE与实际Psycopg/Pillow替换验证随精确TAR绑定交付。源码及原始第三方许可不被改授。
