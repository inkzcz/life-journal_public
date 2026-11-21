# 贡献与测试

本源码仍是未正式发布的 v5.1.9 候选。不要用自己的文章、照片、密码或通知 URL 测试。

后端使用 Python 3.12：安装 `backend/requirements-test.txt`，执行 `python -m pytest -q tests`。默认使用隔离 SQLite，PG 专用项明确跳过。完整 PG17 回归只允许对新建、可丢弃的测试库设置 `TEST_DATABASE_URL`，不能指向生产或 NAS，也不能公开打印该值。

前端：`cd frontend`，然后 `npm ci`、`npm test`、`npm run build`。

测试图片和 ZIP 由 `tests/conftest.py` 从合成 JSON 和 Pillow 色块生成，不复制私人媒体，不提交生成的 ZIP。原私有工作流、发布收据和 Git 历史相关测试不进入新仓库；业务、迁移、权限、导入、相册、日历及单业务镜像测试保留。排除清单在私有准备 PR 中逐项审阅，不以删除失败业务测试获得通过。

提交前运行 `python scripts/open_source_gate.py` 和完整脱敏的受信任 Gitleaks。真实 .env、数据、备份、TAR、截图和扫描原始结果不得进 Git。假 Token 在测试运行时用片段构造；不对整个 tests 目录豁免扫描。

使用分支和 PR；不得关闭迁移/备份门禁、改历史迁移哈希或把未执行检查标成功。新迁移授权须实际独立 PG17 恢复/试迁移证据。此前 v5.1.8 → v5.1.9 Maintenance 故障本轮按要求暂不复现。

CI 只有只读仓库权限，不上传私人文件，不发布镜像/Release。主许可证由所有者决定后，再建立贡献许可约定。
