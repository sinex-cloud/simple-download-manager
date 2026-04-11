import json
import os
from datetime import datetime


class HistoryManager:
    def __init__(self, history_file="download_history.json"):
        self.history_file = history_file

        if not os.path.exists(self.history_file):
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump([], f, indent=4)

    def _load_history(self):
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            print("[History WARNING] Corrupted or missing history file. Resetting...")
            return []

    def _save_history(self, history):
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=4)
        except Exception as e:
            print(f"[History ERROR] Failed to save history: {e}")

    def add_entry(
        self,
        url,
        file_name,
        file_size,
        num_threads,
        status,
    ):
        history = self._load_history()

        # ✅ Prevent duplicate consecutive entries
        if history:
            last = history[-1]
            if (
                last["file_name"] == file_name and
                last["status"] == status
            ):
                return

        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url": url,
            "file_name": file_name,
            "file_size": file_size,
            "num_threads": num_threads,
            "status": status,
        }

        history.append(entry)

        # ✅ Keep history size reasonable (last 100 entries)
        if len(history) > 100:
            history = history[-100:]

        self._save_history(history)

    def get_all_entries(self):
        history = self._load_history()

        # ✅ Always return newest first
        return list(reversed(history))

    def clear_history(self):
        self._save_history([])

    def print_history(self):
        history = self.get_all_entries()

        if not history:
            print("\nNo download history found.")
            return

        print("\n=== Download History ===")
        for i, entry in enumerate(history, start=1):
            print(f"\n{i}. [{entry['timestamp']}]")
            print(f"   File       : {entry['file_name']}")
            print(f"   Status     : {entry['status']}")
            print(f"   Size       : {entry['file_size']} bytes")
            print(f"   Threads    : {entry['num_threads']}")
            print(f"   URL        : {entry['url']}")