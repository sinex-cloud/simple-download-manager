import threading

from downloader import SimpleDownloadManager, DownloadError
from metadata import MetadataManager


def choose_resume(metadata_manager: MetadataManager):
    files = metadata_manager.list_all_metadata()

    if not files:
        return None

    print("\nFound unfinished downloads:")
    for i, f in enumerate(files, start=1):
        print(f"{i}. {f}")

    choice = input("Resume one? (enter number or press Enter to skip): ").strip()

    if not choice:
        return None

    try:
        index = int(choice) - 1
        if index < 0 or index >= len(files):
            return None

        file_name = files[index].replace(".json", "")
        return metadata_manager.load_metadata(file_name)
    except Exception:
        return None


def command_listener(manager: SimpleDownloadManager):
    while manager.status not in ("completed",):
        try:
            cmd = input("\nCommand [p=pause, r=resume, c=stop & save]: ").strip().lower()

            if cmd == "p":
                manager.pause()
            elif cmd == "r":
                manager.resume()
            elif cmd == "c":
                manager.cancel()
                break
        except EOFError:
            break
        except KeyboardInterrupt:
            break


def run_download(manager: SimpleDownloadManager):
    try:
        manager.download()
    except DownloadError as e:
        print(f"\nERROR: {e}")
    except Exception as e:
        print(f"\nUnexpected error: {e}")


def main():
    print("=== Simple Download Manager - Persistent Version ===")

    metadata_manager = MetadataManager("temp")
    resume_metadata = choose_resume(metadata_manager)

    if resume_metadata:
        print("\nResuming previous download...")

        manager = SimpleDownloadManager(
            url=resume_metadata["url"],
            output_dir="downloads",
            num_threads=resume_metadata["num_threads"],
            max_retries=3,
            temp_dir="temp",
            resume_metadata=resume_metadata,
        )
    else:
        url = input("Enter file URL: ").strip()

        if not url:
            print("URL cannot be empty.")
            return

        try:
            threads_input = input("Enter number of threads (default 4): ").strip()
            num_threads = int(threads_input) if threads_input else 4
        except ValueError:
            print("Invalid number. Using default 4 threads.")
            num_threads = 4

        manager = SimpleDownloadManager(
            url=url,
            output_dir="downloads",
            num_threads=num_threads,
            max_retries=3,
            temp_dir="temp",
        )

    download_thread = threading.Thread(target=run_download, args=(manager,))
    download_thread.start()

    listener_thread = threading.Thread(
        target=command_listener,
        args=(manager,),
        daemon=True,
    )
    listener_thread.start()

    download_thread.join()

    if manager.status == "completed":
        print("\nFinished.")
    elif manager.status == "paused":
        print("\nStopped and kept for future resume.")


if __name__ == "__main__":
    main()