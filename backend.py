import os
import time
import logging
import traceback
from datetime import datetime
from state_manager import StateManager
from video_engine import VideoEngine
from youtube_engine import YouTubeEngine
from strategy_manager import StrategyManager

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS = os.path.join(PROJECT_ROOT, "client_secrets.json")

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_ROOT, "backend.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("BeatManagerBackend")

class Backend:
    def __init__(self):
        self.state = StateManager()
        self.strategy_manager = StrategyManager()
        self.video_engine = VideoEngine()
        self.youtube_engine = None

    def _init_youtube(self):
        if not os.path.exists(CLIENT_SECRETS):
            raise FileNotFoundError(f"Missing {CLIENT_SECRETS}. YouTube uploads will fail.")
        return YouTubeEngine(CLIENT_SECRETS, token_storage_dir=os.path.join(PROJECT_ROOT, "tokens"))

    def pre_flight_check(self, task_id):
        """
        Implementation of Point 5: Pre-Flight Simulation.
        Verifies if a task is ready for execution.
        """
        task = self.state.tasks_table.get(doc_id=task_id)
        if not task: return {"ready": False, "error": "Task not found"}
        
        task_type = task.get("type")
        details = task.get("details", {})
        
        checks = []
        
        if task_type in ["RENDER", "AUTO_RENDER"]:
            audio = details.get("audio")
            image = details.get("image")
            if audio and not os.path.exists(audio): checks.append(f"Audio file missing: {audio}")
            if image and not os.path.exists(image): checks.append(f"Image file missing: {image}")
            
        elif task_type in ["UPLOAD", "AUTO_UPLOAD"]:
            if not os.path.exists(CLIENT_SECRETS): checks.append("Missing client_secrets.json")
            video = details.get("video")
            # If video is missing but we have a project_tag, we check for potential mapping later
            if not video and not task.get("project_tag"):
                checks.append("Missing video path and no project_tag for mapping")
            elif video and not os.path.exists(video):
                checks.append(f"Video file missing: {video}")

        if checks:
            return {"ready": False, "errors": checks}
        return {"ready": True}

    def process_task(self, task_id):
        pre_flight = self.pre_flight_check(task_id)
        if not pre_flight["ready"]:
            error_msg = "; ".join(pre_flight.get("errors", ["Unknown error"]))
            self.state.log_task_output(task_id, f"PRE-FLIGHT FAILED: {error_msg}")
            self.state.update_task_status(task_id, "Error")
            return False

        task = self.state.tasks_table.get(doc_id=task_id)
        task_type = task.get("type")
        
        logger.info(f"Executing task #{task_id} ({task_type})")
        self.state.claim_task(task_id)
        
        try:
            if task_type in ["RENDER", "AUTO_RENDER"]:
                self.process_render(task)
                self.state.update_task_status(task_id, "Finished")
            elif task_type in ["UPLOAD", "AUTO_UPLOAD"]:
                self.process_upload(task)
                self.state.update_task_status(task_id, "Uploaded")
            elif task_type == "AUTO_RESEARCH":
                self.state.log_task_output(task_id, "Running automated research...")
                time.sleep(2)
                self.state.update_task_status(task_id, "Finished")
            else:
                raise ValueError(f"Unknown task type: {task_type}")
            
            logger.info(f"Task #{task_id} completed successfully.")
            return True
        except Exception as e:
            error_msg = f"Task #{task_id} failed: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            self.state.log_task_output(task_id, f"ERROR: {str(e)}")
            self.state.update_task_status(task_id, "Error")
            return False

    def process_render(self, task):
        task_id = task.doc_id
        details = task.get("details", {})
        audio = details.get("audio")
        image = details.get("image")
        output = task.get("target")
        
        if not audio or not image:
            # AUTO_RENDER asset selection (can be improved by agent later)
            image_dir = os.path.join(PROJECT_ROOT, "assets", "ronald")
            images = [f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg'))]
            audios = [f for f in os.listdir(image_dir) if f.lower().endswith(('.wav', '.mp3'))]
            if not images or not audios:
                raise ValueError("Missing assets for auto-render.")
            audio = os.path.join(image_dir, audios[0])
            image = os.path.join(image_dir, images[0])
            if not output.endswith(".mp4"):
                output = os.path.join(PROJECT_ROOT, "temp_videos", f"{output}.mp4")

        self.state.log_task_output(task_id, f"Rendering: {os.path.basename(audio)}")
        self.video_engine.create_video(audio, image, output)
        
        # Implementation of Point 1: Register output for mapping
        if task.get("project_tag"):
            self.state.log_task_output(task_id, f"Registering output for tag: {task['project_tag']}")
            # We can store this in state.json or just rely on convention.
            # For now, let's keep it simple: the output filename IS the project_tag.mp4

    def process_upload(self, task):
        task_id = task.doc_id
        details = task.get("details", {})
        video_path = details.get("video")
        
        # Implementation of Point 1: Smart Asset Mapping
        if not video_path and task.get("project_tag"):
            tag = task["project_tag"]
            # Look for rendered file in temp_videos
            potential_path = os.path.join(PROJECT_ROOT, "temp_videos", f"{tag}.mp4")
            if os.path.exists(potential_path):
                video_path = potential_path
                self.state.log_task_output(task_id, f"Resolved video via project_tag: {tag}")
            else:
                raise FileNotFoundError(f"Could not resolve video for tag: {tag}")

        title = details.get("title") or task.get("target")
        description = details.get("description", "Automated upload.")
        publish_at = details.get("publish_at")
        
        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if not self.youtube_engine:
            self.youtube_engine = self._init_youtube()
        
        self.state.log_task_output(task_id, f"Uploading: {title}")
        self.youtube_engine.upload_video(
            "default_channel", video_path, title, description, 
            privacy_status="private", publish_at=publish_at
        )

    def activate_from_queue(self, index):
        """Moves a task from queue.json to state.json."""
        queue = self.strategy_manager.get_queue()
        if index < 0 or index >= len(queue): return None
        item = queue[index]
        if item['status'] == 'scheduled': return None

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
        logger.info(f"Activated task #{task_id} from queue index {index}")
        return task_id

if __name__ == "__main__":
    print("Beat Manager Backend initialized.")
