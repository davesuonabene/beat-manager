import os
import time
import logging
import traceback
from state_manager import StateManager
from video_engine import VideoEngine
from youtube_engine import YouTubeEngine

# Configuration
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRETS = os.path.join(PROJECT_ROOT, "client_secrets.json")
POLL_INTERVAL = 5  # seconds

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(PROJECT_ROOT, "worker.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("BeatManagerWorker")

class Worker:
    def __init__(self):
        self.state = StateManager()
        self.video_engine = VideoEngine()
        
        # YouTube engine is initialized per task or lazily
        self.youtube_engine = None

    def _init_youtube(self):
        if not os.path.exists(CLIENT_SECRETS):
            raise FileNotFoundError(f"Missing {CLIENT_SECRETS}. YouTube uploads will fail.")
        return YouTubeEngine(CLIENT_SECRETS, token_storage_dir=os.path.join(PROJECT_ROOT, "tokens"))

    def process_render(self, task):
        task_id = task.doc_id
        details = task.get("details", {})
        audio = details.get("audio")
        image = details.get("image")
        output = task.get("target")

        if not audio or not image:
            raise ValueError("Missing audio or image path for RENDER task.")

        self.state.log_task_output(task_id, f"Starting render: {audio} + {image} -> {output}")
        self.video_engine.create_video(audio, image, output)
        self.state.log_task_output(task_id, "Render completed successfully.")

    def process_upload(self, task):
        task_id = task.doc_id
        details = task.get("details", {})
        video_path = details.get("video")
        title = task.get("target")
        description = details.get("description", "")
        category = details.get("category", "10")
        privacy = details.get("privacy", "private")
        channel = details.get("channel", "default_channel")

        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found for upload: {video_path}")

        self.state.log_task_output(task_id, f"Initializing YouTube upload for: {title}")
        
        if not self.youtube_engine:
            self.youtube_engine = self._init_youtube()
        
        video_id = self.youtube_engine.upload_video(
            channel, video_path, title, description, 
            category_id=category, privacy_status=privacy
        )
        self.state.log_task_output(task_id, f"Upload successful! YouTube Video ID: {video_id}")

    def run(self):
        logger.info("BeatManager Worker started. Polling for tasks...")
        while True:
            try:
                pending_tasks = self.state.get_pending_tasks()
                for task in pending_tasks:
                    task_id = task.doc_id
                    task_type = task.get("type")
                    
                    logger.info(f"Claiming task {task_id} ({task_type})")
                    self.state.claim_task(task_id)
                    
                    try:
                        if task_type == "RENDER":
                            self.process_render(task)
                            self.state.update_task_status(task_id, "Finished")
                        elif task_type == "UPLOAD":
                            self.process_upload(task)
                            self.state.update_task_status(task_id, "Uploaded")
                        else:
                            logger.warning(f"Unknown task type: {task_type}")
                            self.state.update_task_status(task_id, "Error: Unknown Type")
                        
                        logger.info(f"Task {task_id} completed successfully.")
                    
                    except Exception as e:
                        error_msg = f"Task {task_id} failed: {str(e)}\n{traceback.format_exc()}"
                        logger.error(error_msg)
                        self.state.log_task_output(task_id, f"ERROR: {str(e)}")
                        self.state.update_task_status(task_id, "Error")

            except Exception as e:
                logger.error(f"Worker loop error: {e}")
            
            time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    worker = Worker()
    worker.run()
