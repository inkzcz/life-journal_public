# 公开源码与未来二进制的再分发说明

有权许可的原创源码/原创增量已按明确A授权采用GPL-3.0-or-later；第三方许可/版权不改授，410法律文本保持原字节。
首次源码快照已公开，后续维护经公开分支和 PR 审核。原生库/对应源码/替换/NOTICE 等二进制义务继续归 C，不因源码公开自动完成。
首次 B 批准已绑定并公开指定快照，身份见 docs/initial-source-snapshot.json；它是准备操作授权，不增加 GPL 接收者限制。
下面是此前范围与依赖说明的历史背景；其中“主许可未定”不代表当前状态。

## v5.1.9 / v5.1.10 实际二进制的分发门禁

所有者已授权在必要法律条件和CI通过后正式发布；Windows/Z4S改为发布后待本地验收，UPGRADE-001保持历史已知问题，不再作为阻塞，也不绕过迁移保护。
授权记录独立于旧A/B源码授权；v5.1.9 见 licensing/BINARY_RELEASE_AUTHORIZATION.json，v5.1.10 见 licensing/BINARY_RELEASE_v5.1.10_AUTHORIZATION.json（旧授权不改）；第三方原有grant/版本/署名不改。

| 实际组件/义务 | 本次实现及失败条件 |
| --- | --- |
| 原创GPL-3.0-or-later | 根LICENSE/COPYRIGHT、完整当前应用源码、构建/安装文件同处交付；不导入原私有Git历史。当前组合使用GPLv3，不为第三方GPL/LGPL-only追加未来版本。 |
| Debian/PGDG的GPL/LGPL等组件 | 从实际dpkg Source/Version取得全部精确.dsc、orig/补丁文件；校验包名/版本、发布的SHA256和长度。snapshot的SHA1只是定位并额外校验，不冒称APT/上传者签名已验证；任何精确源文件缺失都失败。 |
| Psycopg / psycopg-c 3.3.9，LGPL-3.0-only | 从发布sdist编译C扩展，动态链接系统libpq，保留加速接口；不再交付psycopg-binary及其14个内附库。源码、编译器/libpq配置、pip实际来源收据提供；实际动态替换并查询合成PG17通过后才可打包。 |
| Pillow12.3.0内附库及LGPL FriBiDi shim | 保留原wheel功能、完整72KB级上游LICENSE/SBOM、对应Pillow sdist和首选源码/构建文件、FriBiDi来源/文本。实际修改shim源码、编译和重链接Pillow，再由UID10001加载、执行修改并验证接口；不把Psycopg的替换测试冒充Pillow重链接。未打包的可选libimagequant不得凭通用SBOM当作实际交付。 |
| Python与Rust | 精确PyPI sdist SHA256、实际pip安装artifact来源、Cargo.lock全部registry archive校验；base pip的vendoring源码/通知在其完整sdist中。CPython源码SHA取自固定基础镜像。保留MPL(certifi)、BSD/MIT/Apache及Unicode等具体义务。 |
| Caddy / Go | 读取实际二进制Go h1元数据，保留所有具名模块源码及原始LICENSE/NOTICE与Go运行时源码；生成根的等价构建配方在SOURCE_BUILD中。Apache/BSD组件不被误改授GPL，也不一概虚构GPL源码义务。 |
| 实际编译浏览器模块 | 按emitted chunks逐包保留通知，保存integrity匹配npm档案及不可变上游首选TS/JS源码提交。只交付实际模块源码，不把两个未打包开发工具的来源缺口带入源码交付。 |
| 替换/重组与用户权利 | 公开Library Corresponding Source、应用源码及实际可用的重建/安装方法；允许为调试库修改进行逆向工程，不增加合同禁止。源码身份校验不限制合法修改。 |
| 最终绑定与同处交付 | prepare_distribution对源码/证据目录做严格文件白名单和哈希检查，拒绝额外配置/ZIP/数据文件；包内DISTRIBUTION_MANIFEST绑定唯一业务TAR、config、源码提交/版本及验证收据；所有附件SHA256登记。源码和二进制同处免费提供，不签发无履约准备的书面offer。 |

410份既有法律文本保持原字节并随镜像/Web `/legal/` 提供，构建还读取实际包和浏览器通知。
历史参考目录不是整个当前二进制的完成证明；各组件合法性以本次实际源码、许可证和收据为依据。
镜像内binary-inventory/收集阶段清单是构建时事实记录，只有最终绑定的对应源码包记录完整交付门禁是否完成。
任何必需组件、通知、源码或替换验证缺失，流程在Artifact/Release上传之前失败；不能靠手填“complete=true”代替材料。

