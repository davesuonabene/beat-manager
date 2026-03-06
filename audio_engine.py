import os
import glob
from tinydb import Query
from state_manager import StateManager
import mutagen

# Project paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_JSON = os.path.join(BASE_DIR, "state.json")

class AudioEngine:
    def __init__(self):
        self.state_manager = StateManager(STATE_JSON)
        self.audio_assets_table = self.state_manager.db.table('audio_assets')

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
    # Replace with an actual path for testing
    # engine.scan_folder("/home/davesuonabene/.openclaw/workspace/workspace/samples_2026-02-27/")
    # print("\nAll scanned audio assets:")
    # for asset in engine.audio_assets_table.all():
    #     print(asset)
