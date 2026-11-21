# GPL-3.0-or-later 已按A阶段授权激活

所有者于2026-11-21明确批准，审核基线b105f82022141892933e7f4c6f2028c4760c2042。
根LICENSE逐字采用GPL-3.0.txt，SHA256为3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986。
正式COPYRIGHT.md采用Copyright (C) 2026 inkzcz，并规定GPL第3版或后续版本的选择权只及有权许可的原创源码和原创增量。
第三方MIT、ISC、GPLv3-only及其他组件继续保留各自许可、版权和版本选择，不被本项目改授。

## 授权范围与状态

PHASE_A_AUTHORIZATION.json是实际收到的所有者声明记录，不是伪造签名或独立司法权属认证。
proposal.state=owner-confirmed、selected_spdx=GPL-3.0-or-later、owner_authorization=true；
owner_authorization_scope仅为phase-a-original-source-license-only。
original_rights_confirmed=true仅对应owner-controlled-protectable-original-source-and-original-increments；
source_third_party_review_complete=true对应既有限定源码审核及本次获准的原创激活/门禁/文档增量。
publication_approved=false：A不批准创建仓库、公开推送、合并或发布产物。

根LICENSE与COPYRIGHT.md是当前法律通知；ORIGINAL_CODE_NOTICE.DRAFT.txt、OWNER_DECLARATION.json及旧确认草案
保留其原来的历史内容，不能把其中较早的未授权状态当成当前状态，也不回写成所有者当时已经批准。

## 第三方和版本选择

当前依赖组合路径为GPLv3；原创or-later不保证未来GPL版本下所有第三方组件均兼容。
lunardate0.2.2继续保留，不替换农历实现；祖先GPL-2+证据不被扩大为所有第三方贡献的未来版本授权。
Psycopg的LGPL-3.0-only、MIT/ISC及其他授权保持原文，详见third_party/SOURCE_REVIEW.md和REDISTRIBUTION.md。

## B阶段独立批准

许可证激活不等于本准备任务有权公开。新的私有源码候选及全部文件哈希已经重新生成，
需所有者对具体提交、目标仓库、manifest SHA256及源码树SHA256明确批准B。
B批准记录应在快照外；不得通过修改已哈希的proposal或manifest来宣称快照已获批准，否则哈希会变化。
--require-license只验证A；--require-publication另核对外部B记录和精确字节，不执行创建或上传。
这是对本准备任务操作的门禁，不是给合法GPL接收者附加许可限制。

原仓库继续Private，PR #46保持Draft；仅等待独立B批准，不执行公开、Tag/Release、镜像或NAS操作。
未来二进制的对应源码、LGPL替换、NOTICE和平台验收是C类事项，不混作当前不含这些二进制的源码条件。
