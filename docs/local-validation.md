# 不依赖 Actions 的源码验收

本地结果独立于 CI。所有日志、测试数据库、媒体和构建输出置于私密目录，不加入源码快照；
不要把已有 NAS/生产连接字符串传给测试。以下仅供所有者在隔离环境操作。

## 工具与依赖

Python 3.12、Node/npm（实际版本要记录）、Git、Gitleaks 8.30.1。需要 PostgreSQL 路径时只使用本机
已安装的 PG17 工具和新空目录，不查询/拉取数据库镜像。包版本记录 names/versions，勿输出完整环境或秘密。

```sh
python --version
node --version
npm --version
git --version
python -m pip install -r backend/requirements-test.txt
python -m pytest -q tests
```

上方测试默认临时 SQLite；先移除继承的 TEST_DATABASE_URL/DATABASE_URL 等部署配置。
记录退出码、passed/skipped/failed 数字、执行目录、精确提交和日志。跳过不算已验证。

## PG17 迁移与后端路径

明确选择一个新空的私密测试目录，initdb 使用测试用户，仅 Unix socket、listen_addresses=''；
新建测试数据库后才把其 URL 传给 TEST_DATABASE_URL。运行完整 pytest 与 tests/test_migrations.py。
结束后停止本次创建的集群，保留日志供审核。不要复用已有集群，不执行历史 Maintenance 故障复现驱动。
完整 pytest 的一般迁移/锁测试只针对新合成数据库，不等于复现 UPGRADE-001。

## 前端与可复现生产构建

```sh
cd frontend
npm ci
npm test
npm run build -- --outDir /PRIVATE/NEW/frontend-A
npm run build -- --outDir /PRIVATE/NEW/frontend-B
```

两个输出目录必须全新。固定 Node/npm、package-lock、相同源码与 LJ_BUILD_INFO/SOURCE_DATE_EPOCH；
逐文件比较 SHA256。记录 TypeScript/Vite 成功、产物数和是否字节一致。元数据可明确标为未验证源码模式，
不要把合成校验身份当成正式镜像来源。产物留在私密验收目录，不随源码公开。
这不证明 Docker 基础层、APT、浮动 pip 依赖或跨平台二进制可复现。

## 源码与许可门禁

```sh
python -m pytest -q tests/test_source_gpl_contract.py tests/test_open_source_gate.py tests/test_license_evidence.py
python scripts/open_source_gate.py --snapshot --root /PRIVATE/FRESH/SOURCE
# 使用已经核验的 Gitleaks 二进制，所有值脱敏：
gitleaks dir /PRIVATE/FRESH/SOURCE --redact=100 --no-banner --no-color --log-level=error
```

对干净、未运行测试的快照核对 EXPORT_MANIFEST.json 全部文件/SHA256；两次同提交/参数导出应完全一致。
测试会生成缓存和合成 ZIP，验证副本与最终交付副本分开，勿把运行后目录当干净源码。
409 份上游法律文本按 notice-index 精确哈希保留；邮箱例外仅用于已核验公共版权，不放行 Token/私钥。
未确认的主许可仍会阻止 require-license/非 review 导出，这是授权门禁，不是 CI 已通过。

原私有准备工具、权属材料和原始日志不会随快照导出。GPL 候选/声明仍待所有者确认；
GitHub 托管 runner、Node22/Windows runner 与事件权限未被其他版本 Linux 本地结果替代。
