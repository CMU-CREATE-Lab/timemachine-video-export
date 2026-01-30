#!/bin/bash

# Add /usr/local/bin to PATH
export PATH=$PATH:/usr/local/bin

# Set environment variables for secrets and export directories
export BREATHECAM_SECRETS_PATH="${BREATHECAM_SECRETS_PATH:-/home/rsargent/projects/plume_detect/secrets}"
export BREATHECAM_EXPORT_DIR="${BREATHECAM_EXPORT_DIR:-/home/rsargent/projects/plume_detect/exports}"

cd /home/rsargent/projects/plume_detect
source venv/bin/activate
python -u -m timemachine_video_export.batch_video_exporter "Natisha Breathe Cam video exports" --export-next >> export_log_2.txt 2>&1
