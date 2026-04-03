import os
from tinydb import TinyDB, Query

class StateManager:
    def __init__(self, db_path=None):
        if db_path is None:
            # Default to state.json in the project root
            # Assuming this file is in app/core/state_manager.py
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(os.path.dirname(current_dir))
            db_path = os.path.join(project_root, "state.json")
        
        self.db = TinyDB(db_path)
        self.tasks_table = self.db.table('tasks')
        self.settings_table = self.db.table('settings')
        self.folders_table = self.db.table('folders')
        self.yt_uploads_table = self.db.table('yt_uploads')

    def add_folder(self, path):
        if not self.folders_table.search(Query().path == path):
            self.folders_table.insert({"path": path})

    def get_folders(self):
        return self.folders_table.all()

    def remove_folder(self, path):
        self.folders_table.remove(Query().path == path)

    def add_yt_upload(self, upload_data: dict):
        return self.yt_uploads_table.insert(upload_data)

    def get_yt_uploads(self):
        return self.yt_uploads_table.all()

    def get_yt_upload(self, upload_id: str):
        return self.yt_uploads_table.get(Query().id == upload_id)

    def update_yt_upload(self, upload_id: str, updates: dict):
        self.yt_uploads_table.update(updates, Query().id == upload_id)

    def delete_yt_upload(self, upload_id: str):
        self.yt_uploads_table.remove(Query().id == upload_id)

    def add_task(self, task_type, target, status="Pending", **kwargs):
        task = {
            "type": task_type,
            "target": target,
            "status": status,
            "details": kwargs,
            "log": ""
        }
        return self.tasks_table.insert(task)

    def get_tasks(self):
        return self.tasks_table.all()

    def get_pending_tasks(self):
        return self.tasks_table.search(Query().status == "Pending")

    def claim_task(self, task_id):
        """Atomically mark a task as processing."""
        self.tasks_table.update({"status": "Processing"}, doc_ids=[task_id])

    def update_task_status(self, task_id, status):
        self.tasks_table.update({"status": status}, doc_ids=[task_id])

    def log_task_output(self, task_id, message):
        """Append a log message to the task."""
        task = self.tasks_table.get(doc_id=task_id)
        current_log = task.get("log", "")
        new_log = current_log + "\n" + message
        self.tasks_table.update({"log": new_log}, doc_ids=[task_id])

    def clear_finished_tasks(self):
        Task = Query()
        self.tasks_table.remove(Task.status.one_of(["Finished", "Uploaded", "Error"]))

    def set_setting(self, key, value):
        self.settings_table.upsert({"key": key, "value": value}, Query().key == key)

    def get_setting(self, key, default=None):
        result = self.settings_table.get(Query().key == key)
        return result["value"] if result else default
