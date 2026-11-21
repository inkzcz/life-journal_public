> 当前状态：原创 GPL-3.0-or-later 已激活，首次源码公开已完成。下方候选研究与 A/B 审批讨论保留为历史背景；当前许可由根 LICENSE/COPYRIGHT.md 确定，后续维护见 SOURCE_DISTRIBUTION.md。未来二进制义务仍独立适用。

# 已选择的原创许可：GPL-3.0-or-later（A已批准，B未批准）

所有者已明确选择并允许在私有准备分支激活有权许可且受版权保护的原创源码/原创增量。
当前法律通知为根LICENSE与COPYRIGHT.md；授权记录为licensing/PHASE_A_AUTHORIZATION.json。
MIT、ISC、GPLv3-only及其他第三方内容保留原条件；or-later选择不向第三方扩张，未来整体兼容性不保证。
技术来源审核已获所有者接受；owner_authorization仅为A，publication_approved继续false。
B须另行绑定新候选的提交/目标仓库/清单与源码树哈希，在快照外记录；门禁不附加GPL之外的接收者限制。

<details>
<summary>批准A之前的候选研究与方案（历史材料，不是当前授权状态）</summary>

# GPL 源码路线候选（尚未授权）

本候选保持完整 v5.1.9 功能与现有农历行为。
首次范围只公开干净源码，不交付镜像、wheel、编译前端、真实数据或旧 Git 历史。
优先研究 **GPL-3.0-or-later**；这是所有者要求评估的方向，不是已作出的许可或公开授权。
生产 lunardate==0.2.2 与日期行为保留，不采用已有全范围差异的 MIT 候选。

## GPL-3.0-only 与 GPL-3.0-or-later

| 原创代码范围 | version 3 | 后续版本 | 需要的权利 |
| --- | --- | --- | --- |
| GPL-3.0-only | 可以按 GPLv3 使用/修改/分发 | 不作后续版本授权 | 对原创贡献有权授予 GPLv3 |
| GPL-3.0-or-later（优先候选） | 同样可以按 GPLv3 使用/组合 | 接收者可为受该授权覆盖的原创部分选择后续 GPL | 权利人还必须有权授予该更宽范围，不能替他人追加授权 |

共同可用的当前组合版本是 GPLv3。原创部分选择 or-later，并不要求把所有独立第三方都改成
or-later；也不保证 GPLv4 等未来版本下整个组合可以分发。第三方 only、双许可、附加条件均保留。
未来若接收者选择更高 GPL 版本，需重新检查组件、选择允许分支、替换或取得许可。
不把“未来许可证可能存在”当作已经验证的兼容性。

GPL-3.0.txt 保存未经修改的 GPLv3 正文，ORIGINAL_CODE_NOTICE.DRAFT.txt 保存已填写拟议署名、仍为 DRAFT 的
原创通知。两者位于 licensing/，明确为候选，根 LICENSE 不存在；没有批量添加生效 SPDX。
2026-11-21 已收到个人开发/无其他开发者与雇主代码的声明，拟议通知使用 Copyright (C) 2026 inkzcz。
proposal.json 单独记录已收到声明；限定快照的第三方来源技术审核已完成，见 third_party/SOURCE_REVIEW.md；最终原创授权仍未作出。
即使单独添加 LICENSE，未确认最终 proposal 也不能非 review 导出。

## 原创权属：个人声明已收到，最终授权仍待确认

所有者于 2026-11-21 声明：个人主导，主要使用 ChatGPT / Codex 辅助，没有其他开发者，
不涉及公司或雇主代码；公开署名 inkzcz，拟议通知为 **Copyright (C) 2026 inkzcz**。
这些事实已记录在 licensing/OWNER_DECLARATION.json 与部分确认草案，不再列作未收到的声明。

功能基线祖先 241 提交、2 个作者记录、3 个提交者记录；两个作者组代表提交均关联 GitHub inkzcz。
工具与合并服务元数据不自动等于其他人类作者，也不构成权利转让证明。
私人原始核查材料不随快照公开；公开材料不含私人姓名/邮箱。

实际复制材料已逐项归因：Alembic模板骨架按MIT保留声明；13个来源未证实的图标已替换为固定Lucide路径并保留ISC/适用MIT。
source-review.json枚举全部交付文件；限定该范围的来源技术审核已完成，未决项0。
这是本次技术审核结果，不是仅凭个人声明签结第三方权利，也不批准最终GPL或公开。
proposal.original_rights_confirmed=false 表示最终源码权利审查未签结，不否认已收到的个人声明。
所有者审核接受本次来源证据/修订、最终原创许可范围及精确快照/公开批准后，才可按 licensing/README.md 激活。

## 第三方兼容性与实际分发范围

