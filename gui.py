import threading
import tkinter as tk
from tkinter import ttk, messagebox

from downloader import SimpleDownloadManager, DownloadError
from metadata import MetadataManager
from history import HistoryManager


class DownloadManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Download Manager")
        self.root.geometry("900x620")
        self.root.resizable(False, False)

        self.manager = None
        self.download_thread = None
        self.metadata_manager = MetadataManager("temp")
        self.history_manager = HistoryManager()

        self._build_ui()
        self.update_button_states("idle")
        self._check_unfinished_downloads()
        self.show_history()
        self._refresh_ui()

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=15)
        main.pack(fill="both", expand=True)

        title = ttk.Label(
            main,
            text="Simple Download Manager",
            font=("Segoe UI", 16, "bold")
        )
        title.pack(anchor="w", pady=(0, 15))

        ttk.Label(main, text="File URL:").pack(anchor="w")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(main, textvariable=self.url_var, width=110)
        self.url_entry.pack(fill="x", pady=(0, 10))

        thread_frame = ttk.Frame(main)
        thread_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(thread_frame, text="Threads:").pack(side="left")
        self.threads_var = tk.StringVar(value="4")
        self.threads_spin = ttk.Spinbox(
            thread_frame,
            from_=1,
            to=8,
            textvariable=self.threads_var,
            width=8
        )
        self.threads_spin.pack(side="left", padx=(8, 0))

        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=(0, 15))

        self.start_btn = ttk.Button(
            btn_frame,
            text="Start Download",
            command=self.start_download
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        self.pause_btn = ttk.Button(
            btn_frame,
            text="Pause",
            command=self.pause_download
        )
        self.pause_btn.pack(side="left", padx=(0, 8))

        self.resume_btn = ttk.Button(
            btn_frame,
            text="Resume",
            command=self.resume_download
        )
        self.resume_btn.pack(side="left", padx=(0, 8))

        self.stop_btn = ttk.Button(
            btn_frame,
            text="Stop & Save",
            command=self.stop_download
        )
        self.stop_btn.pack(side="left", padx=(0, 8))

        self.show_history_btn = ttk.Button(
            btn_frame,
            text="Refresh History",
            command=self.show_history
        )
        self.show_history_btn.pack(side="left")

        info_frame = ttk.LabelFrame(main, text="Current Download", padding=12)
        info_frame.pack(fill="x", pady=(0, 15))

        self.status_var = tk.StringVar(value="Idle")
        self.file_var = tk.StringVar(value="-")
        self.progress_var = tk.StringVar(value="0 / 0 bytes")
        self.percent_var = tk.StringVar(value="0.00%")
        self.speed_var = tk.StringVar(value="0 KB/s")
        self.eta_var = tk.StringVar(value="0 s")

        ttk.Label(info_frame, text="Status:").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Label(info_frame, textvariable=self.status_var).grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(info_frame, text="File:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Label(info_frame, textvariable=self.file_var).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(info_frame, text="Progress:").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Label(info_frame, textvariable=self.progress_var).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(info_frame, text="Percent:").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Label(info_frame, textvariable=self.percent_var).grid(row=3, column=1, sticky="w", pady=4)

        ttk.Label(info_frame, text="Speed:").grid(row=4, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Label(info_frame, textvariable=self.speed_var).grid(row=4, column=1, sticky="w", pady=4)

        ttk.Label(info_frame, text="ETA:").grid(row=5, column=0, sticky="w", padx=(0, 10), pady=4)
        ttk.Label(info_frame, textvariable=self.eta_var).grid(row=5, column=1, sticky="w", pady=4)

        self.progressbar = ttk.Progressbar(
            main,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            length=850
        )
        self.progressbar.pack(fill="x", pady=(0, 15))

        history_frame = ttk.LabelFrame(main, text="History", padding=12)
        history_frame.pack(fill="both", expand=True)

        columns = ("id", "file", "status", "size", "threads", "timestamp")

        self.history_table = ttk.Treeview(
            history_frame,
            columns=columns,
            show="headings",
            height=12
        )
        self.history_table.tag_configure("completed", foreground="green")
        self.history_table.tag_configure("paused", foreground="orange")
        self.history_table.tag_configure("failed", foreground="red")
        self.history_table.heading("id", text="#")
        self.history_table.heading("file", text="File")
        self.history_table.heading("status", text="Status")
        self.history_table.heading("size", text="Size")
        self.history_table.heading("threads", text="Threads")
        self.history_table.heading("timestamp", text="Timestamp")

        self.history_table.column("id", width=40, anchor="center")
        self.history_table.column("file", width=240, anchor="w")
        self.history_table.column("status", width=100, anchor="center")
        self.history_table.column("size", width=120, anchor="center")
        self.history_table.column("threads", width=70, anchor="center")
        self.history_table.column("timestamp", width=180, anchor="center")

        self.history_table.bind("<Double-1>", self.on_history_double_click)

        scrollbar = ttk.Scrollbar(
            history_frame,
            orient="vertical",
            command=self.history_table.yview
        )
        self.history_table.configure(yscrollcommand=scrollbar.set)

        self.history_table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def update_button_states(self, status):
        status = (status or "idle").lower()

        if status == "downloading":
            self.start_btn.config(state="disabled")
            self.pause_btn.config(state="normal")
            self.resume_btn.config(state="disabled")
            self.stop_btn.config(state="normal")

        elif status == "paused":
            self.start_btn.config(state="normal")
            self.pause_btn.config(state="disabled")
            self.resume_btn.config(state="normal")
            self.stop_btn.config(state="normal")

        elif status == "completed":
            self.start_btn.config(state="normal")
            self.pause_btn.config(state="disabled")
            self.resume_btn.config(state="disabled")
            self.stop_btn.config(state="disabled")

        elif status == "failed":
            self.start_btn.config(state="normal")
            self.pause_btn.config(state="disabled")
            self.resume_btn.config(state="disabled")
            self.stop_btn.config(state="disabled")

        else:  # idle and any fallback state
            self.start_btn.config(state="normal")
            self.pause_btn.config(state="disabled")
            self.resume_btn.config(state="disabled")
            self.stop_btn.config(state="disabled")

    def on_history_double_click(self, event):
        selected = self.history_table.selection()

        if not selected:
            return

        item = self.history_table.item(selected[0])
        values = item["values"]

        index = values[0] - 1  # row index
        entry = self.current_history[index]

        # Fill URL + threads
        self.url_var.set(entry["url"])
        self.threads_var.set(str(entry["num_threads"]))

    def format_speed(self, speed_bytes_per_sec):
        if speed_bytes_per_sec < 1024:
            return f"{speed_bytes_per_sec:.0f} B/s"
        elif speed_bytes_per_sec < 1024 * 1024:
            return f"{speed_bytes_per_sec / 1024:.2f} KB/s"
        elif speed_bytes_per_sec < 1024 * 1024 * 1024:
            return f"{speed_bytes_per_sec / (1024 * 1024):.2f} MB/s"
        else:
            return f"{speed_bytes_per_sec / (1024 * 1024 * 1024):.2f} GB/s"

    def format_eta(self, eta_seconds):
        if eta_seconds <= 0:
            return "0 s"

        eta_seconds = int(eta_seconds)

        hours = eta_seconds // 3600
        minutes = (eta_seconds % 3600) // 60
        seconds = eta_seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def format_size(self, size_bytes):
        if size_bytes is None:
            return "-"

        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def _check_unfinished_downloads(self):
        files = self.metadata_manager.list_all_metadata()
        if not files:
            return

        first_file = files[0]
        file_name = first_file.replace(".json", "")
        metadata = self.metadata_manager.load_metadata(file_name)

        if not metadata:
            return

        answer = messagebox.askyesno(
            "Resume Download",
            f"Unfinished download found:\n\n{metadata['file_name']}\n\nDo you want to resume it?"
        )

        if answer:
            self.manager = SimpleDownloadManager(
                url=metadata["url"],
                output_dir="downloads",
                num_threads=metadata["num_threads"],
                max_retries=3,
                temp_dir="temp",
                resume_metadata=metadata,
            )
            self.url_var.set(metadata["url"])
            self.threads_var.set(str(metadata["num_threads"]))
            self.start_download(resume_mode=True)

    def start_download(self, resume_mode=False):
        if self.download_thread and self.download_thread.is_alive():
            messagebox.showwarning("Warning", "A download is already running.")
            return

        if not resume_mode:
            url = self.url_var.get().strip()
            if not url:
                messagebox.showerror("Error", "Please enter a file URL.")
                return

            try:
                num_threads = int(self.threads_var.get())
            except ValueError:
                messagebox.showerror("Error", "Invalid thread count.")
                return

            self.manager = SimpleDownloadManager(
                url=url,
                output_dir="downloads",
                num_threads=num_threads,
                max_retries=3,
                temp_dir="temp",
            )

        self.download_thread = threading.Thread(target=self._run_download, daemon=True)
        self.download_thread.start()

    def _run_download(self):
        try:
            self.manager.download()
            self.root.after(0, self.show_history)

            if self.manager.status == "completed":
                self.root.after(
                    0,
                    lambda: messagebox.showinfo("Success", "Download completed successfully.")
                )
        except DownloadError as e:
            self.root.after(0, lambda: messagebox.showerror("Download Error", str(e)))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Unexpected Error", str(e)))

    def pause_download(self):
        if self.manager:
            self.manager.pause()

    def resume_download(self):
        if self.manager:
            self.manager.resume()

    def stop_download(self):
        if self.manager:
            self.manager.cancel()

    def show_history(self):
        entries = self.history_manager.get_all_entries()
        self.current_history = entries

        for row in self.history_table.get_children():
            self.history_table.delete(row)

        if not entries:
            return

        for i, entry in enumerate(entries, start=1):
            status = entry["status"]

            self.history_table.insert(
                "",
                "end",
                values=(
                    i,
                    entry["file_name"],
                    status,
                    self.format_size(entry["file_size"]),
                    entry["num_threads"],
                    entry["timestamp"],
                ),
                tags=(status,) 
            )

    def _refresh_ui(self):
        if self.manager:
            snapshot = self.manager.get_progress_snapshot()

            self.update_button_states(snapshot["status"])

            self.status_var.set(snapshot["status"].capitalize() if snapshot["status"] else "Idle")
            self.file_var.set(snapshot["file_name"] or "-")
            self.progress_var.set(
                f"{self.format_size(snapshot['downloaded'])} / {self.format_size(snapshot['file_size'])}"
            )
            self.percent_var.set(f"{snapshot['percent']:.2f}%")

            if snapshot["status"] == "completed":
                self.speed_var.set("-")
                self.eta_var.set("0 s")
                self.progressbar["value"] = 100
            else:
                self.speed_var.set(self.format_speed(snapshot["speed"]))
                self.eta_var.set(self.format_eta(snapshot["eta"]))
                self.progressbar["value"] = snapshot["percent"]
        else:
            self.update_button_states("idle")

        self.root.after(500, self._refresh_ui)


def main():
    root = tk.Tk()
    app = DownloadManagerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()