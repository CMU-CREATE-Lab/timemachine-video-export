# coded in part with https://claude.ai/chat/2fba7438-0e73-41d5-bd98-313e5d0a57cc

import datetime
import concurrent
import json
import requests
import re
from .thumbnail_api import Rectangle, BreathecamThumbnail
import math
import numpy as np
import os
import pandas as pd
from .video_decoder import decode_video_frames
import pytz
import dateutil.parser
import time
from functools import cache
import threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
import cv2

# Cap cv2's internal thread pool. Our resize step also runs inside a Python
# thread pool (LANCZOS_THREADS, defaults to 16), so the effective concurrency
# is the product of the two. Letting cv2 default to nproc here gave 16x32=512
# OS threads on a 32-core box, which destroyed throughput. 4 was the empirical
# sweet spot in our sweep. Override via CV2_NUM_THREADS.
cv2.setNumThreads(int(os.environ.get('CV2_NUM_THREADS', 4)))


CAMERAS = {
    "Clairton Coke Works": "clairton4",
    "Shell Plastics West": "vanport3",
    "Edgar Thomson South": "westmifflin2",
    "Metalico": "accan2",
    "Revolution ETC/Harmon Creek Gas Processing Plants": "cryotm",
    "Riverside Concrete": "cementtm",
    "Shell Plastics East": "center1",
    "Irvin": "irvin1",
    "North Shore": "heinz",
    "Mon. Valley": "walnuttowers1",
    "Downtown": "trimont1",
    "Oakland": "oakland"
}

