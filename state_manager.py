import os
from tinydb import TinyDB, Query

class StateManager:
    def __init__(self, db_path="state.json"):
        # Use an absolute path relative to the project root if needed
        # but for now, we'll assume it's in the same directory.
        self.db = TinyDB(db_path)
        self.tasks_table = self.db.table('tasks')
        self.settings_table = self.db.table('settings')
        self.folders_table = self.db.table('folders')

    def add_folder(self, path):
        if not self.folders_table.search(Query().path == path):
            self.folders_table.insert({"path": path})

    def get_folders(self):
        return self.folders_table.all()

    def remove_folder(self, path):
        self.folders_table.remove(Query().path == path)

    def add_task(self, task_type, target, status="Pending", **kwargs):
        task = {
            "type": task_type,
            "target": target,
            "status": status,
            "details": kwargs
        }
        return self.tasks_table.insert(task)

    def get_tasks(self):
        return self.tasks_table.all()

    def update_task_status(self, task_id, status):
        self.tasks_table.update({"status": status}, doc_ids=[task_id])

    def clear_finished_tasks(self):
        Task = Query()
        self.tasks_table.remove(Task.status.one_of(["Finished", "Uploaded", "Error"]))

    def set_setting(self, key, value):
        self.settings_table.upsert({"key": key, "value": value}, Query().key == key)

    def get_setting(self, key, default=None):
        result = self.settings_table.get(Query().key == key)
        return result["value"] if result else default