| 组件 | 已知资料 | 当前源码快照的处理 |
| --- | --- | --- |
| lunardate 0.2.2 | 包声明 GPLv3；祖先 lunar 2.2-10 有 GPL-2+ 明确后续版本证据 | 保留要求引用和原始通知；在 GPLv3 下有兼容路径。祖先 + 不证明 Python 包所有后续贡献也 +；不替第三方追加授权。 |
| Psycopg / binary | LGPL-3.0-only；前轮镜像观察为 3.3.9，本地测试环境另行记录实际版本 | 本次不复制库实现或 wheel；引用与通知保留。当前 GPLv3 下有组合路径；未来 native bundle/源码/用户替换义务另审。 |
| DOMPurify / certifi | 前者 MPL-2.0 OR Apache-2.0；后者 MPL-2.0 | 不复制实现/编译包；引用、许可与作用范围保留。实际复制或编译分发时按所选允许分支和 Covered Files 条件履行。 |
| Vue/TipTap/其他 npm、Go/Rust、系统包 | 先前实际版本及来源资料见 third_party | 本次仅依赖引用与公开法律文本，不把整个二进制依赖闭包冒称源码已附带。实际 vendoring 时重新检查许可与版权。 |
| 实际复制的模板/图标 | Alembic MIT；固定Lucide ISC/适用Feather MIT | 明确归因、保留版权与完整许可；旧图标来源未证实，以替换处理，不追认为原创。 |
| 原409份法律文本 + 新1份图标许可 | 固定来源/内容哈希，包含公开作者署名 | 原409项只核对一致性；全部保留原文，候选GPL不覆盖第三方。 |

源码实际范围见 SOURCE_DISTRIBUTION.md 和 third_party/source-scope.json。
两项 npm 工具缺许可文件、wheel 精确编译对应、Psycopg 内附原生库及 Caddy 生成配方，
在不包含那些实现/二进制的源码快照中属于 C 类参考项，不作为 B 类源码阻塞。
若后续把这些代码/二进制放入快照，必须重新分类，不能靠“源码发布”的名称豁免。

## 保留农历行为

MIT 候选 lunar-python 1.4.9 的先前实验仅作为历史研究证据：148,800 输入有 124 个正向差异，
73,058 个有效日期有 120 个反向差异，集中在 1933/1954/1978/2057；现有 21 项测试通过不足以证明替代。
本轮不替换、不再把替换完成作为 GPL 源码路线前置条件。
新增纪念日黄金日期回归保留这四年的原有接受性/结果以及春节映射，实际使用 lunardate。
GPLv3 路线可以保留现有功能，不需要先把这些差异当 bug 自动修正。

## A/B/C/D 状态

- **A 已完成**：GPL 候选全文/通知、源码范围与依赖分类、公共版权保留、无历史导出门禁和本地可用验收。本地验收结论由所有者审核；不能把未执行 CI 当作通过。
- **B 源码公开前必须**：所有者审核接受已完成的限定源码来源技术审核/修订、明确最终原创许可与范围、精确快照及公开操作（个人声明不重复索取）。未确认则维持私有 Draft。
- **C 未来二进制**：GPL/LGPL 对应源码/替换机制、native/wheel/生成配方与声明、实际镜像/编译前端的交付及部署验收。详见 third_party/REDISTRIBUTION.md。
- **D Actions 未验证**：托管 runner、触发/权限和 Windows 平台执行；本地测试不能冒称 CI 通过。按已记录本地证据准备源码，不把等待托管 CI 恢复作为本地验收前置。

UPGRADE-001 保留未知原因和未验收升级说明，不复现、不改生产。可公开未正式发布的源码候选及已知限制，
但不能因此宣称镜像、NAS 或历史升级就绪。

## 所有者的后续手动操作

审核接受本次来源证据/修订 → 明确最终 GPL 范围（拟议署名已收到） → 审核具体快照/日志和已知限制 → 明确授权 →
在准备分支采用真正的根 LICENSE/原创通知并更新 proposal → 重新登记输入、导出和扫描 →
由所有者创建全新无历史仓库及首个提交。保留原私有仓库，使用批准的干净导出快照创建全新历史。
这些只是说明，本任务没有执行许可激活、公开、Tag、Release、镜像推送或 NAS 操作。

## 一手资料

- https://www.gnu.org/licenses/gpl-3.0.html （§§5–6、版本选择 §14）
- https://www.gnu.org/licenses/gpl-faq.html#VersionThreeOrLater
- https://www.gnu.org/licenses/gpl-faq.html#AllCompatibility
- https://www.gnu.org/licenses/lgpl-3.0.html
- https://metadata.ftp-master.debian.org/changelogs/main/l/lunar/lunar_2.2-10_copyright
- https://pypi.org/project/lunardate/0.2.2/
- https://www.apache.org/licenses/LICENSE-2.0
- https://www.mozilla.org/en-US/MPL/2.0/FAQ/

## 本轮最终预览与分开批准

最终README/安装与开源声明已按待批准源码候选准备；具体许可证激活表及生效后README段落候选见licensing/ACTIVATION_PLAN.DRAFT.md（相对路径按仓库根目录）。A只批准私有分支的原创许可激活，B须另行批准激活后的精确快照和公开操作；本轮不执行A或B。

</details>
