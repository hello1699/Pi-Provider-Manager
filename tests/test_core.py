"""Unit tests for non-GUI Pi Provider Manager components."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from config_manager import ConfigManager
from database import Database, format_backup_time_local
from utils import ValidationError, build_models_url, fetch_provider_models, parse_json_object


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