对应源码包可包含上游官方公开测试向量/版权身份；这些不代表项目私人数据。收集器只读取已验证业务TAR、公开上游和Git跟踪源码，不连接NAS或真实数据库。
同一业务镜像用于API/Web/Maintenance；PostgreSQL数据库镜像始终由部署者独立管理，交付工具不查询/构建/导出它。
完整重建与替换步骤见 SOURCE_BUILD.md，实际测试和哈希在逐构建附件收据中。

以下为旧准备阶段取证背景，旧TAR哈希与“未完成/主许可未选”等历史状态不能替代本轮实际结果。

<details>
<summary>已审核的依赖与分发义务背景</summary>

# 源码与未来二进制的第三方分发义务（分范围审核）

状态：私有审核，项目主许可证未选。保存声明不等同完成授权链、对应源码或发布验收。
本目录不构成 Life Journal 原创代码的主许可证。
所有者声明见 licensing/OWNER_DECLARATION.json；其拟议署名不替换本目录任何第三方版权。
个人开发声明不意味着全部第三方权利已审查，也不使 GPL 或公开授权生效。

## 本轮优先范围与 A/B/C/D

本轮只交付干净源码：应用源码/构建脚本、依赖引用、已核实版权文本；不附任何依赖实现包、镜像、wheel、native 库或编译前端。
实际范围见 SOURCE_DISTRIBUTION.md 与 source-scope.json。下方原 TAR 资料是未来二进制参考证据，不代表它在本次快照中。

| 类别 | 当前结论 |
| --- | --- |
| A 已完成 | 保留依赖声明和 409 份法律文本、GPL-2+ 来源证据、完整源码/无历史导出、可用本地验收；生产 lunardate 不换。 |
| B 首次源码前 | 个人开发/无其他开发者与雇主代码、拟议 Copyright (C) 2026 inkzcz 已声明；限定源码来源技术审核及署名已完成，见SOURCE_REVIEW.md；所有者审核接受证据/修订、最终原创GPL授权/范围、精确快照和公开批准仍待完成。 |
| C 未来二进制 | 实际打包的 wheel/内附库/系统程序对应源码、构建和许可资料、LGPL 替换验证、编译 JS 声明、镜像/升级验收。 |
| D Actions | 托管/Windows runner 与触发/权限集成未执行；本地测试不是 CI 通过，不等待托管 CI 恢复。 |

拟议 GPL-3.0-or-later 仅覆盖有权授予的原创部分。当前可用共同版本是 GPLv3；
GPL-3.0-only / LGPL-3.0-only 组件不会被追加未来授权，不保证未来 GPLv4 组合。
只有在源码快照实际复制相应代码时，组件缺少许可/来源才成为 B；仅引用构建依赖不能等同分发其二进制。
两项 npm 工具资料缺口、wheel 精确构建对应和内附库源码在当前范围属于 C，不阻塞一个不包含它们的源码快照。

## 实际核查对象

使用已有 Debian linux/amd64 单业务 TAR，SHA256
5acb09113ba3baf63e871ee28208aa0d364cdb06446425f7dc62eca84f01dd67。
读取最终层文件/白化、dpkg 状态、Python 元数据与版权、Caddy Go build info，
没有 docker load、执行镜像、构建、推送或数据库镜像访问。

- 163 个 Debian 包：全部可解析到镜像内原始 copyright，包括三项符号链接别名。
- 34 个 Python distribution 安装位置（含基础层和 venv 的 pip），33 个不同 name/version；
  另枚举两份 pip vendoring 清单共 36 项（同一 vendored 组件的重复安装位置不冒充不同项目）。
- 前端锁文件 209 项：从记录的 npm archive 按 SHA512 integrity 核验读取；
  原包缺声明时，记录匹配版本的来源包声明或 npm gitHead 对应源码声明，保留证据类型。
  这是包含 dev/平台可选包的保守清单，不声称每项都进入了浏览器 bundle。
- Caddy 使用 Go 1.27.3，147 个具名依赖 module 的源码 zip 均与二进制 h1 校验一致，
  版权文件已保存。另有一个构建器生成的 caddy (devel) 根，需保留实际生成/构建配方。
