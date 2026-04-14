from functools import cache
import os
from pathlib import Path
import threading
import datetime
import subprocess
import re

from .thumbnail_api import BreathecamThumbnail
from .timemachine import TimeMachine
from concurrent.futures import ThreadPoolExecutor
from .rectangle import Rectangle


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
