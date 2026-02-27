import subprocess
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VideoEngine:
    """
    Core engine for creating videos from audio and background media using FFmpeg.
    """
    def __init__(self, ffmpeg_path="ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def create_video(self, audio_path, background_path, output_path, title_overlay=None, font_path=None, font_size=72):
        """
        Generates a high-quality MP4 video.
        
        :param audio_path: Path to the input audio file.
        :param background_path: Path to the background image or video.
        :param output_path: Path where the output MP4 will be saved.
        :param title_overlay: Optional text to overlay on the video.
        :param font_path: Optional path to a .ttf font file for the overlay.
        :param font_size: Font size for the overlay text.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if not os.path.exists(background_path):
            raise FileNotFoundError(f"Background file not found: {background_path}")

        # Determine if background is image or video
        is_video = background_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))

        # Base command
        cmd = [self.ffmpeg_path, "-y"] # Overwrite output

        # Input Background
        if not is_video:
            # Loop image to match audio duration
            cmd.extend(["-loop", "1", "-i", background_path])
        else:
            # Stream video (assuming it needs to loop if shorter than audio, 
            # or we just use shortest)
            cmd.extend(["-stream_loop", "-1", "-i", background_path])

        # Input Audio
        cmd.extend(["-i", audio_path])

        # Filters
        filter_complex = []
        
        # Scale background to 1080p if needed
        filter_complex.append("scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080")

        if title_overlay:
            drawtext = f"drawtext=text='{title_overlay}':fontcolor=white:fontsize={font_size}:x=(w-text_w)/2:y=(h-text_h)/2"
            if font_path and os.path.exists(font_path):
                drawtext += f":fontfile='{font_path}'"
            # Add a subtle shadow for readability
            drawtext += ":shadowcolor=black@0.5:shadowx=2:shadowy=2"
            filter_complex.append(drawtext)

        filter_str = ",".join(filter_complex)
        
        cmd.extend(["-vf", filter_str])
        
        # Encoding settings (High Quality H.264)
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",         # High quality (lower is better, 18-23 is standard)
            "-pix_fmt", "yuv420p", # Compatible with most players/YouTube
            "-c:a", "aac",
            "-b:a", "320k",       # High quality audio
            "-shortest"           # End when audio ends
        ])

        cmd.append(output_path)

        logger.info(f"Running FFmpeg command: {' '.join(cmd)}")
        
        try:
            # Open log file for this specific render
            log_path = f"{output_path}.log"
            with open(log_path, "w") as log_file:
                process = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, text=True)
                
                logger.info(f"FFmpeg started (PID: {process.pid}). Logging to: {log_path}")
                process.wait()

            if process.returncode != 0:
                logger.error(f"FFmpeg failed with return code {process.returncode}")
                # Read the last few lines of the log for the exception message
                with open(log_path, "r") as log_file:
                    last_lines = log_file.readlines()[-10:]
                raise RuntimeError(f"FFmpeg error: {''.join(last_lines)}")
            
            logger.info(f"Successfully created video: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Error during video creation: {e}")
            raise

if __name__ == "__main__":
    # Simple test logic
    engine = VideoEngine()
    print("VideoEngine class loaded.")
