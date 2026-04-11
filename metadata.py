import json
import os


class MetadataManager:
    def __init__(self, temp_dir="temp"):
        self.temp_dir = temp_dir
        os.makedirs(self.temp_dir, exist_ok=True)

    def _get_metadata_path(self, file_name: str) -> str:
        # Ensure safe filename
        safe_name = file_name.replace("/", "_").replace("\\", "_")
        return os.path.join(self.temp_dir, f"{safe_name}.json")

    def save_metadata(self, file_name: str, data: dict):
        path = self._get_metadata_path(file_name)

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[Metadata ERROR] Failed to save metadata: {e}")

    def load_metadata(self, file_name: str) -> dict:
        path = self._get_metadata_path(file_name)

        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"[Metadata WARNING] Corrupted metadata file: {path}")
            return None
        except Exception as e:
            print(f"[Metadata ERROR] Failed to load metadata: {e}")
            return None

    def delete_metadata(self, file_name: str):
        path = self._get_metadata_path(file_name)

        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            print(f"[Metadata ERROR] Failed to delete metadata: {e}")

    def list_all_metadata(self):
        try:
            files = os.listdir(self.temp_dir)
            return [f for f in files if f.endswith(".json")]
        except Exception as e:
            print(f"[Metadata ERROR] Failed to list metadata: {e}")
            return []