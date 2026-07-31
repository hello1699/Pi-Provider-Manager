"""Tkinter dialogs used by Pi Provider Manager."""

import tkinter as tk
from tkinter import messagebox, ttk

from database import format_backup_time_local
from utils import (
    ValidationError,
    parse_json_object,
    validate_nonnegative_number,
    validate_positive_int,
    validate_url,
)


class ProviderDialog(tk.Toplevel):
    def __init__(self, parent, provider=None, on_save=None):
        super().__init__(parent)
        self.title("编辑 Provider" if provider else "添加 Provider")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.on_save = on_save
        self.is_editing = provider is not None
        provider = provider or {}

        self.name_var = tk.StringVar(value=provider.get("name", ""))
        self.base_url_var = tk.StringVar(value=provider.get("baseUrl", ""))
        self.api_var = tk.StringVar(value=provider.get("api", "openai-completions"))
        self.api_key_var = tk.StringVar(value=provider.get("apiKey", ""))
        self.key_visible = tk.BooleanVar(value=False)

        form = ttk.Frame(self, padding=12)
        form.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        self._entry(form, 0, "名称", self.name_var, state="disabled" if self.is_editing else "normal")
        self._entry(form, 1, "Base URL", self.base_url_var)
        self._entry(form, 2, "API 类型", self.api_var)
        self._entry(form, 3, "API Key", self.api_key_var, show="*")
        self.key_entry = self._last_entry
        ttk.Checkbutton(form, text="显示 API Key", variable=self.key_visible, command=self._toggle_key).grid(
            row=3, column=2, padx=(8, 0), sticky="w"
        )

        ttk.Label(form, text="Headers（JSON 对象）").grid(row=4, column=0, sticky="nw", pady=(8, 0))
        self.headers_text = tk.Text(form, height=5, width=48)
        self.headers_text.grid(row=4, column=1, columnspan=2, sticky="nsew", pady=(8, 0))
        self.headers_text.insert("1.0", self._pretty(provider.get("headers", {})))
        ttk.Label(form, text="Compat（JSON 对象）").grid(row=5, column=0, sticky="nw", pady=(8, 0))
        self.compat_text = tk.Text(form, height=5, width=48)
        self.compat_text.grid(row=5, column=1, columnspan=2, sticky="nsew", pady=(8, 0))
        self.compat_text.insert("1.0", self._pretty(provider.get("compat", {})))
        form.rowconfigure(4, weight=1)
        form.rowconfigure(5, weight=1)

        buttons = ttk.Frame(form)
        buttons.grid(row=6, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="保存", command=self._save).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _event: self.destroy())

    @staticmethod
    def _pretty(value):
        import json
        return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False, indent=2)

    def _entry(self, parent, row, label, variable, **kwargs):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        self._last_entry = ttk.Entry(parent, textvariable=variable, width=50, **kwargs)
        self._last_entry.grid(row=row, column=1, sticky="ew", pady=4)

    def _toggle_key(self):
        self.key_entry.configure(show="" if self.key_visible.get() else "*")

    def _save(self):
        try:
            name = self.name_var.get().strip()
            if not name:
                raise ValidationError("Provider 名称不能为空。")
            data = {
                "baseUrl": validate_url(self.base_url_var.get()),
                "api": self.api_var.get().strip() or "openai-completions",
                "apiKey": self.api_key_var.get(),
                "headers": parse_json_object(self.headers_text.get("1.0", "end-1c"), "Headers"),
                "compat": parse_json_object(self.compat_text.get("1.0", "end-1c"), "Compat"),
            }
            self.on_save(name, data)
            self.destroy()
        except (ValidationError, ValueError) as error:
            messagebox.showerror("输入无效", str(error), parent=self)


