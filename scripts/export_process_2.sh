#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"
LOG_FILE="$PROJECT_DIR/export_log_2.txt"

echo "Starting export_process_2.sh" >> "$LOG_FILE"

# ffmpeg/ffprobe are located via PATH or the FFMPEG_DIR env var
# (set FFMPEG_DIR in the crontab if ffmpeg isn't on PATH).
export BREATHECAM_SECRETS_PATH="${BREATHECAM_SECRETS_PATH:-$PROJECT_DIR/secrets}"
export BREATHECAM_EXPORT_DIR="${BREATHECAM_EXPORT_DIR:-$PROJECT_DIR/exports}"

cd "$PROJECT_DIR"
source venv/bin/activate
python -u -m timemachine_video_export.batch_video_exporter "Natisha Breathe Cam video exports" --export-next >> "$LOG_FILE" 2>&1
echo "Finished export_process_2.sh" >> "$LOG_FILE"