- Pydantic-core 2.50.5 sdist 的 Cargo.lock：101 个 registry crate 按 SHA256 核验，
  101 项均有原包或固定源码提交的许可资料；这是 source lock 的依赖超集，尚未证明与 wheel 编译开关完全对应。
- 32 个 wheel 内附共享库文件：Pillow 18 个、psycopg-binary 14 个；不能把 wheel 的顶层许可等同所有内附库许可。

redistribution-inventory.json 记录实际版本、路径、来源、校验方式和限制；
notice-index.json 按精确内容哈希映射到 licenses/evidence/，同文去重但不修改版权正文。
现有两份手工保留的许可继续保留。409 份不同路径的已登记文本中包含公共作者姓名/邮件，
这些是上游公开版权信息，不能为“脱敏”删掉。来源指向公共包/源码或已核查镜像路径。

## 义务矩阵

| 类别/实际实例 | 源码分发 | 编译前端、wheel 或镜像分发 |
| --- | --- | --- |
| MIT / MIT-CMU / ISC / BSD / Zlib / BlueOak | 保留各自版权、许可与免责声明；遵守具体变体条款 | 把要求的声明置于可获取文档/法律包/前端第三方声明中，不能仅依靠 minifier 未必保留的注释 |
| Apache-2.0：Caddy、部分 Python/Go/Rust | 保留 LICENSE、适用 NOTICE、修改标记 | 保留适用 NOTICE/版权和许可；尊重专利条款，不能只放一份没有各组件声明的 Apache 通用文本 |
| lunardate GPLv3 声明、GPLv2 来源注释 | 保存上游 GPL-2+ 与库 GPLv3 的来源证据，明确组合/原文件范围、版权和修改 | 适用 GPL 对应源码与交付方式；GPL-2+ 支持 GPLv3，不等于授予 MIT/Apache |
| Psycopg LGPL-3.0-only | 保留 LGPL/GPL 全文与版权，库修改按适用条款提供源码 | 完成 §4 所需库源码/可替换或重组机制及必要说明，内附库另审；不施加禁止为调试库修改而逆向工程的限制 |
| certifi MPL-2.0 | MPL 覆盖文件及其修改保持适用许可 | 提供 Covered Software 的源码获取说明及对应源码；不要求把所有独立应用文件改成 MPL |
| DOMPurify 双许可 | 可评估 Apache-2.0 分支，记录选择并保留声明 | 按所选择分支履约；不把整个应用当成双许可或漏掉声明 |
| Rust Unicode-3.0 / Unicode-DFS-2016 与 AND 条款 | 保留 Unicode 数据/软件版权和免责声明 | 即使选择 MIT/Apache 分支，AND 的 Unicode 条件仍需保留 |
| Debian 的 GPL/LGPL 程序、GCC runtime exception 等 | 按具体 package copyright 及源码许可处理 | 独立程序的聚合不自动把整个 Docker 所有原创代码变成 GPL；各程序和库的分发义务仍适用，不能只引用 Debian 镜像名称 |
| FreeType / IJG / 其他 Pillow 内附库 | 保留原声明及允许分支的条件 | 文档保留 FreeType 项目信用和 IJG 致谢，内附编解码器逐项核实 |

