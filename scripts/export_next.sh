#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# Set environment variables for secrets and export directories
# These should be overridden by the user if running from a different location
export BREATHECAM_SECRETS_PATH="${BREATHECAM_SECRETS_PATH:-/home/rsargent/projects/plume_detect/secrets}"
export BREATHECAM_EXPORT_DIR="${BREATHECAM_EXPORT_DIR:-/home/rsargent/projects/plume_detect/exports}"

source venv/bin/activate

while true; do
    python -m timemachine_video_export.batch_video_exporter "Natisha Breathe Cam video exports" --export-next
    sleep 60
done
