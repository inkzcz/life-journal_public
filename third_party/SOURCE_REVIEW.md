# A阶段已批准后的来源状态（当前结论）

所有者明确接受此前限定来源审核、MIT归因及Lucide替换，批准有权许可的原创源码及原创增量采用GPL-3.0-or-later。
根LICENSE与COPYRIGHT已激活；owner_authorization仅为A，publication_approved=false，B须独立绑定新候选。
本次仅加入原文LICENSE、原创正式通知、A批准记录及原创门禁/测试/说明增量，不改变既有第三方实现或410法律文本。
原声明历史不回写；下面保留此前方法/证据及当时待授权状态，当前状态以PHASE_A_AUTHORIZATION和proposal为准。
操作B门禁不限制GPL接收者已有权利，不对未知全网来源作保证。

<details>
<summary>既有来源方法与证据（已获所有者接受）</summary>

# 首次源码快照的来源、许可与署名审核

审核起点：895ca0e6b714f9fed1466e69e7763c15c99fef4b，日期 2026-11-21（Asia/Shanghai）。
本页与 source-review.json 的逐文件记录、icon-provenance.json 及最终 EXPORT_MANIFEST.json 一起使用。
范围是**实际导出的源码、配置、文档、测试和法律文本**；不是 Docker/wheel/编译前端的分发批准。

## 方法与完成的含义

从起点 877 个源文件条目（另加生成清单）建立逐文件清单，检查完整文件的来源标记、导入/引用、
生成模板、SVG/内联资源、外部 URL/字体、测试向量与数据；人工追查命中的模板、图形及格式解析器。
使用项目可访问的文件历史和已收到的所有者声明作为项目代码来源证据，核对指定上游材料；
没有把私有代码或日志送到外部相似度扫描平台，也没有执行全网代码查重。

J 类是**所有者已声明的项目开发来源 + 本次未识别外来复制信号**，不是独立证明每一行都原创。
无外来信号的普通 API 调用、惯用算法、CSS 布局不凭相似功能自动判为复制，也不宣称其必然有独占版权。
已出现明确外来线索的项目则须有来源/许可或替换证据，不能只凭所有者声明放行。
source-review.json 对每个实际交付路径登记类别、证据编号及规范化内容哈希（仅规范化目标仓库名与通用example/life-journal；第三方文本/完整许可证不替换）；其自身为自描述审核元数据，
不做不可能的自哈希，另由导出输入登记和最终清单校验。生成的 EXPORT_MANIFEST 单独校验。

“技术审核完成”仅指该枚举快照内已发现线索均有处理、无未决来源项；不等于许可已激活、
所有者已接受最终授权范围、全球权利担保或公开批准。未来新增/变化材料须重新审核、更新登记。

## 实际包含的第三方材料与处理

| ID | 实际交付路径 | 来源与许可 | 署名/处理结论 |
| --- | --- | --- | --- |
| A001 | backend/alembic/script.py.mako、backend/alembic/env.py；versions/ 中的生成骨架 | Alembic generic 模板/API 骨架，保守按改编处理；MIT。原有1.20.1法律文本见下方路径 | 保留 Michael Bayer 版权与完整 MIT；两个模板入口增加来源注释，项目特定迁移/禁止降级策略不变。没有修改既有迁移文件、Schema或运行逻辑。 |
| L001 | frontend/src/writing/iconPaths.ts；ModuleIcon.vue、places.ts 导入使用 | Lucide 固定提交 c1a02a04d4f3f7049d44567d62b8b06cff0b9103 的13个图标；ISC及适用的 Feather MIT | 保留 Lucide 与 Cole Bemis 版权及完整上游 LICENSE。逐图标源文件、SHA256、角色键及改动见 icon-provenance.json。几何转单一路径，保留项目描边；images 的实心点改为轮廓。 |
| G001 | licensing/GPL-3.0.txt、licensing/ORIGINAL_CODE_NOTICE.DRAFT.txt | GNU GPLv3 正文及其建议通知格式；FSF 原文/How to Apply | GPL正文逐字保留、候选通知明确 DRAFT；不是对项目的生效授权，根 LICENSE 不创建。 |
| N001 | third_party/licenses/ 中原409份法律文本及新增Lucide文本 | 各原始来源与既有声明见 notice-index.json | 原409项只核对与实际交付清单/哈希一致，未重新无意义取证；新1项另固定URL/哈希。法律文本的公共署名不替换为 inkzcz，不代表依赖实现一并交付。 |

A001 完整 MIT：licenses/evidence/6e68d94a03a0e3e327ddf3e86d1ebedc14eece3922022618fc246a36296fd0cc.txt。
对应rel_1_20_1固定提交，LICENSE与已保留MIT文本SHA256完全相同。上游参考：https://github.com/sqlalchemy/alembic/tree/47da01c856027876f4022b2da721a4edd6b4a0db/alembic/templates/generic 。
L001 完整 ISC/MIT：licenses/lucide-c1a02a04d4f3.txt。
G001 原文哈希/上游出处已由既有 licensing/proposal.json、license-provenance.json 与法律文本交叉记录。

