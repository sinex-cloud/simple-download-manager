import os
import re
import time
import threading
from typing import List, Tuple, Optional
from urllib.parse import urlparse, unquote

import requests

from history import HistoryManager
from metadata import MetadataManager


class DownloadError(Exception):
    pass


class SegmentDownloadThread(threading.Thread):
    """
    Downloads one byte range into its own part file.
    Supports pause, resume, stop/save, and retry.
    """

    def __init__(
        self,
        thread_id: int,
        url: str,
        start_byte: int,
        end_byte: int,
        part_path: str,
        progress_dict: dict,
        progress_lock: threading.Lock,
        stop_event: threading.Event,
        pause_event: threading.Event,
        max_retries: int = 3,
        chunk_size: int = 64 * 1024,
        timeout: int = 15,
    ):
        super().__init__()
        self.thread_id = thread_id
        self.url = url
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.part_path = part_path
        self.progress_dict = progress_dict
        self.progress_lock = progress_lock
        self.stop_event = stop_event
        self.pause_event = pause_event
        self.max_retries = max_retries
        self.chunk_size = chunk_size
        self.timeout = timeout
        self.exception: Optional[Exception] = None

    def run(self):
        retries = 0

        while retries <= self.max_retries and not self.stop_event.is_set():
            try:
                self._download_range()
                return
            except Exception as e:
                retries += 1
                if retries > self.max_retries:
                    self.exception = e
                    return
                time.sleep(1.5 * retries)

    def _download_range(self):
        existing_size = 0
        if os.path.exists(self.part_path):
            existing_size = os.path.getsize(self.part_path)

        total_part_size = self.end_byte - self.start_byte + 1

        if existing_size >= total_part_size:
            with self.progress_lock:
                self.progress_dict[self.thread_id] = total_part_size
            return

        current_start = self.start_byte + existing_size
        headers = {"Range": f"bytes={current_start}-{self.end_byte}"}

        response = requests.get(
            self.url,
            headers=headers,
            stream=True,
            timeout=self.timeout,
            allow_redirects=True,
        )

        try:
            if response.status_code not in (200, 206):
                raise DownloadError(
                    f"Thread {self.thread_id}: unexpected status code {response.status_code}"
                )

            mode = "ab" if existing_size > 0 else "wb"

            with open(self.part_path, mode) as f:
                bytes_written = existing_size

                with self.progress_lock:
                    self.progress_dict[self.thread_id] = bytes_written

                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if self.stop_event.is_set():
                        return

                    while self.pause_event.is_set() and not self.stop_event.is_set():
                        time.sleep(0.2)

                    if self.stop_event.is_set():
                        return

                    if not chunk:
                        continue

                    f.write(chunk)
                    f.flush()

                    chunk_len = len(chunk)
                    bytes_written += chunk_len

                    with self.progress_lock:
                        self.progress_dict[self.thread_id] = bytes_written
        finally:
            response.close()


