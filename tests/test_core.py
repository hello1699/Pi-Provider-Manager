"""Unit tests for non-GUI Pi Provider Manager components."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from config_manager import ConfigManager
from database import Database, format_backup_time_local
from utils import (
    ModelListCache,
    ValidationError,
    build_models_url,
    fetch_provider_models,
    parse_json_object,
    provider_model_list_cache_key,
    validate_nonnegative_number,
)


class ConfigManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.temp_dir.name, "test.db"))
        self.config_path = os.path.join(self.temp_dir.name, "agent", "models.json")
        self.manager = ConfigManager(self.db, self.config_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def provider(self):
        return {
            "baseUrl": "https://example.com/v1",
            "api": "openai-completions",
            "apiKey": "test-key",
            "headers": {},
            "compat": {},
            "models": [],
        }

    def model(self, model_id="test-model"):
        return {
            "id": model_id,
            "reasoning": True,
            "input": ["text", "image"],
            "contextWindow": 128000,
            "maxTokens": 8192,
        }

    def test_initializes_empty_configuration_file(self):
        self.assertEqual({"providers": {}}, self.manager.config)
        with open(self.config_path, encoding="utf-8") as config_file:
            self.assertEqual({"providers": {}}, json.load(config_file))

    def test_provider_and_model_crud_creates_backups(self):
        self.manager.add_provider("example", self.provider())
        self.manager.add_model("example", self.model())
        self.assertEqual("test-model", self.manager.config["providers"]["example"]["models"][0]["id"])
        self.assertGreaterEqual(len(self.db.list_backups()), 2)

        updated = self.model("test-model")
        updated["maxTokens"] = 4096
        self.manager.update_model("example", "test-model", updated)
        self.assertEqual(4096, self.manager.config["providers"]["example"]["models"][0]["maxTokens"])
        self.manager.delete_model("example", "test-model")
        self.manager.delete_provider("example")
        self.assertEqual({}, self.manager.config["providers"])

    def test_rejects_duplicate_model_ids(self):
        self.manager.add_provider("example", self.provider())
        self.manager.add_model("example", self.model())
        with self.assertRaises(ValidationError):
            self.manager.add_model("example", self.model())

    def test_rejects_duplicate_model_id_when_renaming(self):
        self.manager.add_provider("example", self.provider())
        self.manager.add_model("example", self.model("first"))
        self.manager.add_model("example", self.model("second"))
        with self.assertRaises(ValidationError):
            self.manager.update_model("example", "first", self.model("second"))

    def test_rejects_invalid_config_structure(self):
        with self.assertRaises(ValidationError):
            self.manager.replace_config({"providers": []})

    def test_thinking_level_map_persists_and_can_be_replaced(self):
        self.manager.add_provider("example", self.provider())
        model = self.model()
        model["thinkingLevelMap"] = {
            "minimal": None,
            "low": None,
            "medium": None,
            "high": "high",
            "max": "max",
        }
        self.manager.add_model("example", model)
        self.assertEqual(model["thinkingLevelMap"], self.manager.config["providers"]["example"]["models"][0]["thinkingLevelMap"])
        with open(self.config_path, encoding="utf-8") as config_file:
            self.assertEqual(
                model["thinkingLevelMap"],
                json.load(config_file)["providers"]["example"]["models"][0]["thinkingLevelMap"],
            )

        updated = self.model()
        updated["thinkingLevelMap"] = {
            "minimal": "minimal",
            "low": None,
            "medium": "medium",
            "high": None,
            "max": None,
        }
        self.manager.update_model("example", "test-model", updated)
        self.assertEqual(
            updated["thinkingLevelMap"],
            self.manager.config["providers"]["example"]["models"][0]["thinkingLevelMap"],
        )

    def test_pause_and_resume_model_preserves_full_definition(self):
        self.manager.add_provider("example", self.provider())
        model = self.model()
        model["cost"] = {"input": 0.1, "output": 0.2, "cacheRead": 0.01, "cacheWrite": 0.02}
        model["thinkingLevelMap"] = {"minimal": None, "low": None, "medium": None, "high": "high", "max": "max"}
        self.manager.add_model("example", model)

        self.manager.pause_model("example", "test-model", "workspace")
        self.assertEqual([], self.manager.config["providers"]["example"]["models"])
        with open(self.config_path, encoding="utf-8") as config_file:
            self.assertEqual([], json.load(config_file)["providers"]["example"]["models"])
        paused_models = self.db.list_paused_models("workspace", "example")
        self.assertEqual(1, len(paused_models))
        self.assertEqual("test-model", paused_models[0][0])

        restarted_database = Database(os.path.join(self.temp_dir.name, "test.db"))
        restarted_manager = ConfigManager(restarted_database, self.config_path)
        restarted_manager.resume_model("example", "test-model", "workspace")
        self.assertEqual(model, restarted_manager.config["providers"]["example"]["models"][0])
        self.assertEqual([], restarted_database.list_paused_models("workspace", "example"))

    def test_resume_duplicate_keeps_paused_model(self):
        self.manager.add_provider("example", self.provider())
        self.manager.add_model("example", self.model())
        self.manager.pause_model("example", "test-model", "workspace")
        self.manager.add_model("example", self.model())
        with self.assertRaises(ValidationError):
            self.manager.resume_model("example", "test-model", "workspace")
        self.assertIsNotNone(self.db.get_paused_model("workspace", "example", "test-model"))

    def test_delete_provider_clears_current_scope_paused_models(self):
        self.manager.add_provider("example", self.provider())
        self.manager.add_model("example", self.model())
        self.manager.pause_model("example", "test-model", "workspace")
        self.manager.delete_provider("example", "workspace")
        self.assertEqual([], self.db.list_paused_models("workspace", "example"))


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(os.path.join(self.temp_dir.name, "test.db"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_profiles_and_backups(self):
        self.assertTrue(self.database.save_profile("work", '{"providers": {}}'))
        self.assertFalse(self.database.save_profile("work", "{}"))
        self.assertTrue(self.database.save_profile("work", '{"providers": {"x": {}}}', overwrite=True))
        self.assertEqual('{"providers": {"x": {}}}', self.database.get_profile("work"))
        self.assertEqual([("work",)], self.database.list_profiles())
        self.assertTrue(self.database.delete_profile("work"))

        self.database.create_backup('{"providers": {}}')
        first_backup_id = self.database.list_backups()[0][0]
        self.assertEqual('{"providers": {}}', self.database.get_backup(first_backup_id))
        self.database.create_backup('{"providers": {"second": {}}}')
        second_backup_id = self.database.list_backups()[0][0]

        self.assertTrue(self.database.delete_backup(first_backup_id))
        self.assertIsNone(self.database.get_backup(first_backup_id))
        self.assertEqual('{"providers": {"second": {}}}', self.database.get_backup(second_backup_id))
        self.assertFalse(self.database.delete_backup(999999))

    def test_backup_timestamp_uses_local_display_time(self):
        raw_time = "2026-01-15 12:34:56"
        expected = datetime(2026, 1, 15, 12, 34, 56, tzinfo=timezone.utc).astimezone().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self.assertEqual(expected, format_backup_time_local(raw_time))
        self.assertEqual(expected, format_backup_time_local("2026-01-15T12:34:56Z"))

    def test_invalid_backup_timestamp_is_preserved(self):
        self.assertEqual("not-a-timestamp", format_backup_time_local("not-a-timestamp"))

    def test_backups_keep_only_the_latest_ten_records(self):
        for index in range(12):
            self.database.create_backup('{"backup": %d}' % index)

        backups = self.database.list_backups()
        self.assertEqual(10, len(backups))
        self.assertEqual('{"backup": 11}', self.database.get_backup(backups[0][0]))
        self.assertEqual('{"backup": 2}', self.database.get_backup(backups[-1][0]))

    def test_delete_all_backups(self):
        for index in range(3):
            self.database.create_backup('{"backup": %d}' % index)

        self.assertEqual(3, self.database.delete_all_backups())
        self.assertEqual([], self.database.list_backups())
        self.assertEqual(0, self.database.delete_all_backups())

    def test_paused_models_are_scope_isolated_and_copyable(self):
        self.database.save_paused_model("first", "provider", "model", '{"id": "model"}')
        self.database.save_paused_model("second", "provider", "model", '{"id": "replacement"}')
        self.assertEqual('{"id": "model"}', self.database.get_paused_model("first", "provider", "model"))
        self.assertEqual('{"id": "replacement"}', self.database.get_paused_model("second", "provider", "model"))

        self.database.copy_paused_models("first", "profile")
        self.assertEqual('{"id": "model"}', self.database.get_paused_model("profile", "provider", "model"))
        self.assertTrue(self.database.delete_paused_model("profile", "provider", "model"))
        self.assertIsNone(self.database.get_paused_model("profile", "provider", "model"))
        self.database.clear_paused_models("first")
        self.assertEqual([], self.database.list_paused_models("first", "provider"))


class ModelListCacheTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.cache = ModelListCache(clock=lambda: self.now)

    def test_returns_cached_models_before_expiry_and_expires_at_three_minutes(self):
        self.cache.store(("provider", "signature"), ["first", "second"])
        self.assertEqual(["first", "second"], self.cache.get(("provider", "signature")))

        self.now += 180
        self.assertIsNone(self.cache.get(("provider", "signature")))

    def test_cached_models_are_copied_and_clear_removes_entries(self):
        key = ("provider", "signature")
        original = ["first"]
        self.cache.store(key, original)
        original.append("second")
        cached = self.cache.get(key)
        cached.append("third")
        self.assertEqual(["first"], self.cache.get(key))
        self.cache.clear()
        self.assertIsNone(self.cache.get(key))

    def test_provider_request_settings_produce_distinct_cache_keys(self):
        provider = {
            "baseUrl": "https://api.example.com",
            "apiKey": "first-key",
            "headers": {"X-Client": "ppm"},
        }
        first_key = provider_model_list_cache_key("example", provider)
        self.assertEqual(first_key, provider_model_list_cache_key("example", dict(provider)))

        changed_url = dict(provider, baseUrl="https://other.example.com")
        changed_key = dict(provider, apiKey="second-key")
        changed_headers = dict(provider, headers={"X-Client": "other"})
        self.assertNotEqual(first_key, provider_model_list_cache_key("example", changed_url))
        self.assertNotEqual(first_key, provider_model_list_cache_key("example", changed_key))
        self.assertNotEqual(first_key, provider_model_list_cache_key("example", changed_headers))
        self.assertNotEqual(first_key, provider_model_list_cache_key("other", provider))


class UtilsTests(unittest.TestCase):
    def test_models_url_appends_v1_only_when_needed(self):
        self.assertEqual("https://api.example.com/v1/models", build_models_url("https://api.example.com"))
        self.assertEqual("https://api.example.com/v1/models", build_models_url("https://api.example.com/v1/"))
        self.assertEqual("https://api.example.com/custom/v1/models", build_models_url("https://api.example.com/custom"))

    def test_json_object_validation(self):
        self.assertEqual({}, parse_json_object("", "Headers"))
        self.assertEqual({"X-Test": "yes"}, parse_json_object('{"X-Test": "yes"}', "Headers"))
        with self.assertRaises(ValidationError):
            parse_json_object("[]", "Headers")

    def test_cost_accepts_nonnegative_decimals(self):
        self.assertEqual(0.000003, validate_nonnegative_number("0.000003", "Cost.input"))
        self.assertEqual(0.0, validate_nonnegative_number("0", "Cost.output"))
        with self.assertRaises(ValidationError):
            validate_nonnegative_number("-0.01", "Cost.input")
        with self.assertRaises(ValidationError):
            validate_nonnegative_number("not-a-number", "Cost.input")

    @patch("utils.requests.get")
    def test_fetch_models_sends_auth_headers_and_normalizes_ids(self, mocked_get):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {
            "data": [{"id": "z-model"}, {"id": "a-model"}, {"id": "a-model"}, {"id": " "}, {}]
        }
        mocked_get.return_value = response
        provider = {
            "baseUrl": "https://api.example.com",
            "apiKey": "secret",
            "headers": {"Authorization": "Custom value", "X-Client": "ppm"},
        }

        success, model_ids = fetch_provider_models(provider)

        self.assertTrue(success)
        self.assertEqual(["a-model", "z-model"], model_ids)
        mocked_get.assert_called_once_with(
            "https://api.example.com/v1/models",
            headers={"Authorization": "Custom value", "X-Client": "ppm"},
            timeout=10,
        )

    @patch("utils.requests.get")
    def test_fetch_models_handles_invalid_payload_and_http_error(self, mocked_get):
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"object": "list"}
        mocked_get.return_value = response
        success, message = fetch_provider_models({"baseUrl": "https://api.example.com"})
        self.assertFalse(success)
        self.assertIn("data 数组", message)

        response.ok = False
        response.status_code = 401
        response.text = "Unauthorized"
        success, message = fetch_provider_models({"baseUrl": "https://api.example.com"})
        self.assertFalse(success)
        self.assertIn("HTTP 401", message)

    @patch("utils.requests.get")
    def test_fetch_models_handles_non_json_response(self, mocked_get):
        response = Mock(ok=True, status_code=200)
        response.json.side_effect = ValueError("invalid JSON")
        mocked_get.return_value = response
        success, message = fetch_provider_models({"baseUrl": "https://api.example.com"})
        self.assertFalse(success)
        self.assertIn("不是有效 JSON", message)


if __name__ == "__main__":
    unittest.main()
