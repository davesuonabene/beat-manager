import os
import sqlite3
import json
import logging
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
            self.db_path = db_path
            self.old_json_path = db_path.replace(".db", ".json")

        self.conn = sqlite3.connect(self.db_path)
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
        # Collections Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS collections (
                id TEXT PRIMARY KEY,
                name TEXT,
                type TEXT,
                created_at TEXT
            )
        """)
        # Samples Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS samples (
                id TEXT PRIMARY KEY,
                path TEXT,
                filename TEXT,
                data_type TEXT,
                asset_type TEXT,
                bpm REAL,
                key TEXT,
                sample_type TEXT,
                duration REAL,
                collection_id TEXT,
                metadata TEXT
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
                collection_id TEXT
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
        self.conn.commit()

    def _migrate_from_json(self):
        """One-time migration from state.json to SQLite."""
        try:
            with open(self.old_json_path, 'r') as f:
                data = json.load(f)
            
            cursor = self.conn.cursor()
            
            # Check if already migrated
            cursor.execute("SELECT count(*) FROM tasks")
            if cursor.fetchone()[0] > 0:
                return

            logger.info("Starting migration from state.json to SQLite...")

            # Migrate Tasks
            tasks = data.get('tasks', {})
            for tid, tval in tasks.items():
                cursor.execute(
                    "INSERT INTO tasks (type, target, status, project_tag, details, log) VALUES (?, ?, ?, ?, ?, ?)",
                    (tval.get('type'), tval.get('target'), tval.get('status'), tval.get('project_tag'), 
                     json.dumps(tval.get('details', {})), tval.get('log', ""))
                )

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
                    "INSERT OR REPLACE INTO library_assets (id, name, path, data_type, asset_type, created_at, versions, metadata, collection_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (lval.get('id'), lval.get('name'), lval.get('path'), lval.get('data_type'), lval.get('asset_type'),
                     lval.get('created_at'), json.dumps(lval.get('versions', {})), json.dumps(lval.get('metadata', {})), lval.get('collection_id'))
                )

            # Migrate Audio Assets
            audio = data.get('audio_assets', {})
            for aid, aval in audio.items():
                cursor.execute(
                    "INSERT OR REPLACE INTO audio_assets (path, filename, duration, sample_rate, bit_depth, format, parent_folder) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (aval.get('path'), aval.get('filename'), aval.get('duration'), aval.get('sample_rate'), aval.get('bit_depth'), aval.get('format'), aval.get('parent_folder'))
                )

            self.conn.commit()
            logger.info("Migration complete. Renaming state.json to state.json.bak")
            os.rename(self.old_json_path, self.old_json_path + ".bak")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")

    # --- Task Methods ---
    def add_task(self, task_type, target, status="Pending", **kwargs):
        project_tag = kwargs.pop('project_tag', None)
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (type, target, status, project_tag, details, log) VALUES (?, ?, ?, ?, ?, ?)",
            (task_type, target, status, project_tag, json.dumps(kwargs), "")
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_tasks(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tasks")
        return [self._row_to_task(row) for row in cursor.fetchall()]

    def get_pending_tasks(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE status = 'Pending'")
        return [self._row_to_task(row) for row in cursor.fetchall()]

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
        cursor.execute("SELECT log FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        current_log = row['log'] if row else ""
        new_log = current_log + "\n" + message
        cursor.execute("UPDATE tasks SET log = ? WHERE id = ?", (new_log, task_id))
        self.conn.commit()

    def _row_to_task(self, row):
        # TinyDB compatible object
        class Task(dict):
            @property
            def doc_id(self):
                return self['id']
        
        d = dict(row)
        d['details'] = json.loads(d['details'])
        return Task(d)

    # --- Collection Methods ---
    def add_collection(self, collection_data: dict):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO collections (id, name, type, created_at) VALUES (?, ?, ?, ?)",
            (collection_data.get('id'), collection_data.get('name'), collection_data.get('type'), collection_data.get('created_at'))
        )
        self.conn.commit()
        return collection_data.get('id')

    def get_collections(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM collections")
        return [dict(row) for row in cursor.fetchall()]

    def delete_collection(self, collection_id: str):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        self.conn.commit()

    # --- Setting Methods ---
    def set_setting(self, key, value):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))
        self.conn.commit()

    def get_setting(self, key, default=None):
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return json.loads(row['value']) if row else default

    # --- YouTube Uploads ---
    def add_yt_upload(self, upload_data: dict):
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO yt_uploads (id, video_file_path, thumbnail_file_path, title, description, tags, 
               category_id, privacy_status, publish_at, status, created_at, youtube_id) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (upload_data.get('id'), upload_data.get('video_file_path'), upload_data.get('thumbnail_file_path'),
             upload_data.get('title'), upload_data.get('description'), json.dumps(upload_data.get('tags', [])),
             upload_data.get('category_id'), upload_data.get('privacy_status'), upload_data.get('publish_at'),
             upload_data.get('status'), upload_data.get('created_at'), upload_data.get('youtube_id'))
        )
        self.conn.commit()
        return upload_data.get('id')

    def get_yt_uploads(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM yt_uploads")
        res = []
        for row in cursor.fetchall():
            d = dict(row)
            d['tags'] = json.loads(d['tags'])
            res.append(d)
        return res

    # --- Folder Methods ---
    def add_folder(self, path):
        cursor = self.conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO folders (path) VALUES (?)", (path,))
        self.conn.commit()

    def get_folders(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM folders")
        return [dict(row) for row in cursor.fetchall()]

    def remove_folder(self, path):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM folders WHERE path = ?", (path,))
        self.conn.commit()

    @property
    def db(self):
        return self

    def table(self, name):
        if name == 'tasks': return self.tasks_table
        if name == 'settings': return self.settings_table
        if name == 'folders': return self.folders_table
        if name == 'yt_uploads': return self.yt_uploads_table
        if name == 'collections': return self.collections_table
        if name == 'samples': return self.samples_table
        if name == 'library_assets': return self.library_assets_table
        if name == 'audio_assets': return self.audio_assets_table
        return None

    @property
    def tasks_table(self):
        class TasksTable:
            def __init__(self, m): self.m = m
            def all(self): return self.m.get_tasks()
            def insert(self, data): return self.m.add_task(data.get('type'), data.get('target'), **data.get('details', {}))
            def update(self, updates, query=None, doc_ids=None):
                if doc_ids:
                    for tid in doc_ids: self.m.update_task_status(tid, updates.get('status'))
            def remove(self, query=None): self.m.clear_finished_tasks()
            def get(self, query=None, doc_id=None):
                cursor = self.m.conn.cursor()
                cursor.execute("SELECT * FROM tasks WHERE id = ?", (doc_id,))
                row = cursor.fetchone()
                return self.m._row_to_task(row) if row else None
        return TasksTable(self)

    @property
    def collections_table(self):
        class CollectionsTable:
            def __init__(self, m): self.m = m
            def all(self): return self.m.get_collections()
            def insert(self, data): return self.m.add_collection(data)
            def remove(self, query): pass # Implement if needed
            def get(self, query):
                # Basic ID lookup shim
                from tinydb import Query
                cursor = self.m.conn.cursor()
                cursor.execute("SELECT * FROM collections") # Simplified for now
                for row in cursor.fetchall():
                    return dict(row) # Return first for now or implement proper search
                return None
        return CollectionsTable(self)

    @property
    def settings_table(self):
        class SettingsTable:
            def __init__(self, m): self.m = m
            def upsert(self, data, query): self.m.set_setting(data['key'], data['value'])
            def get(self, query):
                # Extract key from query if possible, or just return something
                return None
        return SettingsTable(self)
    
    @property
    def folders_table(self):
        class FoldersTable:
            def __init__(self, m): self.m = m
            def all(self): return self.m.get_folders()
            def insert(self, data): self.m.add_folder(data['path'])
            def search(self, query): return [] # Simplified
            def remove(self, query): pass
        return FoldersTable(self)

    @property
    def yt_uploads_table(self):
        class YTTable:
            def __init__(self, m): self.m = m
            def all(self): return self.m.get_yt_uploads()
            def insert(self, data): return self.m.add_yt_upload(data)
            def get(self, query): return None
            def update(self, updates, query): pass
            def remove(self, query): pass
        return YTTable(self)

    @property
    def samples_table(self):
        class SamplesTable:
            def __init__(self, m): self.m = m
            def all(self): return [] # Implement if needed
            def insert(self, data): pass
        return SamplesTable(self)

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
                    try:
                        d['versions'] = json.loads(d['versions'] or '{}')
                        d['metadata'] = json.loads(d['metadata'] or '{}')
                    except Exception as e:
                        logger.error(f"Error decoding JSON for asset {d.get('id')}: {e}")
                        d['versions'] = {}
                        d['metadata'] = {}
                    res.append(d)
                # logger.info(f"library_assets_table.all() returning {len(res)} assets")
                return res
            def get(self, query=None, doc_id=None):
                cursor = self.m.conn.cursor()
                if doc_id:
                    # In our SQLite, id is a string but doc_id might be int index in TUI
                    # TinyDB used int doc_id. We map id to id.
                    cursor.execute("SELECT * FROM library_assets WHERE id = ?", (str(doc_id),))
                else:
                    # Very basic shim for Query().id == val
                    from tinydb import Query
                    # Extract the ID from the query object if possible
                    # Since we can't easily parse Query objects, we rely on callers 
                    # using the direct methods or we implement a few common ones.
                    return None
                
                row = cursor.fetchone()
                if row:
                    d = dict(row)
                    d['versions'] = json.loads(d['versions'])
                    d['metadata'] = json.loads(d['metadata'])
                    # Shim for doc_id property
                    class Doc(dict):
                        @property
                        def doc_id(self): return self['id']
                    return Doc(d)
                return None
            def insert(self, data):
                cursor = self.m.conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO library_assets (id, name, path, data_type, asset_type, created_at, versions, metadata, collection_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (data.get('id'), data.get('name'), data.get('path'), data.get('data_type'), data.get('asset_type'),
                     data.get('created_at'), json.dumps(data.get('versions', {})), json.dumps(data.get('metadata', {})), data.get('collection_id'))
                )
                self.m.conn.commit()
            def update(self, updates, query):
                # Another limited shim
                pass
            def remove(self, query=None, doc_ids=None):
                pass
        return LibraryTable(self)

    @property
    def audio_assets_table(self):
        class AudioTable:
            def __init__(self, manager): self.m = manager
            def search(self, query):
                # Simple path matching for AudioEngine.scan_folder
                from tinydb import Query
                cursor = self.m.conn.cursor()
                # Extremely limited shim for Query().path == path
                # This is only used in scan_folder
                return [] # Force re-scan for now or implement properly
            def all(self):
                cursor = self.m.conn.cursor()
                cursor.execute("SELECT * FROM audio_assets")
                return [dict(row) for row in cursor.fetchall()]
            def insert(self, data):
                cursor = self.m.conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO audio_assets (path, filename, duration, sample_rate, bit_depth, format, parent_folder) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (data.get('path'), data.get('filename'), data.get('duration'), data.get('sample_rate'), data.get('bit_depth'), data.get('format'), data.get('parent_folder'))
                )
                self.m.conn.commit()
        return AudioTable(self)

    # Helper for yt_defaults
    def get_yt_upload(self, upload_id: str):
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM yt_uploads WHERE id = ?", (upload_id,))
        row = cursor.fetchone()
        if row:
            d = dict(row)
            d['tags'] = json.loads(d['tags'])
            return d
        return None

    def update_yt_upload(self, upload_id: str, updates: dict):
        if 'tags' in updates:
            updates['tags'] = json.dumps(updates['tags'])
        
        query = "UPDATE yt_uploads SET " + ", ".join([f"{k} = ?" for k in updates.keys()]) + " WHERE id = ?"
        params = list(updates.values()) + [upload_id]
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        self.conn.commit()

    def delete_yt_upload(self, upload_id: str):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM yt_uploads WHERE id = ?", (upload_id,))
        self.conn.commit()

    def clear_finished_tasks(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE status IN ('Finished', 'Uploaded', 'Error')")
        self.conn.commit()

    def get_yt_defaults(self):
        defaults = {
            "title_template": "{name} | {genre} Type Beat",
            "desc_template": "Buy/Lease: [link]\nBPM: {bpm} | Key: {key}\nMood: {mood}",
            "default_tags": ""
        }
        for key in defaults.keys():
            saved = self.get_setting(f"yt_default_{key}")
            if saved is not None:
                defaults[key] = saved
        return defaults

    def set_yt_defaults(self, title: str, desc: str, tags: str):
        self.set_setting("yt_default_title_template", title)
        self.set_setting("yt_default_desc_template", desc)
        self.set_setting("yt_default_default_tags", tags)
