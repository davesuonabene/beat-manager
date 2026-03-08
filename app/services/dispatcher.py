import logging
import os
from app.models.schemas import RenderConfig, UploadConfig, TaskResult, PrivacyEnum
from app.core.video_engine import VideoEngine
from app.core.youtube_engine import YouTubeEngine
from app.core.state_manager import StateManager
from app.services.strategy_manager import StrategyManager

# Internal logger
logger = logging.getLogger(__name__)

class TaskDispatcher:
    """
    The Service Layer: Bridges the Interface (TUI/CLI) and the Core logic.
    Manages state persistence via StateManager and coordinates core engines.
    """
    def __init__(self, project_root: str):
        self.project_root = project_root
        self.state = StateManager()
        self.strategy_manager = StrategyManager()
        
        # Initialize Core Engines
        self.video_engine = VideoEngine()
        
        # YouTube Engine initialization
        client_secrets = os.path.join(self.project_root, "client_secrets.json")
        tokens_dir = os.path.join(self.project_root, "tokens")
        self.youtube_engine = YouTubeEngine(client_secrets, token_storage_dir=tokens_dir)

    def run_render(self, config: RenderConfig) -> TaskResult:
        """
        Coordinates a render task: logs to state, executes engine, updates state.
        """
        # Register task in state.json
        task_id = self.state.add_task(
            "RENDER", 
            os.path.basename(config.output_path), 
            "Pending",
            project_tag=config.project_tag,
            audio=config.audio_path,
            image=config.image_path
        )
        
        return self._execute_render(task_id, config)

    def _execute_render(self, task_id: int, config: RenderConfig) -> TaskResult:
        self.state.claim_task(task_id)
        self.state.log_task_output(task_id, f"Starting render for tag: {config.project_tag}")
        
        try:
            result = self.video_engine.create_video(config)
            if result.success:
                self.state.log_task_output(task_id, f"Render successful: {result.output_path}")
                self.state.update_task_status(task_id, "Finished")
            else:
                self.state.log_task_output(task_id, f"Render failed: {result.error_message}")
                self.state.update_task_status(task_id, "Error")
            return result
        except Exception as e:
            error_msg = f"Unexpected error during render: {str(e)}"
            self.state.log_task_output(task_id, error_msg)
            self.state.update_task_status(task_id, "Error")
            return TaskResult(success=False, error_message=error_msg)

    def run_upload(self, config: UploadConfig, channel_id: str = "default_channel") -> TaskResult:
        """
        Coordinates an upload task: logs to state, executes engine, updates state.
        """
        task_id = self.state.add_task(
            "UPLOAD", 
            config.title, 
            "Pending",
            video=config.video_path,
            publish_at=config.publish_at
        )
        
        return self._execute_upload(task_id, config, channel_id)

    def _execute_upload(self, task_id: int, config: UploadConfig, channel_id: str) -> TaskResult:
        self.state.claim_task(task_id)
        self.state.log_task_output(task_id, f"Starting upload: {config.title}")
        
        try:
            result = self.youtube_engine.upload_video(channel_id, config)
            if result.success:
                self.state.log_task_output(task_id, f"Upload successful! Video ID: {result.output_path}")
                self.state.update_task_status(task_id, "Uploaded")
            else:
                self.state.log_task_output(task_id, f"Upload failed: {result.error_message}")
                self.state.update_task_status(task_id, "Error")
            return result
        except Exception as e:
            error_msg = f"Unexpected error during upload: {str(e)}"
            self.state.log_task_output(task_id, error_msg)
            self.state.update_task_status(task_id, "Error")
            return TaskResult(success=False, error_message=error_msg)

    def process_task(self, task_id: int) -> TaskResult:
        """Executes a pending task by its ID."""
        task = self.state.tasks_table.get(doc_id=task_id)
        if not task:
            return TaskResult(success=False, error_message="Task not found")
        
        task_type = task.get("type")
        details = task.get("details", {})
        
        if task_type in ["RENDER", "AUTO_RENDER"]:
            config = RenderConfig(
                audio_path=details.get("audio"),
                image_path=details.get("image"),
                output_path=task.get("target"),
                project_tag=task.get("project_tag", "untagged")
            )
            return self._execute_render(task_id, config)
        
        elif task_type in ["UPLOAD", "AUTO_UPLOAD"]:
            config = UploadConfig(
                video_path=details.get("video"),
                title=task.get("target"),
                description=details.get("description", "Automated upload."),
                privacy=PrivacyEnum(details.get("privacy", "private")),
                publish_at=details.get("publish_at")
            )
            return self._execute_upload(task_id, config, "default_channel")
        
        elif task_type in ["AUTO_RESEARCH", "AUTO_STRATEGY"]:
            self.state.claim_task(task_id)
            self.state.log_task_output(task_id, f"Running automated action: {task_type}")
            # Mock or logic for these types (currently placeholder in legacy)
            import time
            time.sleep(1)
            self.state.update_task_status(task_id, "Finished")
            return TaskResult(success=True)
        
        # Mark unknown tasks as Error to prevent worker from retrying indefinitely
        error_msg = f"Unsupported task type: {task_type}"
        self.state.update_task_status(task_id, "Error")
        self.state.log_task_output(task_id, error_msg)
        return TaskResult(success=False, error_message=error_msg)

    def activate_from_queue(self, index: int) -> int:
        """Moves a task from the weekly queue to the active state."""
        queue = self.strategy_manager.get_queue()
        if index < 0 or index >= len(queue):
            return None
        
        item = queue[index]
        if item['status'] == 'scheduled':
            return None

        details = item.get('details', {}).copy()
        if item['action'] == "AUTO_UPLOAD" and "publish_at" not in details:
            ts = item['timestamp'].replace(" ", "T") + "Z"
            details['publish_at'] = ts

        task_id = self.state.add_task(
            item['action'], 
            details.get('title') or f"Auto_{item['action']}_{index}", 
            "Pending",
            project_tag=item.get("project_tag"),
            **details
        )
        
        item['status'] = 'scheduled'
        self.strategy_manager.save_queue(queue)
        return task_id

if __name__ == "__main__":
    print("TaskDispatcher service loaded.")