致谢：This product uses the FreeType Project (https://freetype.org/); original years and authors
are preserved in the bundled notices. This software is based in part on the work of the Independent JPEG Group.
这些致谢不替代其完整许可证，也不表示上游为本项目背书。

## 源码公开与二进制交付分开审核

1. 新无历史仓库应包含主许可证（所有者选择后）、声明、必要版权、对应构建/安装脚本和明确的依赖范围。
   不复制原 Git 历史或私有运行材料。引用依赖不是把第三方代码改授项目主许可。
2. 二进制法律包应绑定**同一个实际构建**的 TAR SHA256、配置身份、基础镜像 digest、所有实际软件版本、
   补丁、编译/链接选项、依赖声明和适用的对应源码。浮动依赖与基础镜像意味着必须逐构建重新生成，
   不能把本轮清单直接当成未来构建的完成证明。
3. 对 GPLv3/LGPLv3，优先评估 §6(d) 的同处免费对应源码交付方案；仅给上游 URL、仅提供应用源码或
   仅列版本不自动满足。若采用书面 offer，应先具备兑现其期限和范围的能力，本轮未承诺或签发 offer。
4. 对应源码可能包括修改、构建/安装脚本、生成代码所需输入以及适用链接/重组材料。
   是否满足 system library 例外需逐项判断；不能把整个 Debian 根文件系统笼统排除。
5. LGPL 可替换机制要在隔离环境验证：用接口兼容的修改库重新组合/重建并运行；
   明确用户有权这样做。源码身份检查不能被当作禁止合法库修改的合同条款。
6. 编译 Vue 资源应带适用第三方声明，主代码与编译输出适用的许可义务各自保留。
   Node/Alpine 构建阶段本体没有复制到最终 Debian 层；不将它们冒充最终镜像实际安装包。
7. 配套法律/源码归档不是额外 Docker 镜像；业务交付继续只有一个 TAR/一个业务镜像，
   API/Web/Maintenance 共用。NAS 独立管理的数据库镜像不打包、不查询、不拉取。

## C：仅针对未来编译产物／镜像的未完成事项

- 原创主许可与权属属于上方 B，而不是二进制专属缺口。当前保留现库，MIT 替换差异不再作为 GPL 路线前置条件。
- psycopg-binary 的 14 个内附原生库需要精确源码、构建版本/补丁及独立声明的完整核对。
  本轮保存 LGPL 文本不等同替这些库提供完整对应源码。
- Pydantic-core 源码 Cargo.lock 的 101 crate 已核验；仍需证明实际 wheel 编译对应关系，
  并核对其他原生扩展的静态/内嵌依赖。Go 生成根和构建配方也需归档。
- 两项 npm 开发工具 @napi-rs/lzma-linux-x64-gnu 与 de-indent 的原包/固定提交未提供可定位的完整许可文件。
  元数据声明 MIT，已记录该缺口；不编造版权年份或用不相关许可证替换。
  它们的 dev/平台用途与实际编译输出应另核实，不能据此宣称最终 bundle 有该二进制。
- 必须为实际计划发布的产物准备受控对应源码/声明获取方式及用户可替换验证，本轮未完成或公开。
- 本轮实际 TAR 构建早于新增法律包，不会自动包含这些新文件；未重打包或发布旧 TAR。
  后续构建须将适用声明纳入镜像或配套交付，逐构建检查，再完成真实容器验收。

因此，本轮完成了已核实材料的补齐与候选分析，**没有认定已满足未来完整二进制再分发条件**。

## 复核工具

scripts/license_evidence.py 是 stdlib 工具，不调用 Docker，不执行包代码，
读取单业务 Docker-save TAR 与 lockfile；npm 按 SHA512、Go 按二进制 h1 核验档案，
读取前有下载/展开上限，输出目录必须全新，失败保留私密 partial 并报告阶段/类型。

```sh
python scripts/license_evidence.py --image-archive /PRIVATE/app.tar \
  --frontend-lock frontend/package-lock.json --fetch-npm-archives --fetch-go-archives \
  --output-dir /PRIVATE/NEW/license-evidence
```

这重建原始证据，不自动批准元数据缺口、选择双许可分支或完成法律审核。
上游固定源码补充及本轮人工分类均记在 inventory/index；更新哈希前须审核实际变更，
不能用自动重新登记把不明个人信息当成版权资料放行。

UPGRADE-001、Windows/真实 Compose/load 验收及 Actions 账单限制继续按原审计记录，未复现历史升级。

补充保存 Debian lunar 2.2-10 的固定版权记录（GPL-2+，允许后续版本），来源见 inventory.lunardate_ancestry_evidence。另已纳入实际镜像 usr/share/common-licenses 的通用许可全文，避免只保留引用而漏掉 GPL-2/LGPL-2.1 等正文。

首次仅源码不会承诺对应原 TAR 的完整二进制源码包。未来把编译 JS 发送给浏览器也可能构成分发，应履行相应源码/通知义务；仅服务器运行 GPL 程序不等于 AGPL 网络条款，但不能据此忽略浏览器接收的代码。

## 本次实际源码复制材料

Alembic模板骨架按MIT保留Michael Bayer版权；13个图标使用固定Lucide来源并保留ISC及适用Feather MIT。
逐文件范围与处理见SOURCE_REVIEW.md和source-review.json；原409法律文本不改，另增一份Lucide许可。
这是本次源码义务，已处理；未来镜像须把适用声明实际带入产物，仍属C类，不据源码目录存在就宣称镜像已履约。

</details>
