# Project: BeatManager TUI

A Python TUI for managing "Type Beat" YouTube channels, handling video composition (ffmpeg) and automated uploads (YouTube API).

## 1. Core Architecture
- **TUI Framework:** `Textual` (for a modern, responsive terminal interface).
- **Video Engine:** `FFmpeg` (via subprocess or `ffmpeg-python`) for compositing audio + static image/background video.
- **Upload Engine:** `google-api-python-client` (OAuth2 flow) for YouTube uploads.
- **Database/State:** `TinyDB` or a simple JSON file to track upload status, channel metadata, and assets.

## 2. Components

### Component A: The Video Creator (Sub-agent 1)
- **Input:** Audio file, Background (Image/Video), Metadata (Title/BPM/Scale).
- **Logic:**
    - Composite audio and visuals.
    - Ensure video duration matches audio.
    - Optional: Add text overlays (Title, BPM) via FFmpeg filters.
- **Output:** Rendered MP4 file ready for upload.

### Component B: The YouTube Manager (Sub-agent 1)
- **Input:** Rendered MP4, Metadata (Title, Description, Tags, Category).
- **Logic:**
    - Handle OAuth2 authentication (storing tokens per channel).
    - Chunked upload to YouTube.
    - Set privacy status, thumbnails, and playlists.

### Component C: The TUI Interface (Sub-agent 2)
- **Views:**
    - **Dashboard:** Overview of channels and recent uploads.
    - **Composer:** UI to select audio/visual assets and start a render.
    - **Upload Queue:** List of pending/active/completed uploads.
    - **Settings:** API key management and channel switching.

## 3. Implementation Plan

### Phase 1: Foundation (Current Session)
- Create project structure.
- Define `AssetManager` to handle local file paths.
- Set up `requirements.txt`.

### Phase 2: Engine Development (Sub-agent 1)
- Write the ffmpeg composition script.
- Write the YouTube API upload script (using a placeholder client secret).

### Phase 3: Interface Development (Sub-agent 2)
- Build the Textual TUI layout.
- Integrate the engines into the TUI with progress bars.

## 4. Next Steps
1. Create `projects/beat-manager/`.
2. Spawn Sub-agent 1 for Engine development.
3. Spawn Sub-agent 2 for TUI layout.
