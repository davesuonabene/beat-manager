import os
import sqlite3
import json
import logging
import re
from typing import Any, List, Dict, Optional

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self, db_path=None):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        
        if db_path is None:
            self.db_path = os.path.join(project_root, "state.db")
            self.old_json_path = os.path.join(project_root, "state.json")
        else:
            if db_path.endswith(".json"):
                self.db_path = db_path[:-5] + ".db"
                self.old_json_path = db_path
            else:
                self.db_path = db_path
                self.old_json_path = db_path.replace(".db", ".json")

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        
        # Automatic Migration from TinyDB
        if os.path.exists(self.old_json_path):
            self._migrate_from_json()

    def _create_tables(self):
        cursor = self.conn.cursor()
        # Tasks Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT,
                target TEXT,
                status TEXT,
                project_tag TEXT,
                details TEXT,
                log TEXT
            )
        """)
        # Settings Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # Folders Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                path TEXT PRIMARY KEY
            )
        """)
        # YouTube Uploads Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS yt_uploads (
                id TEXT PRIMARY KEY,
                video_file_path TEXT,
                thumbnail_file_path TEXT,
                title TEXT,
                description TEXT,
                tags TEXT,
                category_id TEXT,
                privacy_status TEXT,
                publish_at TEXT,
                status TEXT,
                created_at TEXT,
                youtube_id TEXT
            )
        """)
        # Audio Assets Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audio_assets (
                path TEXT PRIMARY KEY,
                filename TEXT,
                duration REAL,
                sample_rate INTEGER,
                bit_depth INTEGER,
                format TEXT,
                parent_folder TEXT
            )
        """)
        
        # Library Assets (Beats) Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS library_assets (
                id TEXT PRIMARY KEY,
                name TEXT,
                path TEXT,
                data_type TEXT,
                asset_type TEXT,
                created_at TEXT,
                versions TEXT,
                metadata TEXT,
                tags TEXT,
                stems_id TEXT,
                duration REAL,
                selected_version TEXT
            )
        """)
        
        # Migration: Add duration column if it doesn't exist
        try:
            cursor.execute("SELECT duration FROM library_assets LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("Adding duration column to library_assets table...")
            cursor.execute("ALTER TABLE library_assets ADD COLUMN duration REAL DEFAULT 0")

        # Migration: Add tags column if it doesn't exist
        try:
            cursor.execute("SELECT tags FROM library_assets LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("Adding tags column to library_assets table...")
            cursor.execute("ALTER TABLE library_assets ADD COLUMN tags TEXT")
            
        # Migration: Add stems_id column if it doesn't exist
        try:
            cursor.execute("SELECT stems_id FROM library_assets LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("Adding stems_id column to library_assets table...")
            cursor.execute("ALTER TABLE library_assets ADD COLUMN stems_id TEXT")

        # Migration: Add selected_version column if it doesn't exist
        try:
            cursor.execute("SELECT selected_version FROM library_assets LIMIT 1")
        except sqlite3.OperationalError:
            logger.info("Adding selected_version column to library_assets table...")
            cursor.execute("ALTER TABLE library_assets ADD COLUMN selected_version TEXT")

        self.conn.commit()

    def _migrate_from_json(self):
        """One-time migration from state.json to SQLite."""
        try:
            with open(self.old_json_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                content = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', content)
                if not content.strip(): return
                data = json.loads(content)
            
            cursor = self.conn.cursor()
            cursor.execute("SELECT count(*) FROM library_assets")
            if cursor.fetchone()[0] > 0: return

            logger.info("Starting migration from state.json to SQLite...")

            # Migrate Settings
            settings = data.get('settings', {})
            for sid, sval in settings.items():
                cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                               (sval.get('key'), json.dumps(sval.get('value'))))

            # Migrate Folders
            folders = data.get('folders', {})
            for fid, fval in folders.items():
                cursor.execute("INSERT OR REPLACE INTO folders (path) VALUES (?)", (fval.get('path'),))

            # Migrate Library Assets
            lib = data.get('library_assets', {})
            for lid, lval in lib.items():
                cursor.execute(
                    "INSERT OR REPLACE INTO library_assets (id, name, path, data_type, asset_type, created_at, versions, metadata, tags, stems_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (lval.get('id'), lval.get('name'), lval.get('path'), lval.get('data_type'), lval.get('asset_type'),
                     lval.get('created_at'), json.dumps(lval.get('versions', {})), json.dumps(lval.get('metadata', {})), json.dumps(lval.get('tags', [])), lval.get('stems_id'))
                )

            self.conn.commit()
            os.rename(self.old_json_path, self.old_json_path + ".bak")
        except Exception as e:
            logger.error(f"Migration failed: {e}")

    @property
    def db(self): return self

    def table(self, name):
        if name == 'library_assets': return self.library_assets_table
        if name == 'audio_assets': return self.audio_assets_table
        if name == 'tasks': return self.tasks_table
        if name == 'settings': return self.settings_table
        if name == 'folders': return self.folders_table
        if name == 'yt_uploads': return self.yt_uploads_table
        return None

    def _extract_id(self, query):
        if not query: return None
        s = str(query)
        m = re.search(r"'id',?\), '([^']+)'", s)
        if m: return m.group(1)
        m = re.search(r"id' == '([^']+)'", s)
        if m: return m.group(1)
        return None

    @property
    def library_assets_table(self):
        class LibraryTable:
            def __init__(self, manager): self.m = manager
            def all(self):
                cursor = self.m.conn.cursor()
                cursor.execute("SELECT * FROM library_assets")
                res = []
                for row in cursor.fetchall():
                    d = dict(row)
                    d['versions'] = json.loads(d.get('versions') or '{}')
                    d['metadata'] = json.loads(d.get('metadata') or '{}')
                    d['tags'] = json.loads(d.get('tags') or '[]')
                    # duration is already a float (REAL)
                    res.append(d)
                return res
            def get(self, query=None, doc_id=None):
                target_id = str(doc_id) if doc_id else self.m._extract_id(query)
                if not target_id: return None
                cursor = self.m.conn.cursor()
                cursor.execute("SELECT * FROM library_assets WHERE id = ?", (target_id,))
                row = cursor.fetchone()
                if row:
                    d = dict(row)
                    d['versions'] = json.loads(d.get('versions') or '{}')
                    d['metadata'] = json.loads(d.get('metadata') or '{}')
                    d['tags'] = json.loads(d.get('tags') or '[]')
                    class Doc(dict):
                        @property
                        def doc_id(self): return self['id']
                    return Doc(d)
                return None
            def insert(self, data):
                cursor = self.m.conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO library_assets (id, name, path, data_type, asset_type, created_at, versions, metadata, tags, stems_id, duration, selected_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (data.get('id'), data.get('name'), data.get('path'), data.get('data_type'), data.get('asset_type'),
                     data.get('created_at'), json.dumps(data.get('versions', {})), json.dumps(data.get('metadata', {})), json.dumps(data.get('tags', [])), data.get('stems_id'), data.get('duration', 0), data.get('selected_version'))
                )
                self.m.conn.commit()
            def update(self, updates, query):
                target_id = self.m._extract_id(query)
                if not target_id: return
                clean_updates = {k: v for k, v in updates.items() if not k.startswith('_')}
                if 'versions' in clean_updates: clean_updates['versions'] = json.dumps(clean_updates['versions'])
                if 'metadata' in clean_updates: clean_updates['metadata'] = json.dumps(clean_updates['metadata'])
                if 'tags' in clean_updates: clean_updates['tags'] = json.dumps(clean_updates['tags'])
                sql = "UPDATE library_assets SET " + ", ".join([f"{k} = ?" for k in clean_updates.keys()]) + " WHERE id = ?"
                params = list(clean_updates.values()) + [target_id]
                cursor = self.m.conn.cursor()
                cursor.execute(sql, params)
                self.m.conn.commit()
            def remove(self, query=None, doc_ids=None):
                cursor = self.m.conn.cursor()
                if doc_ids:
                    for did in doc_ids: cursor.execute("DELETE FROM library_assets WHERE id = ?", (str(did),))
                elif query:
                    target_id = self.m._extract_id(query)
                    if target_id: cursor.execute("DELETE FROM library_assets WHERE id = ?", (target_id,))
                self.m.conn.commit()

            def truncate(self):
                cursor = self.m.conn.cursor()
                cursor.execute("DELETE FROM library_assets")
                self.m.conn.commit()

        return LibraryTable(self)

    @property
    def tasks_table(self):
        class TasksTable:
            def __init__(self, m): self.m = m
            def all(self): return self.m.get_tasks()
        return TasksTable(self)

    @property
    def settings_table(self):
        class SettingsTable:
            def __init__(self, m): self.m = m
            def get(self, query): return None # Simplified
        return SettingsTable(self)

    @property
    def folders_table(self):
        class FoldersTable:
            def __init__(self, m): self.m = m
            def all(self): return self.m.get_folders()
            def insert(self, data): self.m.add_folder(data['path'])
        return FoldersTable(self)

    @property
    def yt_uploads_table(self):
        class YTTable:
            def __init__(self, m): self.m = m
            def all(self): return self.m.get_yt_uploads()
            def insert(self, data): return self.m.add_yt_upload(data)
            def remove(self, query=None):
                target_id = self.m._extract_id(query)
                if target_id: self.m.delete_yt_upload(target_id)
        return YTTable(self)

    @property
    def audio_assets_table(self):
        class AudioTable:
            def __init__(self, manager): self.m = manager
            def search(self, query):
                s = str(query)
                m = re.search(r"'path',?\), '([^']+)'", s)
                if not m: return []
                cursor = self.m.conn.cursor()
                cursor.execute("SELECT * FROM audio_assets WHERE path = ?", (m.group(1),))
                return [dict(row) for row in cursor.fetchall()]
            def insert(self, data):
                cursor = self.m.conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO audio_assets (path, filename, duration, sample_rate, bit_depth, format, parent_folder) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (data.get('path'), data.get('filename'), data.get('duration'), data.get('sample_rate'), data.get('bit_depth'), data.get('format'), data.get('parent_folder'))
                )
                self.m.conn.commit()
        return AudioTable(self)

    def get_setting(self, key, default=None):
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        if row: return json.loads(row[0])
        return default

    def set_setting(self, key, value):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))
        self.conn.commit()

    def add_folder(self, path):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO folders (path) VALUES (?)", (path,))
        self.conn.commit()

    def get_folders(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT path FROM folders")
        return [row[0] for row in cursor.fetchall()]

    def add_task(self, task_type, target, status="Pending", project_tag=None, **details):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (type, target, status, project_tag, details, log) VALUES (?, ?, ?, ?, ?, ?)",
            (task_type, target, status, project_tag, json.dumps(details), "")
        )
        self.conn.commit()
        return cursor.lastrowid

    def claim_task(self, task_id):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE tasks SET status = 'Processing' WHERE id = ?", (task_id,))
        self.conn.commit()

    def update_task_status(self, task_id, status):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))
        self.conn.commit()

    def log_task_output(self, task_id, message):
        cursor = self.conn.cursor()
        # Get existing log
        cursor.execute("SELECT log FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        current_log = row[0] if row else ""
        new_log = current_log + "\n" + message
        cursor.execute("UPDATE tasks SET log = ? WHERE id = ?", (new_log.strip(), task_id))
        self.conn.commit()

    def get_tasks(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tasks")
        return [dict(row) for row in cursor.fetchall()]

    def get_yt_uploads(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM yt_uploads")
        res = []
        for row in cursor.fetchall():
            d = dict(row)
            d['tags'] = json.loads(d.get('tags') or '[]')
            res.append(d)
        return res

    def add_yt_upload(self, data):
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO yt_uploads (id, title, status, created_at, tags) VALUES (?, ?, ?, ?, ?)",
                       (data.get('id'), data.get('title'), data.get('status'), data.get('created_at'), json.dumps(data.get('tags', []))))
        self.conn.commit()
        return data.get('id')

    def delete_yt_upload(self, upload_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM yt_uploads WHERE id = ?", (upload_id,))
        self.conn.commit()

    def get_yt_defaults(self):
        defaults = {"title_template": "{name}", "desc_template": "{name}", "default_tags": ""}
        for k in defaults:
            v = self.get_setting(f"yt_default_{k}")
            if v: defaults[k] = v
        return defaults

    def set_yt_defaults(self, title, desc, tags):
        self.set_setting("yt_default_title_template", title)
        self.set_setting("yt_default_desc_template", desc)
        self.set_setting("yt_default_default_tags", tags)