class TimeMachine:
    @staticmethod
    def find_timemachine_paths_recursively(root_dir):
        """
        Recursively find all timemachine paths in the given directory.
        """
        import os
        timemachine_paths = []
        for dirpath, dirnames, filenames in os.walk(root_dir):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if filepath.endswith(".timemachine/tm.json"):
                    timemachine_paths.append(dirpath)
        return timemachine_paths

    def read_url_or_path(self, url_or_path: str):
        try:
            if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
                response = requests.get(url_or_path, timeout=10)
                if response.status_code == 404:
                    raise FileNotFoundError
                response.raise_for_status()
                return response.json()
            else:
                if not os.path.exists(url_or_path):
                    raise FileNotFoundError
                with open(url_or_path, 'r') as f:
                    return json.load(f)

        except FileNotFoundError:
            raise FileNotFoundError(f"No camera data found for that date")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error while fetching {url_or_path}") from e
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {url_or_path}") from e
        except Exception as e:
            raise RuntimeError(f"Unexpected error reading {url_or_path}") from e


    def __init__(self, root_url_or_path: str, timezone=pytz.timezone("America/New_York"), verbose=True):
        self.root_url = root_url_or_path
        self.tm_url = f"{self.root_url}/tm.json"
        if verbose:
            print(f"Fetching {self.tm_url}")
        self.tm = self.read_url_or_path(self.tm_url)
        datasets = self.tm['datasets']
        assert(len(datasets) == 1)
        dataset = datasets[0]
        id = dataset['id']
        self.tile_root_url = f"{self.root_url}/{id}"
        self.r_url = f"{self.tile_root_url}/r.json"
        if verbose:
            print(f"Fetching {self.r_url}")
        self.r = self.read_url_or_path(self.r_url)
        if verbose:
            print(f'TimeMachine has {self.r["nlevels"]} levels and {len(self.capture_times())} frames')
        self.timezone = timezone

    @cache
    def capture_datetimes(self):
        # Use strptime to parse the capture times since it's faster.  Format is 2024-09-09 00:00:00
        return [self.timezone.localize(datetime.datetime.strptime(t, "%Y-%m-%d %H:%M:%S")) for t in self.capture_times()]
        #return [self.timezone.localize(dateutil.parser.parse(t)) for t in self.capture_times()]

    @cache
    def frameno_from_date_before_or_equal(self, dt: datetime.datetime):
        for i, t in enumerate(self.capture_datetimes()):
            if t > dt:
                return max(0, i - 1)
        return len(self.capture_datetimes()) - 1

    @cache
    def frameno_from_date_after_or_equal(self, dt: datetime.datetime):
        for i, t in enumerate(self.capture_datetimes()):
            if t >= dt:
                return i
        return len(self.capture_datetimes()) - 1

    @classmethod
    def from_breathecam_thumbnail(cls, thumbnail: BreathecamThumbnail):
        return cls(thumbnail.timemachine_root_url())

    def tile_coords(self):
        """
        Enumerate the tiles in the timemachine.
        """
        ret = []
        for l, level in enumerate(self.r['level_info']):
            cols = list(range(level['cols']))
            if cols[-1] % 4 != 0:
                # Add an extra mod-4 column at the end
                cols.append(cols[-1] // 4 * 4 + 4)
            for c in cols:
                rows = list(range(level['rows']))
                if rows[-1] % 4 != 0:
                    # Add an extra mod-4 row at the end
                    rows.append(rows[-1] // 4 * 4 + 4)
                for r in rows:
                    is_mod_4 = (r % 4 == 0) and (c % 4 == 0)
                    ret.append({"l": l, "c": c, "r": r, "is_mod_4": is_mod_4})
        return ret

    def tile_paths(self):
        ret = []
        for tile in self.tile_coords():
            path = f"{self.tile_root_url}/{tile['l']}/{tile['r']}/{tile['c']}.mp4"
            ret.append({"path": path, "l": tile["l"], "is_mod_4": tile['is_mod_4']})
        return ret

    def delete_non_mod4_tiles(self, delete=False):
        paths = self.tile_paths()
        # Make sure all mod-4 tiles are present
        mod_4_tile_count = 0
        for pathinfo in paths:
            is_mod_4 = pathinfo['is_mod_4']
            path = pathinfo['path']
            if is_mod_4:
                assert os.path.exists(path), f"Missing {path}"
                mod_4_tile_count += 1
        print(f"    Found all {mod_4_tile_count} mod-4 tiles")

        to_delete = []
        n_non_mod_4 = 0

        for pathinfo in paths:
            is_mod_4 = pathinfo['is_mod_4']
            path = pathinfo['path']
            if not is_mod_4:
                n_non_mod_4 += 1
                if os.path.exists(path):
                    to_delete.append(path)

        if len(to_delete) == 0:
            print("    No non-mod-4 tiles to delete")
        else:
            print(f"    Found {len(to_delete)} non-mod-4 tiles to delete (out of a possible {n_non_mod_4})")
            for path in to_delete:
                l, c, r = [int(s) for s in re.search(r"(\d+)/(\d+)/(\d+)\.mp4$", path).groups()]
                assert not (c % 4 == 0 and r % 4 == 0), f"Tile {path} is mod-4, but was marked for deletion"
                if delete:
                    os.remove(path)
            if delete:
                print(f"    Deleted {len(to_delete)} non-mod-4 tiles")
        return to_delete

    @staticmethod
    def download(
        location: str,
        date: datetime.date,
        time: datetime.time,
        frames: int,
        rect: Rectangle,
        subsample: int) -> np.ndarray:
        """
        Downloads a video for the given tmera location, date and time.

        Parameters:
        ---
        * location - Location of the tmera, refer to `CAMERAS` for valid locations.
        * date - The day of the video
        * time - The time to start the capture
        * frames - The number of frames to capture
        * rect - The view to capture
        * subsample - The subsample of the produced video

        Returns:
        ---
        If frames is 1, a numpy array of dimensions width*height*4. If frames
        is greater than 1, a numpy array of dimensions frames*width*height*4.
        """

        if date is None:
            raise Exception("Date not set.")

        if time is None:
            raise Exception("Time not set.")

        # date_str = date.strftime("%Y-%m-%d")
        # time_str = get_time(time)
        # start_time = f"{date_str} {time_str.strftime('%H:%M:%S')}"
        # url = f"{BASE_URL}/{CAMERAS[location]}/{date_str}.timemachine"

        # tm = TimeMachine(url)

        # start_frame = tm.frame_from_date(start_time)

        # if start_frame < 0:
        #     raise Exception("First frame invalid.")
        #     return None

        # remaining_frames = len(tm.capture_times()) - start_frame

        # if remaining_frames < frames:
        #     frames = remaining_frames

        # video = tm.download_video(start_frame, frames, view, subsample)

        # opacity = np.full((video.shape[0], video.shape[1], video.shape[2], 1), 255, dtype=video.dtype)
        # video = np.concatenate((video, opacity), axis=3) / 255.0

        # if frames == 1:
        #     return video[0]
        # else:
        #     return video


    # output_width, output_height, source_rect (might be non-integers)

    def download_scaled_video_frame_range(self, start_frame_no: int, nframes: int, source_rect: Rectangle, output_width:int, output_height:int, max_threads:int=8, stats:dict=None):
        """
        Download and assemble video tiles into a single numpy array using parallel threads.

        Args:
            start_frame_no: Starting frame number
            nframes: Number of frames to download
            source_rect: Source rectangle in full resolution coordinates.  Can be non-integer.
            output_width: Width of the output video frames.  Must be integer
            output_height: Height of the output video frames.  Must be integer
            max_threads: Maximum number of concurrent download threads

        Returns:
            numpy.ndarray: Array of shape (nframes, height, width, 3) containing the video data
        """

        # Compute source tile level and rectangle
        # max_scale should be <= 1 since we are always downsampling or same-size
        max_scale = max(output_width / source_rect.width, output_height / source_rect.height)
        if max_scale > 1:
            raise ValueError(f"Cannot upsample.  Output size {output_width}x{output_height} is larger than source rect {source_rect.width()}x{source_rect.height()}")

        tile_level = self.detailed_tile_level_for_scale(max_scale)
        # Adjust source_rect to match tile level subsample
        subsample = self.subsample_from_level(tile_level)
        # Adjust rectangle to level coordinates
        source_rect_level = Rectangle(
            source_rect.x1 / subsample,
            source_rect.y1 / subsample,
            source_rect.x2 / subsample,
            source_rect.y2 / subsample
        )

        # Compute integer rectangle to download
        source_rect_to_download = Rectangle(
            int(math.floor(source_rect_level.x1)),
            int(math.floor(source_rect_level.y1)),
            int(math.ceil(source_rect_level.x2)),
            int(math.ceil(source_rect_level.y2))
        )

        download = self.download_video_frame_range(
            start_frame_no=start_frame_no,
            nframes=nframes,
            rect=source_rect_to_download,
            subsample=subsample,
            max_threads=max_threads,
            stats=stats,
        )
        if stats is not None:
            # Pre-LANCZOS buffer dims (the assembled tile mosaic before resize).
            stats.setdefault('pre_lanczos_dims', []).append(
                [download.shape[2], download.shape[1]]
            )

        # Calculate the floating-point crop rectangle within the downloaded frames.
        # source_rect_level is in level coordinates; translate to downloaded frame coordinates
        # by subtracting the origin of source_rect_to_download
        crop_box = (
            source_rect_level.x1 - source_rect_to_download.x1,
            source_rect_level.y1 - source_rect_to_download.y1,
            source_rect_level.x2 - source_rect_to_download.x1,
            source_rect_level.y2 - source_rect_to_download.y1
        )

        # Create output array
        result = np.zeros((nframes, output_height, output_width, 3), dtype=np.uint8)

        # Resize each frame with cv2.resize + INTER_LANCZOS4. We snap the
        # fractional crop_box to integer pixel boundaries: in practice (for
        # axis-aligned source rectangles) the offset is already integer; in
        # the worst case we lose a sub-pixel alignment shift that is
        # imperceptible. cv2.warpAffine could preserve the sub-pixel crop but
        # benchmarked ~3x slower than cv2.resize for this scale operation.
        #
        # cv2's LANCZOS-4 uses a fixed 8-tap kernel and does not widen on
        # downsampling, unlike PIL LANCZOS. To restore equivalent antialiasing
        # we pre-blur the source with a Gaussian whose sigma matches the
        # downsample ratio per axis (scale-space anti-alias formula). Below
        # sigma~0.3 the blur has no measurable effect, so we skip it.
        x1, y1, x2, y2 = crop_box
        cx1, cy1 = int(math.floor(x1)), int(math.floor(y1))
        cx2, cy2 = int(math.ceil(x2)), int(math.ceil(y2))
        sx = (x2 - x1) / output_width
        sy = (y2 - y1) / output_height
        sigma_x = 0.5 * math.sqrt(max(sx * sx - 1.0, 0.0))
        sigma_y = 0.5 * math.sqrt(max(sy * sy - 1.0, 0.0))
        needs_blur = max(sigma_x, sigma_y) > 0.3

        lanczos_cpu_acc = [0.0]
        lanczos_cpu_lock = threading.Lock()
        def resize_one(i):
            t_cpu = time.thread_time() if stats is not None else 0.0
            src = download[i, cy1:cy2, cx1:cx2]
            if needs_blur:
                src = cv2.GaussianBlur(src, (0, 0), sigmaX=sigma_x, sigmaY=sigma_y)
            result[i] = cv2.resize(src, (output_width, output_height), interpolation=cv2.INTER_LANCZOS4)
            if stats is not None:
                d = time.thread_time() - t_cpu
                with lanczos_cpu_lock:
                    lanczos_cpu_acc[0] += d

        # Only pay the thread-pool overhead when the per-frame resize is large enough
        # to dominate it. Threshold picked empirically: resizes below ~1 megapixel run
        # faster serially.
        # LANCZOS releases the GIL, so we scale past max_threads (which gates
        # network/decoder concurrency). 16 was the empirical sweet spot on a
        # 32-core box; 24+ regressed from thread-pool overhead and memory-bus
        # contention.
        output_megapixels = (output_width * output_height) / 1_000_000
        lanczos_threads = int(os.environ.get('LANCZOS_THREADS', 16))
        use_threads = nframes > 1 and lanczos_threads > 1 and output_megapixels >= 1.0
        if use_threads:
            with ThreadPoolExecutor(max_workers=min(lanczos_threads, nframes)) as executor:
                for _ in executor.map(resize_one, range(nframes)):
                    pass
        else:
            for i in range(nframes):
                resize_one(i)

        if stats is not None:
            stats['lanczos_cpu_s'] = stats.get('lanczos_cpu_s', 0.0) + lanczos_cpu_acc[0]

        return result

    def download_video_frame_range(self, start_frame_no: int, nframes: int, rect: Rectangle, subsample:int=1, max_threads:int=8, stats:dict=None):
        """
        Download and assemble video tiles into a single numpy array using parallel threads.

        Args:
            start_frame_no: Starting frame number
            nframes: Number of frames to download
            rect: Rectangle coordinates after subsampling
            subsample: Subsample factor
            max_threads: Maximum number of concurrent download threads

        Returns:
            numpy.ndarray: Array of shape (nframes, height, width, 3) containing the video data
        """

        rect = rect.ensure_integer()
        level = self.level_from_subsample(subsample)
        level_width = self.width(subsample)
        level_height = self.height(subsample)

        # Create output array
        result = np.zeros((nframes, rect.height, rect.width, 3), dtype=np.uint8)

        # Compute tile range
        min_tile_y = rect.y1 // self.tile_height()
        max_tile_y = 1 + (rect.y2 - 1) // self.tile_height()
        min_tile_x = rect.x1 // self.tile_width()
        max_tile_x = 1 + (rect.x2 - 1) // self.tile_width()

        # Function to download and process a single tile
        def process_tile(tile_x, tile_y):
            tile_url = self.tile_url(level, tile_x, tile_y)

            # # Check if tile exists
            # response = requests.head(tile_url)
            # if response.status_code == 404:
            #     return None

            tile_rectangle = Rectangle(
                tile_x * self.tile_width(),
                tile_y * self.tile_height(),
                (tile_x + 1) * self.tile_width(),
                (tile_y + 1) * self.tile_height()
            )

            intersection = rect.intersection(tile_rectangle)
            if intersection is None:
                return None

            src_rect = intersection.translate(-tile_rectangle.x1, -tile_rectangle.y1)
            dest_rect = intersection.translate(-rect.x1, -rect.y1)

            try:
                frames = decode_video_frames(
                    video_url=tile_url,
                    start_frame=start_frame_no,
                    n_frames=nframes,
                    width = self.tile_width(),
                    height = self.tile_height(),
                    fps = self.fps(),
                    stats = stats.setdefault('tile_decoders', []) if stats is not None else None,
                )
                return (frames, src_rect, dest_rect)
            except Exception as e:
                print(f"Error processing tile {tile_url}: {str(e)}")
                return None

        # Create list of all tile coordinates
        tiles = [(x, y) for y in range(min_tile_y, max_tile_y)
                       for x in range(min_tile_x, max_tile_x)]
        n_tiles = len(tiles)
        print(f"Processing {n_tiles} tiles with {max_threads} threads")

        # Process tiles in parallel
        with ThreadPoolExecutor(max_workers=max_threads) as executor:
            # Submit all tasks
            future_to_tile = {executor.submit(process_tile, x, y): (x, y)
                            for x, y in tiles}

            # Process results as they complete
            for i, future in enumerate(concurrent.futures.as_completed(future_to_tile), 1):
                tile_x, tile_y = future_to_tile[future]
                result_data = future.result()

                if result_data is not None:
                    frames, src_rect, dest_rect = result_data
                    t_cpu = time.thread_time() if stats is not None else 0.0
                    result[:,
                           dest_rect.y1:dest_rect.y2,
                           dest_rect.x1:dest_rect.x2,
                           :] = frames[:,
                                     src_rect.y1:src_rect.y2,
                                     src_rect.x1:src_rect.x2,
                                     :]
                    if stats is not None:
                        stats['composite_cpu_s'] = stats.get('composite_cpu_s', 0.0) + (time.thread_time() - t_cpu)
                print(f"Completed {i} of {n_tiles} tiles")
        return result

    def download_video_time_range(self, start_time: datetime.datetime, end_time: datetime.datetime, rect: Rectangle, subsample:int=1):
        start_frame = self.frameno_from_date_after_or_equal(start_time)
        end_frame = self.frameno_from_date_before_or_equal(end_time)
        nframes = end_frame - start_frame + 1
        return self.download_video_frame_range(start_frame, nframes, rect, subsample)

    # tile_x and tile_y are in tile coordinates / 4
    def tile_url(self, level:int, tile_x:int, tile_y:int):
        return f"{self.tile_root_url}/{level}/{tile_y*4}/{tile_x*4}.mp4"

    def level_from_subsample(self, subsample:int) -> int:
        log2_subsample = math.log2(subsample)
        assert(log2_subsample.is_integer())
        # Find level_info for subsample
        level_number = round(len(self.level_info()) - 1 - log2_subsample)
        print(f"Subsample {subsample} corresponds to level {level_number}")
        assert level_number >= 0, f"Subsample {subsample} too high for timemachine of {len(self.level_info())} levels (max subsample {self.max_subsample()})"
        return level_number

    def subsample_from_level(self, level:int) -> int:
        return 2 ** (len(self.level_info()) - 1 - level)

    def max_subsample(self) -> int:
        return self.subsample_from_level(0)

    def detailed_tile_level_for_scale(self, scale:float) -> int:
        """
        Given a desired scale (output size / source size), return the tile level that produces more detail
        than the request, within the valid range of levels.
        """
        if scale > 1:
            raise ValueError("Scale must be <= 1.0")

        max_level = len(self.level_info()) - 1
        desired_tile_level = max_level - math.log2(1 / scale)
        if desired_tile_level.is_integer():
            # If level is exact scale requested, bump it up to next level for more detail
            # or to compensate for offset coordinates
            tile_level = int(desired_tile_level)+1
        else:
            tile_level = math.ceil(desired_tile_level)
        if tile_level < 0:
            tile_level = 0
        elif tile_level > max_level:
            tile_level = max_level
        return tile_level

    # Convenience accessors for tm and r
    def capture_times(self):
        return self.tm["capture-times"]

    def level_info(self):
        return self.r["level_info"]

    def fps(self):
        return self.r["fps"]

    def width(self, subsample:int=1):
        return int(math.ceil(self.r["width"]/subsample))

    def height(self, subsample:int=1):
        return int(math.ceil(self.r["height"]/subsample))

    def tile_width(self):
        return self.r["video_width"]

    def tile_height(self):
        return self.r["video_height"]

    def info(self):
        print(f"TimeMachine root: {self.root_url}")
        print(f"Tile root: {self.tile_root_url}")
        print(f"Capture times: {self.capture_times()}")
        print(f"Level info: {self.level_info()}")
        print(f"FPS: {self.fps()}")
        print(f"Width: {self.width()}")
        print(f"Height: {self.height()}")
        print(f"Tile width: {self.tile_width()}")
        print(f"Tile height: {self.tile_height()}")
        print(f"r: {self.r}")
        print(f"tm: {self.tm}")
