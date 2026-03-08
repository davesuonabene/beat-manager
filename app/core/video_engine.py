import subprocess
import os
import logging
from app.models.schemas import RenderConfig, TaskResult

# Internal logger for this module
logger = logging.getLogger(__name__)

class VideoEngine:
    """
    Core engine for creating videos from audio and background media using FFmpeg.
    This class is pure logic and maintains no state.
    """
    def __init__(self, ffmpeg_path="ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def create_video(self, config: RenderConfig) -> TaskResult:
        """
        Generates a high-quality MP4 video using the provided configuration.
        
        :param config: RenderConfig object containing paths and project info.
        :return: TaskResult object indicating success or failure.
        """
        audio_path = config.audio_path
        background_path = config.image_path
        output_path = config.output_path

        if not os.path.exists(audio_path):
            return TaskResult(success=False, error_message=f"Audio file not found: {audio_path}")
        if not os.path.exists(background_path):
            return TaskResult(success=False, error_message=f"Background file not found: {background_path}")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # Determine if background is image or video
        is_video = background_path.lower().endswith(('.mp4', '.mov', '.avi', '.mkv'))

        # Base command
        cmd = [self.ffmpeg_path, "-y"] # Overwrite output

        # Input Background
        if not is_video:
            # Loop image to match audio duration
            cmd.extend(["-loop", "1", "-i", background_path])
        else:
            # Stream video (assuming it needs to loop if shorter than audio)
            cmd.extend(["-stream_loop", "-1", "-i", background_path])

        # Input Audio
        cmd.extend(["-i", audio_path])

        # Filters: Scale background to 1080p
        filter_str = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
        cmd.extend(["-vf", filter_str])
        
        # Encoding settings (High Quality H.264)
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",         # High quality
            "-pix_fmt", "yuv420p", # Compatible with most players/YouTube
            "-c:a", "aac",
            "-b:a", "320k",       # High quality audio
            "-shortest"           # End when audio ends
        ])

        cmd.append(output_path)

        logger.info(f"Running FFmpeg command for tag {config.project_tag}")
        
        try:
            # Capture FFmpeg output for logging/debugging without global side effects
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True
            )
            
            # We could read from process.stdout here if we wanted to log progress
            stdout, _ = process.communicate()

            if process.returncode != 0:
                logger.error(f"FFmpeg failed for {config.project_tag} with return code {process.returncode}")
                return TaskResult(
                    success=False, 
                    error_message=f"FFmpeg error: {stdout[-500:]}" # Last 500 chars of output
                )
            
            logger.info(f"Successfully created video: {output_path}")
            return TaskResult(success=True, output_path=output_path)

        except Exception as e:
            logger.error(f"Unexpected error during video creation: {str(e)}")
            return TaskResult(success=False, error_message=str(e))

if __name__ == "__main__":
    print("VideoEngine class loaded from app.core.video_engine.")
