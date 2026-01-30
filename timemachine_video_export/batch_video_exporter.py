from functools import cache
import math
import os
from pathlib import Path
import sys
import threading
import dateutil
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import datetime
import subprocess
import numpy as np
import argparse

import pytz

from .stopwatch import Stopwatch
from .thumbnail_api import BreathecamThumbnail
from .timemachine import TimeMachine
from concurrent.futures import ThreadPoolExecutor
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from .rectangle import Rectangle

import re

# Configuration via environment variables
BREATHECAM_SECRETS_PATH = os.environ.get('BREATHECAM_SECRETS_PATH',
                                          os.path.join(os.getcwd(), 'secrets'))
BREATHECAM_EXPORT_DIR = os.environ.get('BREATHECAM_EXPORT_DIR',
                                        os.path.join(os.getcwd(), 'exports'))

print(f"{datetime.datetime.now()} Starting batch_video_exporter.py with Python {sys.version} ")
class Thumbnails:
    @cache
    @staticmethod
    def clairton():
        # Natisha's Clairton view
        url = "https://share.createlab.org/shorturl/breathecam/f263bebc7632efa9"
        thumbnail = BreathecamThumbnail(url)

        # Increase resolution to 1:1
        thumbnail.set_scale(1, 1)

        # Increase size to 4K
        thumbnail.resize_rect_preserving_scale(3840, 2160)

        return thumbnail

    @cache
    @staticmethod
    def edgar_thomson_south():
        # Edgar Thomson South
        url = "https://share.createlab.org/shorturl/breathecam/53f9448ec86ade5b"
        thumbnail = BreathecamThumbnail(url)

        # Increase resolution to 1:1
        thumbnail.set_scale(1, 1)

        # Video width must be even
        if thumbnail.width % 2 == 1:
            thumbnail.resize_rect_preserving_scale(thumbnail.width - 1, thumbnail.height)

        return thumbnail


    @cache
    @staticmethod
    def shenango_accan_avalon():
        url = "https://thumbnails-v2.createlab.org/thumbnail?root=http%3A%2F%2Ftiles.cmucreatelab.org%2Fecam%2Ftimemachines%2Fshenango1%2F2016-10-18.timemachine%2F&width=1280&height=720&format=mp4&fps=6&tileFormat=mp4&startDwell=0&endDwell=0&boundsLTRB=1489%2C1254%2C2806%2C1995&startFrame=12537&nframes=15&labelsFromDataset&watermark=Breathe%20Project%7CCREATE%20Lab"
        thumbnail = BreathecamThumbnail(url)

        # Show full resolution
        thumbnail.width = 4240 # we can get this full width from mod-4 tiles
        thumbnail.height = 800 * 3 # the largest we can get from mod-4 tiles is 2400, not the original 2832
        thumbnail.view_rect().x1 = 0
        thumbnail.view_rect().y1 = 0
        thumbnail.view_rect().x2 = thumbnail.width
        thumbnail.view_rect().y2 = thumbnail.height

        # Video width must be even
        if thumbnail.width % 2 == 1:
            thumbnail.resize_rect_preserving_scale(thumbnail.width - 1, thumbnail.height)

        return thumbnail


    @cache
    @staticmethod
    def shenango_achd_bellevue():
        url = "https://thumbnails-v2.createlab.org/thumbnail?root=http%3A%2F%2Ftiles.cmucreatelab.org%2Fecam%2Ftimemachines%2Fshenango2%2F2016-06-06.timemachine%2F&width=1280&height=720&format=mp4&fps=6&tileFormat=mp4&startDwell=0&endDwell=0&boundsLTRB=1462%2C947%2C2778%2C1686&startFrame=4554&nframes=6&labelsFromDataset&watermark=Breathe%20Project%7CCREATE%20Lab"
        thumbnail = BreathecamThumbnail(url)

        # Show full resolution
        thumbnail.width = 4240 # we can get this full width from mod-4 tiles
        thumbnail.height = 800 * 3 # the largest we can get from mod-4 tiles is 2400, not the original 2832
        thumbnail.view_rect().x1 = 0
        thumbnail.view_rect().y1 = 0
        thumbnail.view_rect().x2 = thumbnail.width
        thumbnail.view_rect().y2 = thumbnail.height

        # Video width must be even
        if thumbnail.width % 2 == 1:
            thumbnail.resize_rect_preserving_scale(thumbnail.width - 1, thumbnail.height)

        return thumbnail




