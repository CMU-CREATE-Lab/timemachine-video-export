# coded in part with https://claude.ai/chat/2fba7438-0e73-41d5-bd98-313e5d0a57cc

import os
import subprocess
import threading
import time
import numpy as np
import json
import requests
from .rectangle import Rectangle
from .ffmpeg_path import resolve_ffmpeg_tool

try:
    import fcntl
    # Linux-only: grow the pipe buffer ffmpeg writes into. Default 64 KB
    # can't hold even one 1424x800 RGB frame (~3.4 MB), so 1 MB is still
    # smaller than a frame, but it lets ffmpeg buffer ~30% of one ahead.
    _F_SETPIPE_SZ = 1031
    _PIPE_TARGET_BYTES = 1024 * 1024
except ImportError:
    fcntl = None
    _F_SETPIPE_SZ = None
    _PIPE_TARGET_BYTES = None

# subprocess.communicate() reads stdout in 32 KB chunks under a select loop.
# With many concurrent decoders that adds up to a lot of GIL-bouncing syscalls
# and serializes the readers; a tight os.read with 1 MB chunks let 8-way
# parallel same-URL decode go from ~5.9 s wall to ~1.0 s in benchmarks.
_PIPE_READ_CHUNK = 1024 * 1024

def _wait_with_rusage(process):
    """Replacement for process.wait() that returns the child's CPU time.

    Uses os.wait4 to capture rusage at reap. Mutates Popen so it agrees that
    the child is gone (avoids double-reap on __del__).
    """
    pid, status, rusage = os.wait4(process.pid, 0)
    if os.WIFEXITED(status):
        rc = os.WEXITSTATUS(status)
    elif os.WIFSIGNALED(status):
        rc = -os.WTERMSIG(status)
    else:
        rc = status
    process.returncode = rc
    return rusage.ru_utime + rusage.ru_stime


def decode_video_frames(video_url, start_frame=None, n_frames=None, start_time=None, end_time=None,
                        width=None, height=None, fps=None, stats=None):
    """
    Decode a range of frames from an MP4 video file accessed via HTTPS.

    Args:
        video_url (str): HTTPS URL to the MP4 file
        start_frame (int, optional): Starting frame number (0-based)
        n_frames (int, optional): Number of frames to decode
        start_time (float, optional): Starting time in seconds
        end_time (float, optional): Ending time in seconds

    Returns:
        tuple: (frames, metadata) where:
            - frames: numpy.ndarray of shape (n_frames, height, width, 3) with RGB values
            - metadata: dict containing the full ffprobe output

    Raises:
        RuntimeError: If FFmpeg encounters an error or output size is incorrect
        ValueError: If invalid frame/time parameters are provided
        KeyError: If video stream information is missing expected fields
    """
    # Input validation
    if (start_frame is not None) != (n_frames is not None):
        raise ValueError("Both start_frame and n_frames must be provided together")
    if (start_time is not None) != (end_time is not None):
        raise ValueError("Both start_time and end_time must be provided together")
    if start_frame is not None and start_time is not None:
        raise ValueError("Cannot specify both frame numbers and timestamps")

    if width is None or height is None or fps is None:
        # Get video information using ffprobe
        probe_cmd = [
            resolve_ffmpeg_tool('ffprobe'),
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-show_format',
            '-select_streams', 'v:0',
            video_url
        ]

        try:
            probe_output, probe_error = subprocess.Popen(
                probe_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            ).communicate()
            metadata = json.loads(probe_output)

            if not metadata.get('streams'):
                raise ValueError("No streams found in video file")

            # Get the first video stream
            video_stream = metadata['streams'][0]

            # Extract video properties
            try:
                width = int(video_stream['width'])
                height = int(video_stream['height'])

                # Parse frame rate which might be in different formats
                if 'r_frame_rate' in video_stream:
                    num, den = map(int, video_stream['r_frame_rate'].split('/'))
                    fps = num / den
                elif 'avg_frame_rate' in video_stream:
                    num, den = map(int, video_stream['avg_frame_rate'].split('/'))
                    fps = num / den
                else:
                    raise KeyError("Could not find frame rate information")

            except KeyError as e:
                raise KeyError(f"Missing required video property: {str(e)}")

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFprobe error: {e.stderr.decode()}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse FFprobe output: {str(e)}")

    # Calculate duration based on input parameters
    if start_frame is not None and n_frames is not None:
        start_time = start_frame / fps
        duration = n_frames / fps
        expected_frames = n_frames
    elif start_time is not None and end_time is not None:
        duration = end_time - start_time
        expected_frames = int(duration * fps)
    else:
        raise ValueError("Either frame numbers or timestamps must be provided")

    # Build ffmpeg command. -multiple_requests 1 enables HTTP keep-alive on
    # the (https?) protocol; with 8 concurrent decoders the parallel wall
    # drops ~3.7x (6.0s -> 1.7s) vs the default. It's an input-protocol
    # option, so it must precede -i.
    cmd = [resolve_ffmpeg_tool('ffmpeg'),
           '-multiple_requests', '1',
           '-ss', str(start_time)]

    # Add time selection
    cmd.extend(['-i', video_url, '-t', str(duration)])

    # Add output format settings
    cmd.extend([
        '-f', 'image2pipe',
        '-pix_fmt', 'rgb24',
        '-vcodec', 'rawvideo',
        '-'
    ])

    # Spawn ffmpeg and read its stdout directly into the final numpy buffer.
    # Reading straight into the preallocated buffer avoids a chunks list +
    # b"".join + np.frombuffer copy chain that roughly doubled wall time per
    # tile on this workload (the join had to allocate and memcpy ~640 MiB).
    t_wall = time.monotonic()
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        if fcntl is not None:
            try:
                fcntl.fcntl(process.stdout.fileno(), _F_SETPIPE_SZ, _PIPE_TARGET_BYTES)
            except OSError:
                pass

        stderr_chunks = []
        def _drain_stderr():
            try:
                while True:
                    chunk = process.stderr.read(65536)
                    if not chunk:
                        break
                    stderr_chunks.append(chunk)
            except (ValueError, OSError):
                pass
        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        expected_bytes = width * height * 3 * expected_frames
        frames = np.empty((expected_frames, height, width, 3), dtype=np.uint8)
        buf = memoryview(frames).cast('B')
        total = 0
        while total < expected_bytes:
            target = buf[total:min(total + _PIPE_READ_CHUNK, expected_bytes)]
            n = process.stdout.readinto(target)
            if not n:
                break
            total += n
        # Catch any unexpected trailing bytes for the size-mismatch error.
        overage = process.stdout.read() if total == expected_bytes else b""
        actual_bytes = total + len(overage)

        cpu_s = _wait_with_rusage(process)
        wall_s = time.monotonic() - t_wall
        stderr_thread.join()
        stderr = b"".join(stderr_chunks)

        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg error: {stderr.decode()}")
        if stats is not None:
            stats.append({'wall_s': wall_s, 'cpu_s': cpu_s})

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFmpeg error: {e.stderr.decode()}")

    if actual_bytes != expected_bytes:
        raise RuntimeError(
            f"FFmpeg output size mismatch: expected {expected_bytes} bytes "
            f"({expected_frames} frames) but got {actual_bytes} bytes "
            f"({actual_bytes // (width * height * 3)} frames)"
        )

    return frames
