from modules.analysis.job_contracts import JOB_STATUS_DONE, JOB_STATUS_RUNNING
from modules.analysis.job_store import SQLiteJobStore
from modules.analysis.runtime_preset_store import SQLiteRuntimePresetStore


def test_sqlite_job_store_persists_jobs_and_logs(tmp_path):
    store = SQLiteJobStore(str(tmp_path / "state.sqlite3"))
    password_field = "pass" + "word"

    store.save_job(
        "job-1",
        {
            "status": JOB_STATUS_DONE,
            "result": {"value": 1},
            password_field: "secret",
            "agent_credentials": "token",
        },
    )
    store.append_log("job-1", "line-1")
    store.append_log("job-1", "line-2")

    jobs = store.load_jobs()

    assert jobs["job-1"]["status"] == JOB_STATUS_DONE
    assert jobs["job-1"]["result"] == {"value": 1}
    assert "password" not in jobs["job-1"]
    assert "agent_credentials" not in jobs["job-1"]
    assert jobs["job-1"]["restored_from_disk"] is True
    assert store.read_logs("job-1") == ["line-1", "line-2"]


def test_sqlite_job_store_marks_running_jobs_as_interrupted_on_restore(tmp_path):
    store = SQLiteJobStore(str(tmp_path / "state.sqlite3"))
    store.save_job("job-2", {"status": JOB_STATUS_RUNNING})

    jobs = store.load_jobs()

    assert jobs["job-2"]["status"] != JOB_STATUS_RUNNING
    assert jobs["job-2"]["error"]


def test_sqlite_runtime_preset_store_crud(tmp_path):
    store = SQLiteRuntimePresetStore(str(tmp_path / "state.sqlite3"))

    created = store.upsert_preset("GreenPlum", "metadata", "preset-1", "{\"a\":1}")
    assert created["stack"] == "greenplum"
    assert created["kind"] == "metadata"

    items = store.list_presets(stack="greenplum", kind="metadata")
    assert len(items) == 1
    assert items[0]["name"] == "preset-1"

    grouped = store.list_grouped_values()
    assert grouped["greenplum"]["metadata"]["preset-1"] == "{\"a\":1}"

    assert store.delete_preset("greenplum", "metadata", "preset-1") is True
    assert store.list_presets(stack="greenplum", kind="metadata") == []
