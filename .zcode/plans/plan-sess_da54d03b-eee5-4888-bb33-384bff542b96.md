## 原因
备份表的 `backup_time` 使用 SQLite `CURRENT_TIMESTAMP` 自动生成；SQLite 该值是 UTC。当前窗口把该原始 UTC 文本直接显示，因此会和用户电脑的本地时区相差数小时。

## 修复方案

1. **保持数据库 UTC 存储 — `database.py`**
   - 不改表结构、不迁移数据，也不把数据库写入改成本地时间。
   - UTC 存储可避免电脑跨时区、夏令时切换时出现含义不明确的时间；现有和新建备份都能统一处理。

2. **增加显示时间格式化 — `database.py`**
   - 新增小型格式化函数，将 SQLite 既有的无时区格式 `YYYY-MM-DD HH:MM:SS` 明确按 UTC 解析。
   - 转换为当前电脑本地时区，并以 `YYYY-MM-DD HH:MM:SS` 显示。
   - 同时兼容 `Z` 和带偏移的 ISO 时间格式；若数据库时间意外损坏或无法解析，则原样显示，确保用户仍可恢复/删除备份。

3. **在备份窗口使用本地显示时间 — `dialogs.py`**
   - `BackupDialog` 填充 Treeview 时调用格式化函数，替换当前直接显示数据库原始字段的行为。
   - 备份 ID、恢复、删除和排序均保持不变；只改变用户看到的时间文本。

4. **补充测试 — `tests/test_core.py`**
   - 验证旧 SQLite UTC 文本转换后等于 Python 当前系统时区对应的值。
   - 验证带 `Z`/时区偏移的 ISO 格式。
   - 验证无效时间文本原样返回，避免列表功能受单条脏数据影响。

## 验证
- 运行 `.venv/Scripts/python.exe -m unittest discover -s tests -v`。
- 运行 `.venv/Scripts/python.exe -m py_compile main.py config_manager.py database.py dialogs.py ui_main.py utils.py`。
- 启动应用并检查“查看备份”中显示的时间与系统本地时间一致。