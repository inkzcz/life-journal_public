# 贡献与测试

当前源码版本为 v5.1.10，正式发行以通过门禁的 Release 附件为准。不要用自己的文章、照片、密码或通知 URL 测试。

后端使用 Python 3.12：安装 `backend/requirements-test.txt`，执行 `python -m pytest -q tests`。默认使用隔离 SQLite，PG 专用项明确跳过。完整 PG17 回归只允许对新建、可丢弃的测试库设置 `TEST_DATABASE_URL`，不能指向生产或 NAS，也不能公开打印该值。

前端：`cd frontend`，然后 `npm ci`、`npm test`、`npm run build`。

测试图片和 ZIP 由 `scripts/demo_fixtures.py` 从合成 JSON 和 Pillow 色块在内存生成，不复制私人媒体，不提交生成的 ZIP。原私有工作流、发布收据和 Git 历史相关测试不进入新仓库；业务、迁移、权限、导入、相册、日历及单业务镜像测试保留。当前来源和文件范围见 EXPORT_MANIFEST.json、third_party/source-review.json；维护更新必须逐项审核，不以删除失败业务测试获得通过。

提交前运行 `python scripts/open_source_gate.py` 和完整脱敏的受信任 Gitleaks。真实 .env、数据、备份、TAR、截图和扫描原始结果不得进 Git。假 Token 在测试运行时用片段构造；不对整个 tests 目录豁免扫描。

使用分支和 PR；不得关闭迁移/备份门禁、改历史迁移哈希或把未执行检查标成功。新迁移授权须实际独立 PG17 恢复/试迁移证据。此前 v5.1.8 → v5.1.9 Maintenance 故障只允许合成隔离分析，见 docs/upgrade-001.md。

普通 CI 只有只读仓库权限，不上传私人文件；独立正式发布作业只在完整门禁通过后持有最小写权限。正常版本按 [发布规范](docs/release-policy.md) 完成合并和可部署 Release，规则入口为 AGENTS.md。原创源码已按 GPL-3.0-or-later 授权；贡献者仅提交有权许可的原创贡献，保留第三方来源、许可及署名。
