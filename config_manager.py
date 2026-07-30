"""In-memory Pi models.json configuration management and persistence."""

import copy
import json
import os

from utils import ValidationError


class ConfigManager:
    """Owns the editable models.json dictionary and writes it safely."""

    def __init__(self, database, config_path=None):
        self.database = database
        self.config_path = config_path or os.path.expanduser("~/.pi/agent/models.json")
        self.config = {"providers": {}}
        self.load()

    @staticmethod
    def validate_config(config):
        if not isinstance(config, dict):
            raise ValidationError("配置根节点必须是 JSON 对象。")
        providers = config.get("providers")
        if not isinstance(providers, dict):
            raise ValidationError("配置必须包含对象类型的 providers 字段。")
        return config

    def load(self):
        directory = os.path.dirname(self.config_path)
        os.makedirs(directory, exist_ok=True)
        if not os.path.exists(self.config_path):
            self.config = {"providers": {}}
            self._write_without_backup()
            return self.config
        try:
            with open(self.config_path, "r", encoding="utf-8") as config_file:
                loaded = json.load(config_file)
            self.config = self.validate_config(loaded)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise RuntimeError("无法加载 Pi 配置文件：%s" % error) from error
        return self.config

    def _serialize(self, config=None):
        return json.dumps(config if config is not None else self.config, ensure_ascii=False, indent=2)

    def _write_without_backup(self):
        directory = os.path.dirname(self.config_path)
        os.makedirs(directory, exist_ok=True)
        temporary_path = self.config_path + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8", newline="\n") as config_file:
                config_file.write(self._serialize())
                config_file.write("\n")
            os.replace(temporary_path, self.config_path)
        except OSError as error:
            try:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)
            except OSError:
                pass
            raise RuntimeError("无法写入 Pi 配置文件：%s" % error) from error

    def save(self, create_backup=True):
        self.validate_config(self.config)
        if create_backup and os.path.isfile(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as config_file:
                    previous_json = config_file.read()
                json.loads(previous_json)
                self.database.create_backup(previous_json)
            except (OSError, json.JSONDecodeError) as error:
                raise RuntimeError("保存前无法备份当前配置：%s" % error) from error
        self._write_without_backup()

    def replace_config(self, config):
        self.config = copy.deepcopy(self.validate_config(config))
        self.save()

    def import_from_file(self, source_path):
        try:
            with open(source_path, "r", encoding="utf-8") as source_file:
                imported = json.load(source_file)
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("无法读取导入文件：%s" % error) from error
        self.replace_config(imported)

    def export_to_file(self, target_path):
        try:
            with open(target_path, "w", encoding="utf-8", newline="\n") as target_file:
                target_file.write(self._serialize())
                target_file.write("\n")
        except OSError as error:
            raise RuntimeError("无法导出配置：%s" % error) from error

    def add_provider(self, name, provider):
        name = name.strip()
        if not name:
            raise ValidationError("Provider 名称不能为空。")
        if name in self.config["providers"]:
            raise ValidationError("Provider 名称已存在。")
        provider = copy.deepcopy(provider)
        provider.setdefault("models", [])
        if not isinstance(provider["models"], list):
            raise ValidationError("Provider 的 models 必须是列表。")
        self.config["providers"][name] = provider
        self.save()

    def update_provider(self, name, provider_fields):
        if name not in self.config["providers"]:
            raise ValidationError("找不到所选 Provider。")
        provider = self.config["providers"][name]
        models = provider.get("models", [])
        provider.update(copy.deepcopy(provider_fields))
        provider["models"] = models
        self.save()

    def delete_provider(self, name):
        if name not in self.config["providers"]:
            raise ValidationError("找不到所选 Provider。")
        del self.config["providers"][name]
        self.save()

    def add_model(self, provider_name, model):
        provider = self._get_provider(provider_name)
        model_id = model.get("id", "").strip()
        if not model_id:
            raise ValidationError("模型 ID 不能为空。")
        if any(item.get("id") == model_id for item in provider.setdefault("models", [])):
            raise ValidationError("该 Provider 下的模型 ID 已存在。")
        provider["models"].append(copy.deepcopy(model))
        self.save()

    def update_model(self, provider_name, model_id, updated_model):
        provider = self._get_provider(provider_name)
        new_id = updated_model.get("id", "").strip()
        if not new_id:
            raise ValidationError("模型 ID 不能为空。")
        for index, model in enumerate(provider.setdefault("models", [])):
            if model.get("id") == model_id:
                if new_id != model_id and any(
                    item.get("id") == new_id for item in provider["models"]
                ):
                    raise ValidationError("该 Provider 下的模型 ID 已存在。")
                replacement = copy.deepcopy(updated_model)
                replacement["id"] = new_id
                provider["models"][index] = replacement
                self.save()
                return
        raise ValidationError("找不到所选模型。")

    def delete_model(self, provider_name, model_id):
        provider = self._get_provider(provider_name)
        models = provider.setdefault("models", [])
        for index, model in enumerate(models):
            if model.get("id") == model_id:
                del models[index]
                self.save()
                return
        raise ValidationError("找不到所选模型。")

    def _get_provider(self, name):
        try:
            return self.config["providers"][name]
        except KeyError as error:
            raise ValidationError("找不到所选 Provider。") from error
