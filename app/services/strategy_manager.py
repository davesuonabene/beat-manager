import json
import os
from datetime import datetime, timedelta
import random

# Project paths
current_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(current_dir)
PROJECT_ROOT = os.path.dirname(app_dir)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
STRATEGY_FILE = os.path.join(DATA_DIR, "strategy.json")
PLAN_FILE = os.path.join(DATA_DIR, "plan.json")
QUEUE_FILE = os.path.join(DATA_DIR, "queue.json")

class StrategyManager:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
        self.strategy = self._load_json(STRATEGY_FILE, {
            "target_uploads_per_week": 3,
            "niche": "Generic Type Beat",
            "preferred_times": ["14:00", "19:00"],
            "notes": "This JSON is for Agent reference only."
        })
        self.plan = self._load_json(PLAN_FILE, {
            "checkpoints": [
                {"day": "Monday", "action": "UPLOAD"},
                {"day": "Wednesday", "action": "RESEARCH"},
                {"day": "Friday", "action": "UPLOAD"}
            ]
        })

    def _load_json(self, path, default):
        if os.path.exists(path):
            with open(path, 'r') as f:
                try: return json.load(f)
                except: return default
        return default

    def save_strategy(self, strategy_data):
        self.strategy = strategy_data
        with open(STRATEGY_FILE, 'w') as f:
            json.dump(self.strategy, f, indent=4)

    def save_plan(self, plan_data):
        self.plan = plan_data
        with open(PLAN_FILE, 'w') as f:
            json.dump(self.plan, f, indent=4)

    def check_assets(self):
        from app.core.audio_engine import AudioEngine
        ae = AudioEngine()
        audio_count = len(ae.audio_assets_table.all())
        image_dir = os.path.join(PROJECT_ROOT, "assets", "ronald")
        images = [f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg'))] if os.path.exists(image_dir) else []
        return {
            "audio": audio_count,
            "images": len(images),
            "status": "ready" if audio_count > 0 and len(images) > 0 else "scarcity"
        }

    def compile_queue_from_plan(self):
        new_queue = []
        now = datetime.now()
        days_map = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        current_day_idx = now.weekday()

        for checkpoint_idx, entry in enumerate(self.plan.get("checkpoints", [])):
            day_name = entry.get("day")
            if day_name not in days_map: continue
            
            target_day_idx = days_map.index(day_name)
            delta_days = (target_day_idx - current_day_idx) % 7
            event_date = now + timedelta(days=delta_days)
            
            checkpoint_action = entry.get("action")
            preferred_times = self.strategy.get("preferred_times", ["12:00", "20:00"])
            time_str = random.choice(preferred_times)
            h, m = map(int, time_str.split(':'))
            
            timestamp = event_date.replace(hour=h, minute=m, second=0, microsecond=0)
            
            # Implementation of Point 1: Smart Asset Mapping (Automated Linkage)
            # We use a project_tag to link RENDER and UPLOAD tasks
            project_tag = f"Project_{event_date.strftime('%Y%m%d')}_{checkpoint_idx}"

            if timestamp > now:
                if checkpoint_action == "UPLOAD":
                    render_time = timestamp - timedelta(hours=2)
                    new_queue.append({
                        "timestamp": render_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "action": "AUTO_RENDER",
                        "status": "pending",
                        "project_tag": project_tag,
                        "details": {
                            "niche": self.strategy.get("niche"),
                            "audio": "", 
                            "image": "",
                            "output": f"{project_tag}.mp4"
                        }
                    })
                    new_queue.append({
                        "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "action": "AUTO_UPLOAD",
                        "status": "pending",
                        "project_tag": project_tag,
                        "details": {
                            "niche": self.strategy.get("niche"),
                            "video": "", # Left empty for Smart Mapping to resolve
                            "title": f"{self.strategy.get('niche')} - {event_date.strftime('%d %b')}",
                            "description": "New beat upload. Enjoy.",
                            "publish_at": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
                        }
                    })
                elif checkpoint_action == "RESEARCH":
                    new_queue.append({
                        "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "action": "AUTO_RESEARCH",
                        "status": "pending",
                        "project_tag": project_tag,
                        "details": {
                            "niche": self.strategy.get("niche"),
                            "depth": "standard"
                        }
                    })

        new_queue.sort(key=lambda x: x['timestamp'])
        with open(QUEUE_FILE, 'w') as f:
            json.dump(new_queue, f, indent=4)
        return new_queue

    def save_queue(self, queue_data):
        with open(QUEUE_FILE, 'w') as f:
            json.dump(queue_data, f, indent=4)

    def update_queue_item(self, index, details):
        queue = self.get_queue()
        if 0 <= index < len(queue):
            queue[index]['details'] = details
            self.save_queue(queue)
            return True
        return False

    def validate_queue(self):
        """
        Implementation of Point 2: Machine-Readable Validation.
        Returns a list of structured dictionaries for agents.
        """
        queue = self.get_queue()
        validation_results = []
        
        mandatory = {
            "AUTO_RENDER": ["audio", "image"],
            "AUTO_UPLOAD": ["title", "description"], # Video is resolved via mapping
            "AUTO_RESEARCH": ["niche"]
        }

        for idx, item in enumerate(queue):
            if item['status'] == 'scheduled': continue
                
            action = item['action']
            details = item.get('details', {})
            errors = []
            
            if action in mandatory:
                for field in mandatory[action]:
                    val = details.get(field)
                    if not val or (isinstance(val, str) and val.strip() == ""):
                        # For AUTO_UPLOAD, if video is missing but project_tag exists, it's NOT a validation error
                        # because Point 1 handles the mapping.
                        if action == "AUTO_UPLOAD" and field == "video" and item.get("project_tag"):
                            continue
                        errors.append({"field": field, "reason": "missing_parameter"})
                    
                    if field in ["audio", "image", "video"] and val:
                        full_path = val if os.path.isabs(val) else os.path.join(PROJECT_ROOT, val)
                        if not os.path.exists(full_path):
                            errors.append({"field": field, "reason": "file_not_found", "path": val})

            if errors:
                validation_results.append({
                    "row": idx,
                    "action": action,
                    "project_tag": item.get("project_tag"),
                    "errors": errors
                })

        return validation_results

    def get_strategy(self): return self.strategy
    def get_plan(self): return self.plan
    def get_queue(self): return self._load_json(QUEUE_FILE, [])