@cache
def client():
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials_file = os.path.join(BREATHECAM_SECRETS_PATH,
                                    "createlab-breathecam-bulk-video-generation-58427be4b55f.json")
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
    client = gspread.authorize(creds)
    return client

required_columns = ["Site", "Date", "Begin time", "End time", "Video", "Notes"]
first_col = "A"
last_col = chr(ord("A") + len(required_columns) - 1)
# Use the configured export directory
export_directory = BREATHECAM_EXPORT_DIR

class BatchVideoExporter:
    def __init__(self, spreadsheet_name):
        self.spreadsheet_name = spreadsheet_name
        self.df = self.read_spreadsheet(spreadsheet_name)

    def read_spreadsheet(self, spreadsheet_name):
        # Open the main sheet in this spreadsheet.  Complain if there's more than one sheet
        spreadsheet = client().open(spreadsheet_name)
        worksheets = spreadsheet.worksheets()
        if len(worksheets) > 1:
            raise ValueError(f"Expected only one sheet in {spreadsheet_name}, but found {len(worksheets)} sheets")
        worksheet = worksheets[0]

        # Get all tables in the worksheet    df = pd.DataFrame(data[1:], columns=data[0])
        rows = worksheet.get(f"{first_col}:{last_col}")

        header = rows[0]
        data_rows = rows[1:]
        assert header == required_columns

        df = pd.DataFrame(data_rows, columns=header)
        # None in Video or Notes columns should be empty string instead
        df["Video"] = df["Video"].fillna("")
        df["Notes"] = df["Notes"].fillna("")

        return df

    def export_video(self, row):
        site = row["Site"]
        # Parse as datetime.date
        date = dateutil.parser.parse(row["Date"]).date()
        # Parse as datetime.time
        begin_time = dateutil.parser.parse(row["Begin time"]).time()
        end_time = dateutil.parser.parse(row["End time"]).time()
        video = row["Video"]
        notes = row["Notes"]

        et = pytz.timezone("America/New_York")
        begin_datetime = et.localize(datetime.datetime.combine(date, begin_time))
        end_datetime = et.localize(datetime.datetime.combine(date, end_time))

        # Don't create exports directory since we need to symlink it to the web server exports directory
        #os.makedirs(export_directory, exist_ok=True)
        # Create temporary file in exports directory
        export_filename = site
        export_filename += f"-{begin_datetime.strftime('%Y%m%d-%H%M%S')}"
        export_filename += f"-{end_datetime.strftime('%H%M%S')}-et"
        export_filename += ".mp4"
        export_path = os.path.join(export_directory, export_filename)

        row_idx = row.name
        start_time = datetime.datetime.now(pytz.UTC).astimezone()
        self.update_spreadsheet_cell(row_idx, f"Started at {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            with Stopwatch(f"Exporting video for {site} from {begin_datetime} to {end_datetime}"):
                render_video_site(site, begin_datetime, end_datetime, export_path, use_original_full_res=True)
                print(f"BatchVideoExporter: Exported video to {export_path} ({os.path.getsize(export_path)/1e6:.06f} MB)")

            web_export_prefix = "https://videos.breathecam.org/"

            video_url = web_export_prefix + os.path.basename(export_path)
            video_link = f'=hyperlink("{video_url}", "{os.path.basename(export_path)}")'
            self.update_spreadsheet_cell(row_idx, video_link)
            return export_path

        except Exception as e:
            self.update_spreadsheet_cell(row_idx, f"Error: {str(e)}")
            raise

    def export_next(self):
        """Export the next video in the queue"""
        row = self.find_next_row()
        if row is None:
            print("No more videos to export")
            return False
        self.export_video(row)
        return True

    def find_next_row(self):
        """Find the first row where Video column is empty and all required fields are present"""
        empty_video_mask = self.df["Video"] == ""
        valid_fields_mask = (
            self.df["Site"].notna() &
            self.df["Date"].notna() &
            self.df["Begin time"].notna() &
            self.df["End time"].notna()
        )
        eligible_rows = self.df[empty_video_mask & valid_fields_mask]
        if len(eligible_rows) == 0:
            return None
        return eligible_rows.iloc[0]

    def update_spreadsheet_cell(self, row_idx, value):
        """Update the Video cell for the given row, but verify row contents first"""
        worksheet = client().open(self.spreadsheet_name).worksheets()[0]
        # Spreadsheet rows are 1-based and include header
        sheet_row = row_idx + 2

        # Read the entire row to verify contents
        row_data = worksheet.row_values(sheet_row)
        expected_row = self.df.iloc[row_idx]

        # Verify key fields match
        if (row_data[0] != expected_row["Site"] or
            row_data[1] != expected_row["Date"] or
            row_data[2] != expected_row["Begin time"] or
            row_data[3] != expected_row["End time"]):
            raise ValueError(
                f"Row contents changed while processing! Expected:\n"
                f"Site: {expected_row['Site']}, Date: {expected_row['Date']}, "
                f"Begin: {expected_row['Begin time']}, End: {expected_row['End time']}\n"
                f"But found:\n"
                f"Site: {row_data[0]}, Date: {row_data[1]}, "
                f"Begin: {row_data[2]}, End: {row_data[3]}"
            )

        # If verification passes, update the cell
        # Update using row/col numbers instead of A1 notation
        worksheet.update_cell(sheet_row, 5, value)  # 5 is the column number for "Video" (E)
        # Update local dataframe
        self.df.at[row_idx, "Video"] = value



def render_video_site(site: str, begin_datetime: datetime.datetime, end_datetime: datetime.datetime, export_path: str, use_original_full_res=False):
    site = site.lower()
    # Replace each string of one or more non-alnum characters with a single _
    site = re.sub(r'[^a-z0-9]+', '_', site)

    # Assert begin and end have timezones
    assert begin_datetime.tzinfo is not None, "begin_datetime must have a timezone"
    assert end_datetime.tzinfo is not None, "end_datetime must have a timezone"
    # Assert site matches an attribute in Thumbnails
    assert hasattr(Thumbnails, site), f"Site {site} not found in Thumbnails"
    thumbnail = getattr(Thumbnails, site)().copy()

    thumbnail.set_begin_end_times(begin_datetime, end_datetime)
    if use_original_full_res:
        timemachine = TimeMachine.from_breathecam_thumbnail(thumbnail)
        # ffmpeg requires even width and height
        timemachine_width = timemachine.width()
        timemachine_height = timemachine.height()
        if timemachine_width % 2 == 1:
            timemachine_width -= 1
        if timemachine_height % 2 == 1:
            timemachine_height -= 1
        # Set thumbnail size to original size from timemachine
        thumbnail.width = timemachine_width
        thumbnail.height = timemachine_height
        thumbnail.view_rect().x1 = 0
        thumbnail.view_rect().y1 = 0
        thumbnail.view_rect().x2 = thumbnail.width
        thumbnail.view_rect().y2 = thumbnail.height
        print(f"Using original full resolution size: {thumbnail.width}x{thumbnail.height}")
        # Since we changed the thumbnail to exactly match the original time machine,
        # it should be 1:1

    assert thumbnail.scale() == (1, 1), "Thumbnail must have a scale of 1:1"
    output = OutputToVideo(export_path, thumbnail.width, thumbnail.height)

    return render_video_from_thumbnail(begin_datetime, end_datetime, output, thumbnail)

# class OutputToPngs:
#     def __init__(self, export_path, width, height):
#         self.width = width
#         self.height = height
#         self.export_path = export_path
#         self.frame_number = 0
#         # Make sure export_path includes something of form %\d*d
#         # so we can use it as a prefix for the frame numbers
#         if not re.search(r"%\d*d", export_path):
#             raise ValueError(f"export_path {export_path} must include a format string of form %d or %NNNd")
#         os.makedirs(os.path.dirname(export_path), exist_ok=True)

#     # frame is ndarray of uint8 of shape (height, width, 3)
#     # with pixel values in range 0-255
#     def write_frame(self, frame: np.ndarray):
#         # Create a filename for the frame
#         filename = self.export_path % self.frame_number
#         # Make sure the suffix is correct
#         if not filename.endswith(".png"):
#             raise ValueError(f"Filename {filename} must end with .png")
#         self.frame_number += 1
#         # Save the frame as a PNG file
#         # Use PIL to save the image
#         from PIL import Image
#         image = Image.fromarray(frame)
#         assert image.size == (self.width, self.height), f"Image size {image.size} does not match expected size {(self.width, self.height)}"
#         image.save(filename, "PNG")

#     def close(self):
#         pass

class OutputToStream:
    def __init__(self, stream, width, height):
        self.width = width
        self.height = height
        self.stream = stream

    def write_frame(self, frame):
        # Write frame to stdout
        self.stream.write(frame.tobytes())
        self.stream.flush()

    def close(self):
        pass


def ensure_integer(num):
    assert num == round(num), f"Number {num} must be an integer"
    return round(num)

class OutputToVideo:
    def __init__(self, export_path, width, height):
        self.width = ensure_integer(width)
        self.height = ensure_integer(height)
        self.export_path = export_path
        self.ffmpeg_output = []
        self.process = None

        # Create temporary filename with pid and thread id
        self.temp_path = f"{export_path}.{os.getpid()}.{threading.get_ident()}.mp4"

        # Remove temporary file if it exists
        Path(self.temp_path).unlink(missing_ok=True)

        # Set up the process with stderr redirected to stdout
        command = [
            'ffmpeg',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{self.width}x{self.height}',  # size of one frame
            '-pix_fmt', 'rgb24',
            '-r', '30',  # frames per second
            '-i', '-',  # The input comes from a pipe
            '-c:v', 'libx264',
            '-preset', 'slow',  # Higher quality encoding
            '-crf', '18',  # Constant Rate Factor (0-51, lower is better quality)
            '-pix_fmt', 'yuv420p',  # Compatibility for media players
            self.temp_path
        ]

        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        # Start a thread to read and capture output
        def capture_output():
            for line in iter(self.process.stdout.readline, b''):
                line_str = line.decode('utf-8', errors='replace')
                self.ffmpeg_output.append(line_str)

        output_thread = threading.Thread(target=capture_output)
        output_thread.daemon = True
        output_thread.start()

    def write_frame(self, frame):
        try:
            self.process.stdin.write(frame.tobytes())
        except Exception as e:
            print(f"Error writing frame to ffmpeg process: {str(e)}")
            print("ffmpeg output:")
            for line in self.ffmpeg_output:
                print(line.strip())
            raise
        self.process.stdin.flush()

    def close(self):
        self.process.stdin.close()
        self.process.wait()

        if self.process.returncode == 0:
            # Atomic rename of temp file to final path
            os.replace(self.temp_path, self.export_path)
        else:
            # Clean up temp file if ffmpeg failed
            if os.path.exists(self.temp_path):
                os.unlink(self.temp_path)
            raise RuntimeError(f"ffmpeg failed with return code {self.process.returncode}")

        # Atomic rename of temp file to final path
        os.replace(self.export_path, self.export_path)

def render_video_from_thumbnail(begin_datetime, end_datetime, output: OutputToVideo, thumbnail: BreathecamThumbnail):
    timemachine = TimeMachine.from_breathecam_thumbnail(thumbnail)

    # TO DO: Download multiple shards in parallel

    source_width = thumbnail.view_rect().width
    source_height = thumbnail.view_rect().height

    # Encode frames into mp4 using external ffmpeg process
    output_width = ensure_integer(thumbnail.width)
    output_height = ensure_integer(thumbnail.height)

    # Make sure the output dimensions match the thumbnail dimensions
    assert output.width == output_width, f"Output width {output.width} does not match thumbnail"
    assert output.height == output_height, f"Output height {output.height} does not match thumbnail"
    assert output.width % 2 == 0, "Output width must be even"
    assert output.height % 2 == 0, "Output height must be even"

    start_frame = timemachine.frameno_from_date_after_or_equal(begin_datetime)
    end_frame = timemachine.frameno_from_date_before_or_equal(end_datetime)
    nframes = end_frame - start_frame + 1

    # We have to process in small chunks or we run out of RAM
    chunk_size = 200
    frame_chunks = range(start_frame, start_frame + nframes, chunk_size)

    # Download a range of frames, possibly rendering subsamples and extracting/resizing to match requested view rect
    def download_chunk(chunk_info):
        chunk_start, chunk_frames = chunk_info
        frames = timemachine.download_scaled_video_frame_range(chunk_start, chunk_frames, thumbnail.view_rect(), output_width, output_height)
        assert frames[0].shape == (output_height, output_width, 3), f"Frame shape {frames[0].shape} does not match expected {(output_height, output_width, 3)}"
        print(f"BatchVideoExporter: Downloaded {len(frames)} frames")
        return frames

    # Create list of chunk information tuples
    chunk_infos = []
    for chunk_start in frame_chunks:
        chunk_frames = min(chunk_size, start_frame + nframes - chunk_start)
        chunk_infos.append((chunk_start, chunk_frames))

    # Use multiple workers but process results in order to avoid memory buildup
    max_workers = 1
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit first batch of jobs
        pending_futures = {}
        next_chunk_idx = 0
        max_queued_chunks = max_workers  # Control how many chunks we pre-fetch

        # Keep processing until all chunks are done
        while next_chunk_idx < len(chunk_infos) or pending_futures:
            # Submit new jobs up to our limit
            while next_chunk_idx < len(chunk_infos) and len(pending_futures) < max_queued_chunks:
                future = executor.submit(download_chunk, chunk_infos[next_chunk_idx])
                pending_futures[future] = next_chunk_idx
                next_chunk_idx += 1

            # Wait for the next result in sequence
            if pending_futures:
                # Find the future with the lowest chunk index
                next_future = min(pending_futures.items(), key=lambda x: x[1])[0]

                # Get its result (will block until ready)
                frames = next_future.result()
                chunk_idx = pending_futures.pop(next_future)

                print(f"Processing chunk {chunk_idx} ({len(frames)} frames)")

                # Write frames to ffmpeg process
                for frame in frames:
                    output.write_frame(frame)
    output.close()


def main():
    parser = argparse.ArgumentParser(description='Batch Video Exporter for Breathecam')
    parser.add_argument('spreadsheet_name', help='Name of the Google Spreadsheet to process')
    parser.add_argument('--export-next', action='store_true',
                       help='Export the next pending video from the spreadsheet')

    args = parser.parse_args()

    exporter = BatchVideoExporter(args.spreadsheet_name)

    if args.export_next:
        try:
            if exporter.export_next():
                print("Successfully exported next video")
                return 0
            else:
                print("No videos pending export")
                return 1
        except Exception as e:
            print(f"Error exporting video: {str(e)}")
            # Show traceback
            import traceback
            traceback.print_exc()
            return 2
    else:
        parser.print_help()
        return 1

if __name__ == '__main__':
    exit(main())
