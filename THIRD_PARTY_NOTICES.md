# 第三方声明（原创GPL-3.0-or-later已激活）

Life Journal有权许可的原创部分及原创增量已按A授权采用GPL-3.0-or-later；第三方组件继续适用各自条款，不由根许可证覆盖。本文件、[许可证候选](docs/licensing.md)、[二进制分发说明](third_party/REDISTRIBUTION.md)和[逐组件证据](third_party/redistribution-inventory.json)应一起审核。

| 组件/类别 | 声明与处理 |
| --- | --- |
| 实际包含的Alembic模板骨架 | 按MIT保留Michael Bayer版权与完整文本；来源和修改范围见third_party/SOURCE_REVIEW.md。 |
| 实际包含的13个图标几何 | 固定Lucide提交，保留ISC及适用Feather MIT、Lucide/Cole Bemis署名；逐项来源和哈希见third_party/icon-provenance.json。 |
| lunardate 0.2.2 | 包声明 GPLv3，源码有早期 GPLv2 来源注释。保留许可和公开版权，已有上游 lunar GPL-2+ 证据支持 GPLv3；未更换依赖或改授主许可。 |
| Psycopg / binary | 先前私密镜像观察为3.3.9（本次不交付该镜像），LGPL-3.0-only；库源码、可替换机制和 14 个内附共享库另审。 |
| Caddy 2.11.9 / Go | Apache-2.0；147 个具名 module 的源码 h1 与实际二进制一致，保留各模块声明及 Go BSD/PATENTS。 |
| Python / Debian / PG17 工具 | 各自许可及具体包 copyright；163 项 Debian 声明已解析。数据库容器镜像由部署者独立管理，不纳入业务镜像。 |
| Vue / TipTap / 前端 | 209 项 lock 依赖的声明资料；包含 dev/平台候选，实际 bundle 需按构建审核。 |
| DOMPurify | MPL-2.0 OR Apache-2.0，分发时记录合法分支，不能漏掉声明。 |
| certifi | MPL-2.0，覆盖文件及其对应源码获取义务仍适用。 |
| Pillow / FreeType / IJG | 保留编解码器原始声明及适用分支，不能只标 Pillow 顶层许可。 |
| Pydantic-core 原生部分 | 2.50.5 sdist Cargo.lock 的 101 crate 声明；含 Unicode AND 条件，实际 wheel 编译对应关系待补。 |

This product uses the FreeType Project (https://freetype.org/); original copyright years and authors are preserved in the notices. This software is based in part on the work of the Independent JPEG Group.

licenses/evidence/（位于 third_party/）保存原始法律文本与公共署名，notice-index.json 映射来源和内容哈希。不要删除公共作者声明来通过脱敏扫描。对未知个人内容与凭据的检查仍保留。

新演示使用虚构文字和代码生成色块图；原历史截图、图库照片和字体不在本快照中。当前资料不代表全部对应源码、授权链、二进制再分发或候选验收已完成。

本次只准备源码，source-scope.json（位于 third_party/）区分引用与实际复制内容。wheel、内附库、Caddy/Go 生成根等二进制缺口仅影响以后相应产物分发；不把它们当成当前不含这些二进制的源码阻塞。A阶段权属/许可已在限定原创范围内确认，准备任务B仍需独立精确快照批准。原作者许可及 only/or-later 范围保留，未来 GPL 版本的整体组合兼容性不作保证。

本次限定源码来源技术审查已完成，见third_party/SOURCE_REVIEW.md及逐文件source-review.json；来源审核已获所有者接受，原创GPL已激活；不表示准备任务已获B公开批准。

已激活的原创授权只及所有者有权许可的部分，不改写本文件所列上游授权。新目标仓库的源码身份URL会变化，410份法律文本及版权仍逐字保留。公开与未来二进制发布均须各自明确批准。
