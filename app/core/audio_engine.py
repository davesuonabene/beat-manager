import os
import subprocess
import threading
from tinydb import Query
from app.core.state_manager import StateManager
import mutagen

# Project paths
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
STATE_JSON = os.path.join(project_root, "state.json")

class AudioPlayer:
    """Simple audio audio_player using ffplay in a separate thread."""
    def __init__(self):
        self._process = None
        self._lock = threading.Lock()
        self.current_file = None
        self.play_start_time = 0
        self.start_offset = 0
        self.duration = 0
        self.is_playing = False

    def play(self, file_path: str, start_offset: float = 0):
        self.stop()
        with self._lock:
            # Get duration using mutagen if not provided
            try:
                audio = mutagen.File(file_path)
                self.duration = audio.info.length if hasattr(audio.info, 'length') else 0
            except:
                self.duration = 0

            self.current_file = file_path
            self.start_offset = start_offset
            self.play_start_time = time.time()
            self.is_playing = True
            
            # -nodisp: no video window, -autoexit: exit when finished, -loglevel quiet: no output
            # -ss: start offset
            cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-ss", str(start_offset), file_path]
            self._process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def get_current_position(self) -> float:
        if not self.is_playing:
            return 0
        pos = (time.time() - self.play_start_time) + self.start_offset
        if pos >= self.duration and self.duration > 0:
            self.is_playing = False
            return self.duration
        return pos

    def stop(self):
        with self._lock:
            self.is_playing = False
            if self._process:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=0.2)
                except:
                    try: self._process.kill()
                    except: pass
                self._process = None

import time

class AudioEngine:
    def __init__(self):
        self.state_manager = StateManager(STATE_JSON)
        self.audio_assets_table = self.state_manager.db.table('audio_assets')
        self.player = AudioPlayer()

    @property
    def current_playing_path(self) -> str | None:
        if self.player.is_playing:
            return self.player.current_file
        return None

    def play_preview(self, path: str, start_offset: float = 0):
        self.player.play(path, start_offset=start_offset)

    def stop_preview(self):
        self.player.stop()

    def scan_folder(self, path: str):
        if not os.path.exists(path):
            print(f"Error: Folder not found at {path}")
            return

        audio_files = []
        for root, _, files in os.walk(path):
            for file in files:
                if file.lower().endswith(('.wav', '.mp3', '.flac', '.aiff')):
                    audio_files.append(os.path.join(root, file))
        
        print(f"Found {len(audio_files)} audio files in {path}")

        for audio_file_path in audio_files:
            try:
                # Check if asset already exists in DB to avoid re-processing
                if self.audio_assets_table.search(Query().path == audio_file_path):
                    print(f"Skipping existing asset: {os.path.basename(audio_file_path)}")
                    continue

                audio = mutagen.File(audio_file_path)
                if audio:
                    duration = audio.info.length if hasattr(audio.info, 'length') else None
                    sample_rate = audio.info.samplerate if hasattr(audio.info, 'samplerate') else None
                    bit_depth = audio.info.bits_per_sample if hasattr(audio.info, 'bits_per_sample') else None
                    
                    asset_data = {
                        "filename": os.path.basename(audio_file_path),
                        "path": audio_file_path,
                        "duration": duration,
                        "sample_rate": sample_rate,
                        "bit_depth": bit_depth,
                        "format": audio.info.mime_type.split('/')[-1] if hasattr(audio.info, 'mime_type') else None,
                        "parent_folder": os.path.dirname(audio_file_path)
                    }
                    self.audio_assets_table.insert(asset_data)
                    print(f"Processed and stored: {os.path.basename(audio_file_path)}")
                else:
                    print(f"Could not read metadata for: {os.path.basename(audio_file_path)}")
            except Exception as e:
                print(f"Error processing {os.path.basename(audio_file_path)}: {e}")

if __name__ == "__main__":
    # Example usage (for testing)
    engine = AudioEngine()
