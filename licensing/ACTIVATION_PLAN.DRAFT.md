# A阶段已获明确批准并执行；B阶段未批准

2026-11-21所有者明确接受b105f82022141892933e7f4c6f2028c4760c2042中的方案并批准A。
已按原文复制LICENSE，生成正式COPYRIGHT.md，并同步限定原创权利/授权字段与文档；未改授第三方内容。
当前状态见PHASE_A_AUTHORIZATION.json、proposal.json和根法律通知。下面保留原审核方案作为历史，不回写为此前已批准。
B须使用本次激活后新候选的精确提交/目标仓库/manifest与源码树SHA256，独立批准；不会沿用旧888文件预览哈希。
公开检查是本准备任务的操作门禁，不限制接收者根据GPL已有的权利。

<details>
<summary>b105f820中获审核的原激活方案</summary>

# GPL-3.0-or-later 激活方案（DRAFT，未批准、未生效）

目标为首次 v5.1.9 干净源码，拟议目标仓库 `inkzcz/life-journal_public`。
本文件是待审核方案，不是授权。根 LICENSE 仍不存在；proposal 的最终授权字段不因本方案改变。
Copyright (C) 2026 inkzcz 及已收到的个人开发声明保留，不重复索取。

## 授权范围

拟采用 GPL-3.0-or-later，仅覆盖所有者实际有权许可、受版权保护的 Life Journal 原创源码。
以 third_party/source-review.json 的逐文件记录与 SOURCE_REVIEW.md 为边界：
Alembic 模板骨架继续保留 MIT；Lucide 图标继续保留 ISC 及适用 Feather MIT；其他第三方文本和版权不改授。
复制/改编文件中只有所有者有权许可的原创增量属于拟议原创授权，不把上游部分一并声称为 inkzcz 原创。
依赖文件引用的 lunardate、Psycopg、Vue 等继续适用自己的许可。当前组合路径为 GPLv3；
原创部分 or-later 不保证未来 GPL 版本下全部依赖均兼容。

## 批准 A：只激活私有准备分支中的原创许可

只有所有者明确接受具体修订、上述范围并批准 A 后，才能逐项执行：

| 文件/状态 | 批准后才做的变更 |
| --- | --- |
| 根 LICENSE | 从 licensing/GPL-3.0.txt 逐字复制完整 GPLv3；SHA256 应为 3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986。正文不改，or-later 由原创通知明确。 |
| 原创通知 | 采用 ORIGINAL_CODE_NOTICE.DRAFT.txt 中的拟议通知为根 COPYRIGHT.md，去掉仅属候选的说明；保留 Copyright (C) 2026 inkzcz、version 3 or any later version 及第三方范围例外。 |
| licensing/proposal.json | 只有得到真实批准后才设 state=owner-confirmed、selected_spdx=GPL-3.0-or-later、owner_authorization=true、original_rights_confirmed=true；第三方不改授，source-only 不变。 |
| README、licensing说明、source-scope | 同步生效范围，采用下方最终段落；不宣称正式v5.1.9 Release或完整升级验收。 |
| 许可状态契约测试 | 经批准后更新当前候选状态断言为已批准状态的严格断言；保留未授权/伪造LICENSE/独立公开批准负向用例，不删除或跳过门禁。 |
| 来源/导出登记 | 审核这些已批准的文本变化，更新逐文件来源及输入哈希；重新导出、校验与扫描，保留无原历史机制。 |

README 的授权段落候选（**以下文字此刻不生效，不直接替换当前README**）：

> Copyright (C) 2026 inkzcz。Life Journal 中所有者有权许可的原创源码以 GPL-3.0-or-later 授权，
> 详见 LICENSE 与 COPYRIGHT.md。实际包含的第三方源码及声明保留各自的 MIT、ISC 等许可与版权；
> 逐文件范围见 third_party/source-review.json 和 SOURCE_REVIEW.md。本次仅发布源码候选，
> 不提供预构建镜像、二进制或私人内容；v5.1.9 尚非正式 Release，已知限制见 docs/known-limitations.md。

不得批量把第三方文件的 SPDX/版权头改成项目许可，也不得把激活主许可当作可以改写上游通知的权限。
批准 A 只允许私有准备；不授权创建公开仓库、修改可见性、上传源码、合并或发布产物。

## 批准 B：另行批准实际公开操作

激活许可证会新增/更改文件，所以本轮预览的文件数及 SHA256 **不是**激活后的发布指纹。
完成 A 的已批准改动和必要验证后，须提供新的精确提交、文件清单、清单 SHA256、源码树 SHA256 及排除项，
再由所有者明确批准 B：只将该干净快照作为新仓库首个提交，不导入原 .git/refs/history。
目标仓库名本身不是创建权限，A 也不包含 B。私有准备 PR 的合并不是生成快照的前置条件。

source_third_party_review_complete、license/rights 确认和 publication_approved 是不同事实。
导出工具和预览收据不会创建仓库或上传内容；其 publication_approved 继续为 false。
采用了主许可的私有候选也仍须独立公开批准，不能从 --review-only 或 LICENSE 的有无推定批准 B。

未来 Docker/wheel/编译产物的对应源码、替换、NOTICE 等 C 类义务单独保留；本次不借源码批准发布二进制。
原私有仓库、main、PR #45、NAS、真实数据不在 A/B 的操作范围，除非另有明确授权。

</details>
