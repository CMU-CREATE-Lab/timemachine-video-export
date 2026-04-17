"""Profile the 3840x2160 squeeze render to understand CPU/threading/I-O breakdown."""
import os
import time
import threading
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import psutil

from timemachine_video_export import Rectangle
from timemachine_video_export.video_renderer import (
    OutputToVideo, Thumbnails, render_video_from_thumbnail,
)


def main():
    begin = datetime(2025, 2, 15, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    end = datetime(2025, 2, 15, 8, 1, 0, tzinfo=ZoneInfo("America/New_York"))

    thumbnail = Thumbnails.clairton().copy()
    thumbnail.set_begin_end_times(begin, end)
    thumbnail.set_view_rect(Rectangle(0, 0, 6613, 2717))

    os.makedirs("test_outputs", exist_ok=True)
    test_file = "test_outputs/profile_squeeze.mp4"

    proc = psutil.Process(os.getpid())
    n_cpus = psutil.cpu_count()
    samples = []
    stop_monitoring = threading.Event()

    def monitor():
        while not stop_monitoring.is_set():
            try:
                t = time.monotonic()
                main_ct = proc.cpu_times()
                main_threads = proc.num_threads()
                descendants = []
                for c in proc.children(recursive=True):
                    try:
                        descendants.append((c.pid, c.name(), c.cpu_times(), c.num_threads()))
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                samples.append((t, main_ct, main_threads, descendants))
            except psutil.NoSuchProcess:
                break
            time.sleep(0.1)

    t_monitor = threading.Thread(target=monitor, daemon=True)
    t_monitor.start()

    wall_start = time.monotonic()
    cpu_start = proc.cpu_times()

    output = OutputToVideo(test_file, thumbnail.width, thumbnail.height)
    render_video_from_thumbnail(begin, end, output, thumbnail)

    wall = time.monotonic() - wall_start
    cpu_end = proc.cpu_times()
    stop_monitoring.set()
    t_monitor.join()

    main_user = cpu_end.user - cpu_start.user
    main_sys = cpu_end.system - cpu_start.system
    child_user = cpu_end.children_user - cpu_start.children_user
    child_sys = cpu_end.children_system - cpu_start.children_system
    total_cpu = main_user + main_sys + child_user + child_sys

    print("\n=== Profile: 3840x2160 squeeze render, 1-min range (21 frames) ===")
    print(f"Source rect:           6613x2717 -> output {thumbnail.width}x{thumbnail.height}")
    print(f"CPU cores available:   {n_cpus}")
    print(f"Wall clock:            {wall:.2f}s")
    print(f"Main process user:     {main_user:.2f}s")
    print(f"Main process sys:      {main_sys:.2f}s")
    print(f"Children user (sum):   {child_user:.2f}s  (ffmpeg/ffprobe subprocesses)")
    print(f"Children sys (sum):    {child_sys:.2f}s")
    print(f"Total CPU time:        {total_cpu:.2f}s")
    print(f"Average parallelism:   {total_cpu/wall:.2f} cores busy (of {n_cpus})")
    main_cpu = main_user + main_sys
    print(f"Main-thread I/O wait:  ~{max(0, wall - main_cpu):.2f}s "
          f"(wall - main CPU; time main thread wasn't on CPU)")

    if samples:
        main_thread_max = max(s[2] for s in samples)
        max_children = max(len(s[3]) for s in samples)
        print(f"\nMain process max threads:      {main_thread_max}")
        print(f"Max concurrent child processes: {max_children}")

        name_counter = Counter()
        for s in samples:
            for pid, name, ct, nt in s[3]:
                name_counter[name] += 1
        print(f"Child process samples by name: {dict(name_counter)}")

        print("\nTimeline (every ~1s): wall_t  main_cpu%  total_child_cpu%  n_children")
        prev = samples[0]
        last_report = prev[0]
        for s in samples[1:]:
            t, main_ct, main_threads, descendants = s
            if t - last_report < 1.0:
                continue
            dt = t - prev[0]
            dmain = (main_ct.user + main_ct.system) - (prev[1].user + prev[1].system)
            prev_desc_cpu = {pid: ct.user + ct.system for pid, _, ct, _ in prev[3]}
            cur_desc_cpu = {pid: ct.user + ct.system for pid, _, ct, _ in descendants}
            dchild = 0.0
            for pid, cur in cur_desc_cpu.items():
                dchild += cur - prev_desc_cpu.get(pid, 0.0)
            print(f"  t={t-wall_start:5.1f}s  main={100*dmain/dt:5.1f}%  "
                  f"children={100*dchild/dt:6.1f}%  n_children={len(descendants)}")
            prev = s
            last_report = t


if __name__ == "__main__":
    main()
