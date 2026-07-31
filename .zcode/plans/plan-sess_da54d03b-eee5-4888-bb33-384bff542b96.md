## 目标
在“添加模型 / 编辑模型”窗口的 Cost 区域正下方增加 `thinkingLevelMap` 配置区，提供固定的五项映射输入：`minimal`、`low`、`medium`、`high`、`max`。

每项都是可选文本值；保存时会始终生成完整的 `thinkingLevelMap` 对象，空白输入写为 JSON `null`，例如：

```json
"thinkingLevelMap": {
  "minimal": null,
  "low": null,
  "medium": null,
  "high": "high",
  "max": "max"
}
```

## 实现步骤

1. **模型编辑窗口 — `dialogs.py`**
   - 在 `ModelDialog` 中定义固定顺序的五个 thinking level 键。
   - 读取编辑中模型现有的 `thinkingLevelMap`：字符串值预填入对应输入框；`null`、缺失或非字符串值显示为空。
   - 在 Cost 四个输入框之后新增“Thinking Level Map（空白写入 null）”标题和五个单行输入框。
   - 保存时将输入值去除首尾空格；空值转换为 Python `None`（序列化为 JSON `null`），非空文本保留为字符串。
   - 无论新增还是编辑，都把包含五个固定键的完整 `thinkingLevelMap` 写入模型对象。这样用户清空已有值后会明确写为 `null`，不会被 `ui_main.py` 现有的编辑合并逻辑保留成旧值。
   - Cost 的现有“小数价格”行为不改动；仅调整表单行号和布局，确保新增控件与保存/取消按钮正确显示。

2. **持久化兼容性 — 不改 `config_manager.py`**
   - 现有 `add_model()` 与 `update_model()` 会深拷贝并保存完整模型字典，已可原样持久化嵌套 `thinkingLevelMap`。
   - 手动添加、获取远程模型后的逐个补全、以及编辑既有模型都会复用同一个 `ModelDialog`，因此无需为三条流程分别实现。

3. **文档 — `README.md`**
   - 扩展模型 JSON 示例，在 `cost` 后展示 `thinkingLevelMap`。
   - 增加说明：界面固定提供五个 Pi thinking level 映射项；留空会写入 `null`；填写内容会作为目标 Provider/模型接受的映射字符串保存。

4. **测试 — `tests/test_core.py`**
   - 为不依赖 Tk 的配置持久化增加测试：添加含完整 `thinkingLevelMap`（含 `None` 与字符串）的模型，验证内存与写出的 `models.json` 保持该对象和 JSON `null`。
   - 覆盖模型更新后该字段仍可替换为包含空值的完整五键映射，确保更新流程不会保留旧值。
   - 保留现有 Cost 小数、备份、网络获取等回归测试。

## 行为决策
- 输入框不限制目标值枚举：例如 `high` 可以映射为 `"high"`，也可按 Provider 实际要求填写别的字符串；程序只负责构造 Pi 所需映射结构。
- 只输出用户要求的五个标准键；编辑保存会规范化为该固定结构，不保留额外的非标准 mapping 键。
- `thinkingLevelMap` 会在每次模型保存时写入，即使五项全为空，也会保存为五个 `null`，严格满足“没填就写 null”。

## 验证
- 运行 `.venv/Scripts/python.exe -m unittest discover -s tests -v`。
- 运行 `.venv/Scripts/python.exe -m py_compile main.py config_manager.py database.py dialogs.py ui_main.py utils.py`。
- 启动应用，新增和编辑模型，确认五项预填、空值写为 `null`、填写值写为字符串，并确认 fetched-model 的补全窗口也包含此配置区。