### 未证实旧图标来源，已通过替换消除当前源码缺口

起点 ModuleIcon.vue:3-4 标注“Lucide-style”但没有来源版本，places.ts:4 同样含手写轮廓。
旧13个路径没有被追认为原创，也没有被追授上游许可。当前源码中全部移除，以可追溯的上游路径替换；
六种模块、七种地点图标及未知模块回退仍保留，角色、文案、事件、数据、Markdown和SVG安全边界不变。
旧历史继续保存在原私有仓库，本次不导出旧历史。对旧版本的权利不作追溯性结论。

## 已核查但不是复制依赖实现的项目

| ID | 路径/类别 | 证据与边界 |
| --- | --- | --- |
| J001 | 其余业务源码、脚本和项目配置/文档 | 使用已收到的个人主导/AI辅助、无其他开发者/雇主代码声明；逐文件结构、来源信号与历史检查未识别其他外来复制。不是第三方免责声明，也不再次索取同一声明。 |
| J002 | frontend/src/blog/BotanicalIllustration.vue、ThemeOrnament.vue | 内联参数化几何及本项目历史创建/修改；前者最早可访问提交 df6b8b78…、后者 0ff0b55e…；无图像导入/追踪底图/外部资源引用。按所有者声明的项目制作来源处理，未独立证明不存在全球相似作品。 |
| J003 | PlaceMap.vue、life/types.ts、CSS与字体栈 | 经纬度示意、几何网格、项目CSS；字体名是系统字体选择，不分发字体文件；没有瓦片、地图SDK或外部图像。 |
| J004 | writing/extensions.ts、caret.ts、ids.ts 等适配器 | TipTap/ProseMirror 的 import/extend/parent委托、DOM镜像测量与标准UUID位操作；未包含上游包实现或上游文档长篇复制。记录API/算法引用，不因惯用接口自动归为复制。 |
| J005 | 后端/前端测试、合成JSON与示例、demo_fixtures.py | 测试请求/断言、伪造服务、运行时色块/ZIP生成；无真实照片/数据库、外部故事/诗歌或下载素材。安全测试中的恶意SVG/URL是短合成输入。 |
| S001 | scripts/image_private_keys.py | GnuTLS上游公开自检向量的SHA256/固定来源引用，未复制实际私钥/库实现；这些事实标识不等于交付GnuTLS代码或生产密钥。 |
| S002 | scripts/license_evidence.py:go_build_modules | 独立有界Python解析器，读取Go格式魔数/标志/varint/哨兵；参考Go buildinfo格式，未搬入Go的exe/ReaderAt/各平台实现。功能格式事实与复制代码区分；不是把Go BSD代码改称本项目原创。 |
| R001 | requirements、package/lock、Dockerfile/Caddyfile、Compose、workflow | 名称/版本/完整性/安装命令或uses引用，不包含相应包/Action实现。保留生产lunardate 0.2.2；引用GPL包不表示随源码交付其实现。 |
| R002 | third_party 的库存、索引、审核文档 | 已有来源事实/版本/哈希与本项目审核说明；逐字法律材料归N001。未来镜像材料是补充证据，不声称其二进制存在于源码快照。 |

S002 格式参考固定于 Go 提交3901409b5d0fb7c85a3e6730a59943cc93b2835c：
https://github.com/golang/go/blob/3901409b5d0fb7c85a3e6730a59943cc93b2835c/src/debug/buildinfo/buildinfo.go 。
这里没有把未带来源的复杂图形默认为J类：已识别的Lucide线索已按L001彻底替换并归因。

## 结论与剩余操作

限定在逐文件登记并通过完整性检查的源码范围，本次**未决第三方来源项为0**；识别到的复制/改编材料
均有固定来源、适用许可、保留声明及处理结果。MIT/ISC可在拟议GPLv3组合中保留原通知；第三方不改授or-later。

个人声明不变：Copyright (C) 2026 inkzcz。source_third_party_review_complete 表示本次技术审核结果；
original_rights_confirmed、owner_authorization、selected_spdx 仍等待最终授权，不代填所有者许可/公开批准。
仍需所有者审核接受本次证据与修订、确认最终原创GPL范围、精确快照/目标仓库及公开操作；之后才能另行激活许可和导出。

Psycopg内附库源码/替换、wheel/Rust编译对应、Caddy生成配方和两项npm工具资料仍为C类，
不阻塞没有包含它们实现/二进制的源码。若未来加入这些实现须重新分类。Actions/Windows未执行如实保留；
UPGRADE-001不复现。本轮不构建或发布镜像，不访问NAS，不合并，不公开。

## 8e6ffb8之后的最终预览增量

本轮保留已完成的885文件范围来源结论，仅新增激活方案、开源声明和已知限制文档并更新README/安装说明及相关审核文本。它们是本准备任务的新原创说明，不加入新第三方代码或素材；原410法律文本、模板与图标实现不变。逐文件登记只更新这些内容/仓库名替换规则对应的指纹，不重新进行既有第三方全量取证。许可证与实际公开批准继续分开等待。

</details>