class ModelDialog(tk.Toplevel):
    COST_FIELDS = ("input", "output", "cacheRead", "cacheWrite")
    THINKING_LEVEL_FIELDS = ("minimal", "low", "medium", "high", "max")

    def __init__(self, parent, model=None, on_save=None, on_cancel=None):
        super().__init__(parent)
        self.title("编辑模型" if model else "添加模型")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.on_save = on_save
        self.on_cancel = on_cancel
        model = model or {}
        cost = model.get("cost", {}) if isinstance(model.get("cost", {}), dict) else {}
        thinking_level_map = (
            model.get("thinkingLevelMap", {})
            if isinstance(model.get("thinkingLevelMap", {}), dict)
            else {}
        )

        self.id_var = tk.StringVar(value=model.get("id", ""))
        self.context_var = tk.StringVar(value=str(model.get("contextWindow", "")))
        self.max_tokens_var = tk.StringVar(value=str(model.get("maxTokens", "")))
        self.reasoning_var = tk.BooleanVar(value=bool(model.get("reasoning", False)))
        inputs = model.get("input", [])
        self.text_var = tk.BooleanVar(value="text" in inputs)
        self.image_var = tk.BooleanVar(value="image" in inputs)
        self.cost_vars = {key: tk.StringVar(value=str(cost.get(key, ""))) for key in self.COST_FIELDS}
        self.thinking_level_vars = {
            key: tk.StringVar(
                value=thinking_level_map[key] if isinstance(thinking_level_map.get(key), str) else ""
            )
            for key in self.THINKING_LEVEL_FIELDS
        }

        form = ttk.Frame(self, padding=12)
        form.grid(sticky="nsew")
        form.columnconfigure(1, weight=1)
        self._entry(form, 0, "模型 ID", self.id_var)
        self._entry(form, 1, "Context Window", self.context_var)
        self._entry(form, 2, "Max Tokens", self.max_tokens_var)
        ttk.Checkbutton(form, text="支持 Reasoning", variable=self.reasoning_var).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(form, text="Input 类型").grid(row=4, column=0, sticky="w", pady=4)
        inputs_frame = ttk.Frame(form)
        inputs_frame.grid(row=4, column=1, sticky="w")
        ttk.Checkbutton(inputs_frame, text="text", variable=self.text_var).pack(side="left")
        ttk.Checkbutton(inputs_frame, text="image", variable=self.image_var).pack(side="left", padx=(10, 0))
        ttk.Separator(form).grid(row=5, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(form, text="Cost（可选，全部填写或全部留空）").grid(row=6, column=0, columnspan=2, sticky="w")
        for row, key in enumerate(self.COST_FIELDS, start=7):
            self._entry(form, row, key, self.cost_vars[key])
        ttk.Separator(form).grid(row=11, column=0, columnspan=2, sticky="ew", pady=8)
        ttk.Label(form, text="Thinking Level Map（空白写入 null）").grid(
            row=12, column=0, columnspan=2, sticky="w"
        )
        for row, key in enumerate(self.THINKING_LEVEL_FIELDS, start=13):
            self._entry(form, row, key, self.thinking_level_vars[key])
        buttons = ttk.Frame(form)
        buttons.grid(row=18, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=self._cancel).pack(side="right")
        ttk.Button(buttons, text="保存", command=self._save).pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _event: self._cancel())

    def _entry(self, parent, row, label, variable):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable, width=38).grid(row=row, column=1, sticky="ew", pady=4)

    def _cancel(self):
        if self.on_cancel:
            self.on_cancel()
        self.destroy()

    def _save(self):
        try:
            model_id = self.id_var.get().strip()
            if not model_id:
                raise ValidationError("模型 ID 不能为空。")
            inputs = []
            if self.text_var.get():
                inputs.append("text")
            if self.image_var.get():
                inputs.append("image")
            if not inputs:
                raise ValidationError("至少选择一种 Input 类型。")
            values = {key: variable.get().strip() for key, variable in self.cost_vars.items()}
            filled = [value for value in values.values() if value]
            if filled and len(filled) != len(values):
                raise ValidationError("Cost 的四个字段需要全部填写或全部留空。")
            model = {
                "id": model_id,
                "reasoning": self.reasoning_var.get(),
                "input": inputs,
                "contextWindow": validate_positive_int(self.context_var.get(), "Context Window"),
                "maxTokens": validate_positive_int(self.max_tokens_var.get(), "Max Tokens"),
            }
            if filled:
                model["cost"] = {
                    key: validate_nonnegative_number(value, "Cost.%s" % key)
                    for key, value in values.items()
                }
            model["thinkingLevelMap"] = {
                key: self.thinking_level_vars[key].get().strip() or None
                for key in self.THINKING_LEVEL_FIELDS
            }
            self.on_save(model)
            self.destroy()
        except (ValidationError, ValueError) as error:
            messagebox.showerror("输入无效", str(error), parent=self)


