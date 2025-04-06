import json
import os
import subprocess
from datetime import datetime
from deepdiff import DeepDiff
from git import Repo, GitCommandError

class NetworkVersionizer:
    def save_snapshots_per_server_with_diff(self, data_list, repo_path="/home/snastya/mag_vkr/network_collector/snapshots"):
        os.makedirs(repo_path, exist_ok=True)
        repo = Repo(repo_path)
        changed_files = []

        for device_data in data_list:
            name = device_data["device"]["name"]
            del device_data["timestamp"]
            filename = f"{name}.json"
            filepath = os.path.join(repo_path, filename)

            # Загружаем предыдущее состояние (если есть)
            previous_data = None
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    try:
                        previous_data = json.load(f)
                    except Exception:
                        pass

            # Сравниваем с новым
            diff = DeepDiff(previous_data or {}, device_data, ignore_order=True)

            if not diff:
                print(f"[=] {filename}: нет изменений — пропускаем")
                continue

            # Сохраняем новый снимок
            with open(filepath, "w") as f:
                json.dump(device_data, f, indent=2, ensure_ascii=False)
            changed_files.append(filepath)
            print(f"Обновлено: {filename}")
            print(f"Различия:\n{diff.to_json(indent=2)}")

        if not changed_files:
            print("[i] Нет изменений для коммита.")
            return

        # Git commit
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        repo.index.add(changed_files)

        try:
            repo.index.commit(f"Снимки конфигураций обновлены: {now}")
#            origin = repo.remote(name='origin')
#            origin.push()
            print("[✓] Git commit выполнен.")
        except GitCommandError as e:
            print(f"[!] Ошибка Git: {e}")