class SimpleDownloadManager:
    """
    Core segmented downloader with:
    - file info detection
    - range support detection
    - segmented threaded download
    - merge
    - progress display
    - pause / resume / stop-save
    - persistent resume after restart
    - download history
    """

    def __init__(
        self,
        url: str,
        output_dir: str = "downloads",
        num_threads: int = 4,
        max_retries: int = 3,
        temp_dir: str = "temp",
        resume_metadata: Optional[dict] = None,
    ):
        self.url = url.strip()
        self.output_dir = output_dir
        self.num_threads = max(1, num_threads)
        self.max_retries = max(0, max_retries)
        self.temp_dir = temp_dir
        self.resume_metadata = resume_metadata

        self.history_manager = HistoryManager()
        self.metadata_manager = MetadataManager(self.temp_dir)

        self.session = requests.Session()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.progress_lock = threading.Lock()
        self.progress_dict = {}

        self.file_size: Optional[int] = None
        self.file_name: Optional[str] = None
        self.supports_ranges: bool = False

        self.status = "idle"
        self.threads: List[SegmentDownloadThread] = []
        self.part_paths: List[str] = []
        self.ranges: List[Tuple[int, int]] = []

        self.start_time: Optional[float] = None

        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

    def get_file_info(self):
        response = None
        try:
            try:
                response = self.session.head(self.url, allow_redirects=True, timeout=15)
                headers = response.headers
            except requests.RequestException:
                response = self.session.get(
                    self.url,
                    stream=True,
                    allow_redirects=True,
                    timeout=15,
                )
                headers = response.headers

            content_length = headers.get("Content-Length")
            accept_ranges = headers.get("Accept-Ranges", "").lower()
            content_disposition = headers.get("Content-Disposition", "")

            detected_file_size = (
                int(content_length) if content_length and content_length.isdigit() else None
            )
            detected_supports_ranges = "bytes" in accept_ranges
            detected_file_name = self._extract_filename(
                final_url=str(response.url),
                content_disposition=content_disposition,
            )

            if self.resume_metadata:
                self.file_name = self.resume_metadata.get("file_name") or detected_file_name
                self.file_size = self.resume_metadata.get("file_size") or detected_file_size
                self.num_threads = max(
                    1,
                    int(self.resume_metadata.get("num_threads", self.num_threads))
                )
                saved_ranges = self.resume_metadata.get("ranges", [])
                self.ranges = [tuple(r) for r in saved_ranges] if saved_ranges else []
            else:
                self.file_name = detected_file_name
                self.file_size = detected_file_size

            self.supports_ranges = detected_supports_ranges

            if not self.file_name:
                raise DownloadError("Could not determine filename from URL or headers.")
        finally:
            if response is not None:
                response.close()

    def verify_range_support(self):
        test_headers = {"Range": "bytes=0-9"}
        response = None

        try:
            response = self.session.get(
                self.url,
                headers=test_headers,
                stream=True,
                allow_redirects=True,
                timeout=15,
            )
            if response.status_code == 206:
                self.supports_ranges = True
        except requests.RequestException:
            pass
        finally:
            if response is not None:
                response.close()

    def pause(self):
        if self.status == "downloading":
            self.pause_event.set()
            self.status = "paused"
            self._save_metadata(status="paused")
            print("\n[PAUSED] Download paused.")

    def resume(self):
        if self.status == "paused":
            self.pause_event.clear()
            self.status = "downloading"
            self._save_metadata(status="downloading")
            print("\n[RESUMED] Download resumed.")

    def cancel(self):
        """
        Current behavior:
        stop download now, keep progress and metadata for future resume.
        """
        if self.status in ("downloading", "paused"):
            self.stop_event.set()
            self.status = "paused"
            self._save_metadata(status="paused")
            print("\n[STOPPED] Download stopped and saved for future resume.")

    def download(self):
        self.get_file_info()
        self.verify_range_support()

        if self.file_size is None:
            raise DownloadError(
                "Server did not provide Content-Length. This version requires known file size."
            )

        print(f"File name       : {self.file_name}")
        print(f"File size       : {self.file_size} bytes")
        print(f"Range supported : {self.supports_ranges}")

        if not self.supports_ranges:
            print("Server does not support segmented download. Falling back to single-thread.")
            self.num_threads = 1

        if not self.ranges:
            self.ranges = self._split_ranges(self.file_size, self.num_threads)

        self.part_paths = [
            os.path.join(self.temp_dir, f"{self.file_name}.part{i}")
            for i in range(len(self.ranges))
        ]

        self._save_metadata(status="downloading")

        self.progress_dict = {}
        self.threads = []

        for i, ((start_byte, end_byte), part_path) in enumerate(zip(self.ranges, self.part_paths)):
            existing_size = 0
            if os.path.exists(part_path):
                existing_size = os.path.getsize(part_path)

            total_part_size = end_byte - start_byte + 1
            existing_size = min(existing_size, total_part_size)
            self.progress_dict[i] = existing_size

            thread = SegmentDownloadThread(
                thread_id=i,
                url=self.url,
                start_byte=start_byte,
                end_byte=end_byte,
                part_path=part_path,
                progress_dict=self.progress_dict,
                progress_lock=self.progress_lock,
                stop_event=self.stop_event,
                pause_event=self.pause_event,
                max_retries=self.max_retries,
            )
            self.threads.append(thread)

        self.status = "downloading"
        self.start_time = time.time()
        start_time = self.start_time

        for thread in self.threads:
            thread.start()

        try:
            while any(thread.is_alive() for thread in self.threads):
                self._print_progress(start_time)
                time.sleep(0.5)

                if self.stop_event.is_set():
                    break
        except KeyboardInterrupt:
            print("\n[INTERRUPTED] Program interrupted. Partial download kept for future resume.")
            self.status = "paused"
            self.pause_event.set()
            self._save_metadata(status="paused")
            self._log_history_once("paused")

        for thread in self.threads:
            thread.join()

        if self.stop_event.is_set():
            self._save_metadata(status="paused")
            self._log_history_once("paused")
            print("Download stopped. Progress kept for future resume.")
            return

        for thread in self.threads:
            if thread.exception is not None:
                self._save_metadata(status="failed")
                self._log_history_once("failed")
                raise DownloadError(
                    f"Download failed in thread {thread.thread_id}: {thread.exception}"
                )

        self._print_progress(start_time, final=True)

        final_path = os.path.join(self.output_dir, self.file_name)
        self._merge_parts(self.part_paths, final_path)

        merged_size = os.path.getsize(final_path)
        if merged_size != self.file_size:
            self._save_metadata(status="failed")
            self._log_history_once("failed")
            raise DownloadError(
                f"Merged file size mismatch. Expected {self.file_size}, got {merged_size}"
            )

        self._cleanup_files(self.part_paths)
        self.metadata_manager.delete_metadata(self.file_name)

        self._log_history_once("completed")

        self.status = "completed"
        print(f"\nDownload completed successfully: {final_path}")

    def get_progress_snapshot(self):
        with self.progress_lock:
            downloaded = sum(self.progress_dict.values())

        percent = (downloaded / self.file_size * 100) if self.file_size else 0

        if self.start_time is None:
            self.start_time = time.time()

        elapsed = max(time.time() - self.start_time, 0.001)
        speed = downloaded / elapsed
        remaining = max((self.file_size or 0) - downloaded, 0)
        eta = remaining / speed if speed > 0 else 0

        return {
            "status": self.status,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "downloaded": downloaded,
            "percent": percent,
            "speed": speed,
            "eta": eta,
        }

    def _log_history_once(self, status: str):
        entries = self.history_manager.get_all_entries()

        if entries:
            last = entries[-1]
            if (
                last["file_name"] == self.file_name and
                last["status"] == status
            ):
                return

        self.history_manager.add_entry(
            url=self.url,
            file_name=self.file_name,
            file_size=self.file_size,
            num_threads=self.num_threads,
            status=status,
        )

    def _save_metadata(self, status: str):
        metadata = {
            "url": self.url,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "num_threads": self.num_threads,
            "ranges": self.ranges,
            "status": status,
        }
        self.metadata_manager.save_metadata(self.file_name, metadata)

    def _extract_filename(self, final_url: str, content_disposition: str) -> str:
        if "filename=" in content_disposition:
            raw = content_disposition.split("filename=")[-1].strip().strip('"')
            if raw:
                return self._sanitize_filename(raw)

        path = urlparse(final_url).path
        filename = os.path.basename(path)
        filename = unquote(filename)

        if filename:
            return self._sanitize_filename(filename)

        return "downloaded_file"

    def _sanitize_filename(self, filename: str) -> str:
        filename = filename.strip().replace("\x00", "")
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
        return filename or "downloaded_file"

    def _split_ranges(self, file_size: int, num_threads: int) -> List[Tuple[int, int]]:
        if num_threads <= 1 or file_size <= 1:
            return [(0, file_size - 1)]

        ranges = []
        segment_size = file_size // num_threads

        start = 0
        for i in range(num_threads):
            end = start + segment_size - 1
            if i == num_threads - 1:
                end = file_size - 1
            ranges.append((start, end))
            start = end + 1

        return ranges

    def _print_progress(self, start_time: float, final: bool = False):
        with self.progress_lock:
            downloaded = sum(self.progress_dict.values())

        elapsed = max(time.time() - start_time, 0.001)
        speed = downloaded / elapsed
        percent = (downloaded / self.file_size) * 100 if self.file_size else 0

        if final:
            percent = 100.0
            downloaded = self.file_size

        remaining = max(self.file_size - downloaded, 0) if self.file_size else 0
        eta = remaining / speed if speed > 0 else 0

        status_text = self.status.upper()

        print(
            f"\rStatus: {status_text:10} | "
            f"Progress: {percent:6.2f}% | "
            f"Downloaded: {downloaded}/{self.file_size} bytes | "
            f"Speed: {speed/1024:.2f} KB/s | "
            f"ETA: {eta:.1f}s",
            end="",
            flush=True,
        )

    def _merge_parts(self, part_paths: List[str], final_path: str):
        with open(final_path, "wb") as outfile:
            for part_path in part_paths:
                if not os.path.exists(part_path):
                    raise DownloadError(f"Missing part file: {part_path}")

                with open(part_path, "rb") as infile:
                    while True:
                        chunk = infile.read(1024 * 1024)
                        if not chunk:
                            break
                        outfile.write(chunk)

    def _cleanup_files(self, paths: List[str]):
        for path in paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass