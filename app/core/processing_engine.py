import subprocess
import os
import logging

logger = logging.getLogger(__name__)

class ProcessingEngine:
    """Handles audio processing tasks using external tools (ffmpeg, demucs)."""
    
    @staticmethod
    def convert_wav_to_mp3(source_path: str, target_path: str) -> bool:
        """Converts a WAV file to a 320kbps MP3 using ffmpeg."""
        if not os.path.exists(source_path):
            logger.error(f"Source file not found: {source_path}")
            return False
            
        try:
            cmd = [
                "ffmpeg",
                "-y", # Overwrite output
                "-i", source_path,
                "-b:a", "320k",
                target_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg conversion failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Error converting to MP3: {e}")
            return False
