"""SQLite persistence for Pi Provider Manager profiles and backups."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def format_backup_time_local(backup_time):
    """Convert SQLite's UTC timestamp text to the current local display time."""
    if not isinstance(backup_time, str):
        return str(backup_time)
    try:
        normalized = backup_time.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            parsed = datetime.strptime(backup_time, "%Y-%m-%d %H:%M:%S")
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return backup_time


class Database:
    """Stores named configuration profiles and pre-save backups."""

    def __init__(self, db_path=None):
        if db_path is None:
            app_dir = os.path.expanduser("~/.pi-provider-manager")
            os.makedirs(app_dir, exist_ok=True)
            db_path = os.path.join(app_dir, "ppm.db")
        self.db_path = db_path
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    config_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    config_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS paused_models (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_name TEXT NOT NULL,
                    provider_name TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    model_json TEXT NOT NULL,
                    paused_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(scope_name, provider_name, model_id)
                )
                """
            )

    def create_backup(self, config_json):
        with self._connect() as connection:
            connection.execute("INSERT INTO backups (config_json) VALUES (?)", (config_json,))
            connection.execute(
                """
                DELETE FROM backups
                WHERE id NOT IN (
                    SELECT id FROM backups ORDER BY id DESC LIMIT 10
                )
                """
            )

    def list_backups(self):
        with self._connect() as connection:
            return connection.execute(
                "SELECT id, backup_time FROM backups ORDER BY id DESC"
            ).fetchall()

    def get_backup(self, backup_id):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT config_json FROM backups WHERE id = ?", (backup_id,)
            ).fetchone()
        return row[0] if row else None

    def delete_backup(self, backup_id):
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM backups WHERE id = ?", (backup_id,))
        return cursor.rowcount > 0

    def delete_all_backups(self):
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM backups")
        return cursor.rowcount

    def save_paused_model(self, scope_name, provider_name, model_id, model_json):
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO paused_models (scope_name, provider_name, model_id, model_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(scope_name, provider_name, model_id)
                DO UPDATE SET model_json = excluded.model_json, paused_at = CURRENT_TIMESTAMP
                """,
                (scope_name, provider_name, model_id, model_json),
            )

    def list_paused_models(self, scope_name, provider_name):
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT model_id, paused_at FROM paused_models
                WHERE scope_name = ? AND provider_name = ?
                ORDER BY model_id COLLATE NOCASE
                """,
                (scope_name, provider_name),
            ).fetchall()

    def get_paused_model(self, scope_name, provider_name, model_id):
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT model_json FROM paused_models
                WHERE scope_name = ? AND provider_name = ? AND model_id = ?
                """,
                (scope_name, provider_name, model_id),
            ).fetchone()
        return row[0] if row else None

    def list_paused_model_data(self, scope_name):
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT provider_name, model_json FROM paused_models
                WHERE scope_name = ? ORDER BY id
                """,
                (scope_name,),
            ).fetchall()

    def delete_paused_model(self, scope_name, provider_name, model_id):
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM paused_models
                WHERE scope_name = ? AND provider_name = ? AND model_id = ?
                """,
                (scope_name, provider_name, model_id),
            )
        return cursor.rowcount > 0

    def clear_paused_models(self, scope_name, provider_name=None):
        query = "DELETE FROM paused_models WHERE scope_name = ?"
        parameters = [scope_name]
        if provider_name is not None:
            query += " AND provider_name = ?"
            parameters.append(provider_name)
        with self._connect() as connection:
            connection.execute(query, parameters)

    def copy_paused_models(self, source_scope, target_scope):
        if source_scope == target_scope:
            return
        with self._connect() as connection:
            connection.execute("DELETE FROM paused_models WHERE scope_name = ?", (target_scope,))
            connection.execute(
                """
                INSERT INTO paused_models (scope_name, provider_name, model_id, model_json, paused_at)
                SELECT ?, provider_name, model_id, model_json, paused_at
                FROM paused_models WHERE scope_name = ?
                """,
                (target_scope, source_scope),
            )

    def paused_model_ids(self, scope_name, provider_name):
        return {model_id for model_id, _paused_at in self.list_paused_models(scope_name, provider_name)}

    def save_profile(self, name, config_json, overwrite=False):
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM profiles WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                if not overwrite:
                    return False
                connection.execute(
                    "UPDATE profiles SET config_json = ? WHERE name = ?",
                    (config_json, name),
                )
            else:
                connection.execute(
                    "INSERT INTO profiles (name, config_json) VALUES (?, ?)",
                    (name, config_json),
                )
        return True

    def list_profiles(self):
        with self._connect() as connection:
            return connection.execute(
                "SELECT name FROM profiles ORDER BY name COLLATE NOCASE"
            ).fetchall()

    def get_profile(self, name):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT config_json FROM profiles WHERE name = ?", (name,)
            ).fetchone()
        return row[0] if row else None

    def delete_profile(self, name):
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM profiles WHERE name = ?", (name,))
        return cursor.rowcount > 0