class FetchedModelsDialog(tk.Toplevel):
    """Lets users select remotely discovered model IDs before editing their Pi metadata."""

    def __init__(self, parent, model_ids, existing_ids, on_confirm, paused_ids=None):
        super().__init__(parent)
        self.title("获取到的模型列表")
        self.geometry("500x430")
        self.minsize(400, 300)
        self.transient(parent)
        self.grab_set()
        self.on_confirm = on_confirm
        paused_ids = paused_ids or set()
        self.available_ids = [model_id for model_id in model_ids if model_id not in existing_ids]

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text="选择要添加的模型。远程接口通常仅返回 ID，下一步需逐个填写 Pi 参数。",
            wraplength=460,
        ).pack(anchor="w", pady=(0, 8))
        self.tree = ttk.Treeview(frame, columns=("id", "status"), show="headings", selectmode="extended")
        self.tree.heading("id", text="模型 ID")
        self.tree.heading("status", text="状态")
        self.tree.column("id", width=340, anchor="w")
        self.tree.column("status", width=120, anchor="center")
        self.tree.tag_configure("existing", foreground="#777777")
        for index, model_id in enumerate(model_ids):
            is_paused = model_id in paused_ids
            exists = model_id in existing_ids and not is_paused
            status = "已暂停" if is_paused else ("已存在" if exists else "可添加")
            self.tree.insert(
                "", "end", iid=str(index), values=(model_id, status),
                tags=("existing",) if status != "可添加" else (),
            )
        self.tree.pack(fill="both", expand=True)

        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(10, 0))
        ttk.Button(controls, text="全选可添加项", command=self._select_available).pack(side="left")
        ttk.Button(controls, text="清空选择", command=lambda: self.tree.selection_remove(self.tree.selection())).pack(
            side="left", padx=5
        )
        ttk.Button(controls, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(controls, text="添加所选", command=self._confirm).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _event: self.destroy())

    def _select_available(self):
        selected = []
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, "values")
            if values[1] == "可添加":
                selected.append(item_id)
        self.tree.selection_set(selected)

    def _confirm(self):
        selected_ids = []
        for item_id in self.tree.selection():
            model_id, status = self.tree.item(item_id, "values")
            if status == "可添加":
                selected_ids.append(model_id)
        if not selected_ids:
            messagebox.showwarning("未选择模型", "请至少选择一个状态为“可添加”的模型。", parent=self)
            return
        self.on_confirm(selected_ids)
        self.destroy()


class PausedModelsDialog(tk.Toplevel):
    """Shows paused models for one provider and lets the user restore one."""

    def __init__(self, parent, paused_models, on_resume):
        super().__init__(parent)
        self.title("已暂停模型")
        self.geometry("500x330")
        self.minsize(400, 250)
        self.transient(parent)
        self.grab_set()
        self.on_resume = on_resume
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=("id", "time"), show="headings", selectmode="browse")
        self.tree.heading("id", text="模型 ID")
        self.tree.heading("time", text="暂停时间")
        self.tree.column("id", width=280, anchor="w")
        self.tree.column("time", width=180, anchor="w")
        for model_id, paused_at in paused_models:
            self.tree.insert("", "end", iid=model_id, values=(model_id, format_backup_time_local(paused_at)))
        self.tree.pack(fill="both", expand=True)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="恢复选中模型", command=self._resume).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda _event: self.destroy())

    def _resume(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("未选择模型", "请先选择一个已暂停模型。", parent=self)
            return
        model_id = selected[0]
        if self.on_resume(model_id):
            self.tree.delete(model_id)
            if not self.tree.get_children():
                self.destroy()


class BackupDialog(tk.Toplevel):
    def __init__(self, parent, backups, on_restore, on_delete, on_delete_all):
        super().__init__(parent)
        self.title("配置备份")
        self.geometry("420x300")
        self.transient(parent)
        self.grab_set()
        self.on_restore = on_restore
        self.on_delete = on_delete
        self.on_delete_all = on_delete_all
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=("time",), show="headings", selectmode="browse")
        self.tree.heading("time", text="备份时间")
        self.tree.column("time", width=360, anchor="w")
        for backup_id, backup_time in backups:
            self.tree.insert("", "end", iid=str(backup_id), values=(format_backup_time_local(backup_time),))
        self.tree.pack(fill="both", expand=True)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="恢复选中备份", command=self._restore).pack(side="right", padx=(0, 8))
        ttk.Button(buttons, text="删除选中备份", command=self._delete).pack(side="right", padx=(0, 8))
        ttk.Button(buttons, text="全部删除", command=self._delete_all).pack(side="left")

    def _selected_backup_id(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("未选择备份", "请先选择一条备份记录。", parent=self)
            return None
        return int(selected[0])

    def _restore(self):
        backup_id = self._selected_backup_id()
        if backup_id is None:
            return
        self.on_restore(backup_id)
        self.destroy()

    def _delete(self):
        backup_id = self._selected_backup_id()
        if backup_id is None:
            return
        if self.on_delete(backup_id):
            self.tree.delete(str(backup_id))
            if not self.tree.get_children():
                self.destroy()

    def _delete_all(self):
        if self.on_delete_all():
            self.destroy()
