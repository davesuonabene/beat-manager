import subprocess
import os
import logging
import shutil
from typing import Dict, Optional, Callable
from app.models.schemas import TaskResult

# Internal logger
logger = logging.getLogger(__name__)

class StemsEngine:
    """
    Core engine for audio source separation using Demucs (htdemucs).
    Handles separation, caching logic, and progress reporting.
    """
    def __init__(self, stems_dir: str):
        """
        :param stems_dir: Directory where separated stems will be stored.
        """
        self.stems_dir = stems_dir
        if not os.path.exists(self.stems_dir):
            os.makedirs(self.stems_dir)

    def separate_stems(self, audio_path: str, asset_id: str, progress_callback: Optional[Callable[[float], None]] = None) -> TaskResult:
        """
        Separates the audio file into stems using Demucs.
        
        :param audio_path: Path to the original audio file.
        :param asset_id: ID of the parent asset (used for folder naming).
        :param progress_callback: Optional function to report progress (0.0 to 100.0).
        :return: TaskResult indicating success and the path to the stems folder.
        """
        if not os.path.exists(audio_path):
            return TaskResult(success=False, error_message=f"Audio file not found: {audio_path}")

        # Stems folder named after the asset ID to avoid collisions
        output_folder = os.path.join(self.stems_dir, asset_id)
        # Demucs creates a subfolder named after the model, then after the filename
        # We want to flatten this or at least know where it is.
        
        temp_dir = os.path.join(self.stems_dir, f"temp_{asset_id}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            # Locate demucs executable in the current environment
            import sys
            venv_bin = os.path.dirname(sys.executable)
            demucs_path = os.path.join(venv_bin, "demucs")
            if not os.path.exists(demucs_path):
                # Fallback to system path if not in venv
                demucs_path = "demucs"

            # Run Demucs
            # -n htdemucs: use the high-quality model
            # -o: output directory
            cmd = [demucs_path, "-n", "htdemucs", audio_path, "-o", temp_dir]
            
            logger.info(f"Running Demucs for asset {asset_id}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Progress parsing (logic from Gaia)
            buffer = ""
            full_stderr = []
            while True:
                char = process.stdout.read(1)
                if not char and process.poll() is not None:
                    break
                
                if char in ('\r', '\n'):
                    if progress_callback and "%|" in buffer:
                        try:
                            parts = buffer.split("%|")
                            if len(parts) > 1:
                                perc_str = parts[0].split()[-1].replace('%', '').strip()
                                progress_callback(float(perc_str))
                        except Exception:
                            pass
                    if buffer.strip():
                        full_stderr.append(buffer.strip())
                    buffer = ""
                else:
                    buffer += char

            if process.returncode != 0:
                error_context = "\n".join(full_stderr[-10:]) # last 10 lines of output
                logger.error(f"Demucs failed (code {process.returncode}): {error_context}")
                return TaskResult(success=False, error_message=f"Demucs failed (code {process.returncode}). Output: {error_context}")

            # Move results from temp_dir/htdemucs/filename/ to output_folder
            input_filename = os.path.splitext(os.path.basename(audio_path))[0]
            demucs_output = os.path.join(temp_dir, "htdemucs", input_filename)
            
            if not os.path.exists(demucs_output):
                return TaskResult(success=False, error_message="Demucs output folder not found after processing")

            if os.path.exists(output_folder):
                shutil.rmtree(output_folder)
            
            shutil.move(demucs_output, output_folder)
            shutil.rmtree(temp_dir)
            
            logger.info(f"Successfully separated stems for {asset_id} to {output_folder}")
            return TaskResult(success=True, output_path=output_folder)

        except Exception as e:
            logger.error(f"Unexpected error during stem separation: {str(e)}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return TaskResult(success=False, error_message=str(e))

if __name__ == "__main__":
    print("StemsEngine loaded.")
