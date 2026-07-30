"""Main Tkinter user interface for Pi Provider Manager."""

import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from dialogs import BackupDialog, FetchedModelsDialog, ModelDialog, ProviderDialog
from utils import ValidationError, fetch_provider_models, test_provider_connection


class MainWindow:
    def __init__(self, root, config_manager, database):
        self.root = root
        self.config_manager = config_manager
        self.database = database
        self.selected_provider = None
        self.pending_fetched_models = []
        self.pending_fetched_provider = None
        self.status_var = tk.StringVar(value="已加载配置。")
        self.profile_var = tk.StringVar()
        self._build_ui()
        self.refresh_all()

    def _build_ui(self):
        self.root.title("Pi Provider Manager")
        self.root.geometry("1180x720")
        self.root.minsize(960, 620)

        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)
        paned = ttk.PanedWindow(outer, orient="horizontal")
        paned.pack(fill="both", expand=True)

        provider_frame = ttk.LabelFrame(paned, text="Providers", padding=8)
        paned.add(provider_frame, weight=1)
        self.provider_tree = ttk.Treeview(provider_frame, columns=("name",), show="headings", selectmode="browse")
        self.provider_tree.heading("name", text="Provider 名称")
        self.provider_tree.column("name", minwidth=160, width=220, anchor="w")
        self.provider_tree.pack(fill="both", expand=True)
        self.provider_tree.bind("<<TreeviewSelect>>", self._on_provider_selected)
        provider_buttons = ttk.Frame(provider_frame)
        provider_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(provider_buttons, text="添加", command=self.add_provider).pack(side="left")
        ttk.Button(provider_buttons, text="编辑", command=self.edit_provider).pack(side="left", padx=5)
        ttk.Button(provider_buttons, text="删除", command=self.delete_provider).pack(side="left")

        right = ttk.Frame(paned)
        paned.add(right, weight=4)
        self._build_provider_details(right)
        self._build_models(right)
        self._build_global_actions(right)

        ttk.Separator(outer).pack(fill="x", pady=(8, 4))
        ttk.Label(outer, textvariable=self.status_var, anchor="w", relief="sunken", padding=(6, 3)).pack(fill="x")

    def _build_provider_details(self, parent):
        frame = ttk.LabelFrame(parent, text="当前 Provider 详情", padding=10)
        frame.pack(fill="x")
        frame.columnconfigure(1, weight=1)
        self.provider_detail_vars = {
            "baseUrl": tk.StringVar(),
            "api": tk.StringVar(),
            "apiKey": tk.StringVar(),
            "headers": tk.StringVar(),
            "compat": tk.StringVar(),
        }
        self.provider_detail_entries = {}
        labels = (("Base URL", "baseUrl"), ("API 类型", "api"), ("API Key", "apiKey"),
                  ("Headers", "headers"), ("Compat", "compat"))
        for row, (label, key) in enumerate(labels):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=3)
            show = "*" if key == "apiKey" else ""
            entry = ttk.Entry(frame, textvariable=self.provider_detail_vars[key], state="readonly", show=show)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            self.provider_detail_entries[key] = entry
        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="显示 API Key", variable=self.show_key_var, command=self._toggle_detail_key).grid(
            row=2, column=2, sticky="w", padx=(8, 0)
        )

    def _build_models(self, parent):
        frame = ttk.LabelFrame(parent, text="模型", padding=10)
        frame.pack(fill="both", expand=True, pady=(10, 0))
        columns = ("id", "context", "max_tokens", "reasoning", "input")
        self.model_tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "id": "ID", "context": "Context Window", "max_tokens": "Max Tokens",
            "reasoning": "Reasoning", "input": "Input",
        }
        widths = {"id": 210, "context": 130, "max_tokens": 120, "reasoning": 90, "input": 130}
        for column in columns:
            self.model_tree.heading(column, text=headings[column])
            self.model_tree.column(column, width=widths[column], minwidth=80, anchor="w")
        self.model_tree.pack(fill="both", expand=True)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="添加模型", command=self.add_model).pack(side="left")
        self.fetch_models_button = ttk.Button(buttons, text="获取模型列表", command=self.fetch_models)
        self.fetch_models_button.pack(side="left", padx=5)
        ttk.Button(buttons, text="编辑模型", command=self.edit_model).pack(side="left", padx=5)
        ttk.Button(buttons, text="删除模型", command=self.delete_model).pack(side="left")

    def _build_global_actions(self, parent):
        frame = ttk.LabelFrame(parent, text="全局操作", padding=10)
        frame.pack(fill="x", pady=(10, 0))
        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Button(top, text="导入配置", command=self.import_config).pack(side="left")
        ttk.Button(top, text="导出配置", command=self.export_config).pack(side="left", padx=5)
        ttk.Button(top, text="保存配置", command=self.manual_save).pack(side="left")
        self.test_button = ttk.Button(top, text="测试连接", command=self.test_connection)
        self.test_button.pack(side="left", padx=5)
        ttk.Button(top, text="查看备份", command=self.show_backups).pack(side="left")

        profiles = ttk.Frame(frame)
        profiles.pack(fill="x", pady=(8, 0))
        ttk.Label(profiles, text="配置方案").pack(side="left")
        self.profile_combo = ttk.Combobox(profiles, textvariable=self.profile_var, state="readonly", width=26)
        self.profile_combo.pack(side="left", padx=(8, 5))
        ttk.Button(profiles, text="保存为方案", command=self.save_profile).pack(side="left")
        ttk.Button(profiles, text="切换方案", command=self.switch_profile).pack(side="left", padx=5)
        ttk.Button(profiles, text="删除方案", command=self.delete_profile).pack(side="left")

    def refresh_all(self, keep_provider=None):
        providers = self.config_manager.config["providers"]
        desired = keep_provider if keep_provider in providers else self.selected_provider
        self.provider_tree.delete(*self.provider_tree.get_children())
        for name in providers:
            self.provider_tree.insert("", "end", iid=name, values=(name,))
        self.selected_provider = desired if desired in providers else None
        if self.selected_provider:
            self.provider_tree.selection_set(self.selected_provider)
            self.provider_tree.focus(self.selected_provider)
        self._refresh_provider_details()
        self._refresh_models()
        self.refresh_profiles()

    def refresh_profiles(self):
        names = [row[0] for row in self.database.list_profiles()]
        self.profile_combo["values"] = names
        if self.profile_var.get() not in names:
            self.profile_var.set("")

    def _on_provider_selected(self, _event=None):
        selected = self.provider_tree.selection()
        self.selected_provider = selected[0] if selected else None
        self._refresh_provider_details()
        self._refresh_models()

    def _refresh_provider_details(self):
        provider = self._current_provider()
        for key, variable in self.provider_detail_vars.items():
            value = provider.get(key, "") if provider else ""
            if key in ("headers", "compat") and value:
                value = json.dumps(value, ensure_ascii=False)
            variable.set(str(value))

    def _refresh_models(self):
        self.model_tree.delete(*self.model_tree.get_children())
        provider = self._current_provider()
        if not provider:
            return
        for index, model in enumerate(provider.get("models", [])):
            model_id = model.get("id", "")
            self.model_tree.insert(
                "", "end", iid=str(index), values=(
                    model_id, model.get("contextWindow", ""), model.get("maxTokens", ""),
                    "是" if model.get("reasoning") else "否", ", ".join(model.get("input", [])),
                )
            )

    def _toggle_detail_key(self):
        self.provider_detail_entries["apiKey"].configure(show="" if self.show_key_var.get() else "*")

    def _current_provider(self):
        if self.selected_provider:
            return self.config_manager.config["providers"].get(self.selected_provider)
        return None

    def _require_provider(self):
        if not self._current_provider():
            messagebox.showwarning("未选择 Provider", "请先在左侧选择一个 Provider。", parent=self.root)
            return False
        return True

    def _handle_action(self, action, success_message, keep_provider=None):
        try:
            action()
            self.refresh_all(keep_provider)
            self.set_status(success_message)
            return True
        except (RuntimeError, ValidationError, OSError, ValueError) as error:
            self.show_error("操作失败", error)
            return False

    def add_provider(self):
        ProviderDialog(self.root, on_save=self._save_new_provider)

    def _save_new_provider(self, name, fields):
        provider = dict(fields)
        provider["models"] = []
        self._handle_action(lambda: self.config_manager.add_provider(name, provider), "已添加 Provider：%s" % name, name)

    def edit_provider(self):
        if not self._require_provider():
            return
        provider = dict(self._current_provider())
        provider["name"] = self.selected_provider
        ProviderDialog(self.root, provider=provider, on_save=self._save_existing_provider)

    def _save_existing_provider(self, _name, fields):
        selected = self.selected_provider
        self._handle_action(lambda: self.config_manager.update_provider(selected, fields), "Provider 已更新。", selected)

    def delete_provider(self):
        if not self._require_provider():
            return
        name = self.selected_provider
        if messagebox.askyesno("确认删除", "删除 Provider “%s”及其全部模型？" % name, parent=self.root):
            self._handle_action(lambda: self.config_manager.delete_provider(name), "Provider 已删除。")

    def _selected_model(self):
        selected = self.model_tree.selection()
        provider = self._current_provider()
        if not selected or not provider:
            return None, None
        index = int(selected[0])
        models = provider.get("models", [])
        return (index, models[index]) if index < len(models) else (None, None)

    def add_model(self):
        if self._require_provider():
            ModelDialog(self.root, on_save=self._save_new_model)

    def _save_new_model(self, model):
        selected = self.selected_provider
        self._handle_action(lambda: self.config_manager.add_model(selected, model), "模型已添加。", selected)

    def fetch_models(self):
        if not self._require_provider():
            return
        provider_name = self.selected_provider
        provider = dict(self._current_provider())
        self.fetch_models_button.configure(state="disabled")
        self.set_status("正在获取 %s 的模型列表…" % provider_name)
        threading.Thread(target=self._run_fetch_models, args=(provider_name, provider), daemon=True).start()

    def _run_fetch_models(self, provider_name, provider):
        success, result = fetch_provider_models(provider)
        self.root.after(0, lambda: self._finish_fetch_models(provider_name, success, result))

    def _finish_fetch_models(self, provider_name, success, result):
        self.fetch_models_button.configure(state="normal")
        if not success:
            self.set_status(result)
            messagebox.showerror("获取模型列表失败", "%s\n\n%s" % (provider_name, result), parent=self.root)
            return
        if not result:
            message = "%s 未返回可用模型。" % provider_name
            self.set_status(message)
            messagebox.showinfo("获取模型列表", message, parent=self.root)
            return
        provider = self.config_manager.config["providers"].get(provider_name)
        if provider is None:
            message = "Provider “%s”已被删除，无法添加获取到的模型。" % provider_name
            self.set_status(message)
            messagebox.showwarning("Provider 不存在", message, parent=self.root)
            return
        existing_ids = {model.get("id") for model in provider.get("models", [])}
        available_count = len([model_id for model_id in result if model_id not in existing_ids])
        if not available_count:
            message = "获取到的 %d 个模型均已存在于 %s。" % (len(result), provider_name)
            self.set_status(message)
            messagebox.showinfo("获取模型列表", message, parent=self.root)
            return
        self.set_status("已获取 %d 个模型，其中 %d 个可添加。" % (len(result), available_count))
        FetchedModelsDialog(self.root, result, existing_ids, lambda ids: self._begin_fetched_model_batch(provider_name, ids))

    def _begin_fetched_model_batch(self, provider_name, model_ids):
        self.pending_fetched_provider = provider_name
        self.pending_fetched_models = list(model_ids)
        self._show_next_fetched_model_dialog()

    def _show_next_fetched_model_dialog(self):
        if not self.pending_fetched_models:
            self.pending_fetched_provider = None
            self.set_status("已完成所选模型的添加。")
            return
        provider_name = self.pending_fetched_provider
        provider = self.config_manager.config["providers"].get(provider_name)
        if provider is None:
            self._cancel_fetched_model_batch("Provider 已不存在，已取消余下模型的添加。")
            return
        model_id = self.pending_fetched_models.pop(0)
        existing_ids = {model.get("id") for model in provider.get("models", [])}
        if model_id in existing_ids:
            self.set_status("已跳过已存在的模型：%s" % model_id)
            self.root.after(0, self._show_next_fetched_model_dialog)
            return
        ModelDialog(
            self.root,
            model={"id": model_id},
            on_save=self._save_fetched_model,
            on_cancel=lambda: self._cancel_fetched_model_batch("已取消余下模型的添加。"),
        )

    def _save_fetched_model(self, model):
        provider_name = self.pending_fetched_provider
        if provider_name not in self.config_manager.config["providers"]:
            self._cancel_fetched_model_batch("Provider 已不存在，无法添加模型。")
            return
        if self._handle_action(
            lambda: self.config_manager.add_model(provider_name, model),
            "模型已添加：%s" % model.get("id", ""),
            provider_name,
        ):
            self.root.after(0, self._show_next_fetched_model_dialog)
        else:
            self._cancel_fetched_model_batch("添加失败，已取消余下模型的添加。")

    def _cancel_fetched_model_batch(self, message):
        self.pending_fetched_models = []
        self.pending_fetched_provider = None
        self.set_status(message)

    def edit_model(self):
        if not self._require_provider():
            return
        _index, model = self._selected_model()
        if not model:
            messagebox.showwarning("未选择模型", "请先选择一个模型。", parent=self.root)
            return
        ModelDialog(self.root, model=model, on_save=lambda updated: self._save_existing_model(model, updated))

    def _save_existing_model(self, original, updated):
        selected = self.selected_provider
        merged = dict(original)
        merged.update(updated)
        self._handle_action(
            lambda: self.config_manager.update_model(selected, original.get("id"), merged),
            "模型已更新。", selected,
        )

    def delete_model(self):
        if not self._require_provider():
            return
        _index, model = self._selected_model()
        if not model:
            messagebox.showwarning("未选择模型", "请先选择一个模型。", parent=self.root)
            return
        model_id = model.get("id", "")
        if messagebox.askyesno("确认删除", "删除模型 “%s”？" % model_id, parent=self.root):
            self._handle_action(
                lambda: self.config_manager.delete_model(self.selected_provider, model_id),
                "模型已删除。", self.selected_provider,
            )

    def manual_save(self):
        self._handle_action(self.config_manager.save, "配置已保存并创建备份。", self.selected_provider)

    def import_config(self):
        path = filedialog.askopenfilename(parent=self.root, title="导入 Pi 配置", filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")])
        if path and self._handle_action(lambda: self.config_manager.import_from_file(path), "配置已导入。"):
            self.selected_provider = None

    def export_config(self):
        path = filedialog.asksaveasfilename(
            parent=self.root, title="导出 Pi 配置", defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if path:
            self._handle_action(lambda: self.config_manager.export_to_file(path), "配置已导出。", self.selected_provider)

    def test_connection(self):
        if not self._require_provider():
            return
        provider_name = self.selected_provider
        provider = dict(self._current_provider())
        self.test_button.configure(state="disabled")
        self.set_status("正在测试 %s 的连接…" % provider_name)
        threading.Thread(target=self._run_connection_test, args=(provider_name, provider), daemon=True).start()

    def _run_connection_test(self, provider_name, provider):
        success, result = test_provider_connection(provider)
        self.root.after(0, lambda: self._finish_connection_test(provider_name, success, result))

    def _finish_connection_test(self, provider_name, success, result):
        self.test_button.configure(state="normal")
        self.set_status(result)
        if success:
            messagebox.showinfo("连接测试成功", "%s\n\n%s" % (provider_name, result), parent=self.root)
        else:
            messagebox.showerror("连接测试失败", "%s\n\n%s" % (provider_name, result), parent=self.root)

    def save_profile(self):
        name = simpledialog.askstring("保存为方案", "请输入方案名称：", parent=self.root)
        if not name:
            return
        name = name.strip()
        if not name:
            messagebox.showwarning("名称无效", "方案名称不能为空。", parent=self.root)
            return
        config_json = json.dumps(self.config_manager.config, ensure_ascii=False, indent=2)
        try:
            if not self.database.save_profile(name, config_json):
                if not messagebox.askyesno("方案已存在", "方案 “%s” 已存在，是否覆盖？" % name, parent=self.root):
                    return
                self.database.save_profile(name, config_json, overwrite=True)
            self.refresh_profiles()
            self.profile_var.set(name)
            self.set_status("方案已保存：%s" % name)
        except Exception as error:
            self.show_error("保存方案失败", error)

    def switch_profile(self):
        name = self.profile_var.get()
        if not name:
            messagebox.showwarning("未选择方案", "请先选择一个配置方案。", parent=self.root)
            return
        if not messagebox.askyesno("确认切换", "切换到方案 “%s”？当前配置会先自动备份。" % name, parent=self.root):
            return
        try:
            data = self.database.get_profile(name)
            if data is None:
                raise RuntimeError("找不到所选配置方案。")
            self.config_manager.replace_config(json.loads(data))
            self.selected_provider = None
            self.refresh_all()
            self.set_status("已切换到方案：%s" % name)
        except Exception as error:
            self.show_error("切换方案失败", error)

    def delete_profile(self):
        name = self.profile_var.get()
        if not name:
            messagebox.showwarning("未选择方案", "请先选择一个配置方案。", parent=self.root)
            return
        if messagebox.askyesno("确认删除", "删除方案 “%s”？" % name, parent=self.root):
            try:
                self.database.delete_profile(name)
                self.refresh_profiles()
                self.set_status("方案已删除：%s" % name)
            except Exception as error:
                self.show_error("删除方案失败", error)

    def show_backups(self):
        try:
            backups = self.database.list_backups()
            if not backups:
                messagebox.showinfo("配置备份", "暂时没有可用备份。", parent=self.root)
                return
            BackupDialog(self.root, backups, self.restore_backup, self.delete_backup)
        except Exception as error:
            self.show_error("读取备份失败", error)

    def delete_backup(self, backup_id):
        try:
            if not self.database.delete_backup(backup_id):
                raise RuntimeError("找不到所选备份。")
            self.set_status("备份已删除。")
            return True
        except Exception as error:
            self.show_error("删除备份失败", error)
            return False

    def restore_backup(self, backup_id):
        if not messagebox.askyesno("确认恢复", "恢复此备份？当前配置会先自动备份。", parent=self.root):
            return
        try:
            data = self.database.get_backup(backup_id)
            if data is None:
                raise RuntimeError("找不到所选备份。")
            self.config_manager.replace_config(json.loads(data))
            self.selected_provider = None
            self.refresh_all()
            self.set_status("备份已恢复。")
        except Exception as error:
            self.show_error("恢复备份失败", error)

    def set_status(self, message):
        self.status_var.set(message)

    def show_error(self, title, error):
        self.set_status("%s：%s" % (title, error))
        messagebox.showerror(title, str(error), parent=self.root)
