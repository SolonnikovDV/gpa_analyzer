from __future__ import annotations

import os

from .job_store import FileJobStore, SQLiteJobStore
from .runtime_preset_store import FileRuntimePresetStore, SQLiteRuntimePresetStore


class PersistenceService:
    def __init__(self, root_dir: str, db_path: str) -> None:
        self.root_dir = root_dir
        os.makedirs(root_dir, exist_ok=True)
        self.db_path = db_path
        self.job_store = SQLiteJobStore(db_path)
        self.runtime_preset_store = SQLiteRuntimePresetStore(db_path)
        self._migrate_legacy_file_state()

    def _migrate_legacy_file_state(self) -> None:
        legacy_job_store = FileJobStore(os.path.join(self.root_dir, "jobs_state"))
        if not self.job_store.load_jobs():
            for job_id, payload in legacy_job_store.load_jobs().items():
                self.job_store.save_job(job_id, payload)
                for line in legacy_job_store.read_logs(job_id):
                    self.job_store.append_log(job_id, line)

        legacy_preset_store = FileRuntimePresetStore(os.path.join(self.root_dir, "presets"))
        if not self.runtime_preset_store.list_presets():
            for record in legacy_preset_store.list_presets():
                self.runtime_preset_store.upsert_preset(
                    str(record.get("stack") or ""),
                    str(record.get("kind") or ""),
                    str(record.get("name") or ""),
                    str(record.get("value") or ""),
                )


FilePersistenceService = PersistenceService
