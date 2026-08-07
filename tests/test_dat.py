import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dat.journal import create_entry


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    data = tmp_path / "data"
    run = tmp_path / "run"
    data.mkdir()
    run.mkdir()
    monkeypatch.setenv("DAT_DATA", str(data))
    monkeypatch.chdir(run)
    metadata = run / "metadata.json"

    import dat.dat as dat
    # Re-read the configuration under the patched environment.
    dat.RUN = run
    dat.DATA_ROOT = data
    dat.local_storage = dat.JSONStorage(metadata)
    return dat, metadata


@pytest.fixture()
def fake_rclone(sandbox, monkeypatch):
    dat, _ = sandbox
    calls = []

    def _rclone_copy(source, destination):
        calls.append((str(source), str(destination)))
        # Mimic rclone copying the tree.
        if os.path.isdir(source):
            for root, dirs, files in os.walk(source):
                rel = os.path.relpath(root, source)
                dest_dir = (os.path.join(destination, rel)
                            if rel != "." else destination)
                os.makedirs(dest_dir, exist_ok=True)
                for name in files:
                    shutil.copy2(os.path.join(root, name),
                                 os.path.join(dest_dir, name))
        else:
            os.makedirs(destination, exist_ok=True)
            shutil.copy2(source,
                         os.path.join(destination, os.path.basename(source)))

    monkeypatch.setattr(dat, "rclone_copy", _rclone_copy)
    return calls


@pytest.fixture()
def fake_elab(sandbox, monkeypatch):
    dat, _ = sandbox
    created = []

    class FakeElab:
        def __init__(self):
            pass

        def create(self):
            e = create_entry("Untitled")
            e["id"] = len(created) + 1
            created.append(e)
            return e

        def save(self, entry):
            created[entry["id"] - 1] = entry

    monkeypatch.setattr(dat, "ElabStorage", FakeElab)
    return created


def test_pull_copies_data_to_run(sandbox, fake_rclone):
    dat, _ = sandbox
    (dat.DATA_ROOT / "templates").mkdir()
    (dat.DATA_ROOT / "templates" / "input.h5").write_text("data")

    dat.pull(["templates"])

    assert (dat.RUN / "templates" / "input.h5").read_text() == "data"
    assert len(fake_rclone) == 1


def test_pull_requires_path(sandbox):
    dat, _ = sandbox
    with pytest.raises(SystemExit):
        dat.pull([])


def test_commit_records_running_status(sandbox, fake_rclone, fake_elab):
    dat, metadata = sandbox

    dat.commit(["-m", "Test run"])

    record = json.loads(metadata.read_text())
    assert record["title"] == "Test run"
    assert record["status"] == "running"
    assert "started" in record
    assert fake_elab[0]["id"] == 1
    assert fake_elab[0]["status"] == "running"


def test_commit_parses_title_and_body(sandbox, fake_rclone, fake_elab):
    dat, metadata = sandbox

    dat.commit(["-m", "Title here\n\nLonger body text."])

    record = json.loads(metadata.read_text())
    assert record["title"] == "Title here"
    assert record["message"] == "Longer body text."


def test_commit_requires_message_flag(sandbox):
    dat, _ = sandbox
    with pytest.raises(SystemExit):
        dat.commit([])


def test_push_sets_finished_and_syncs(sandbox, fake_rclone, fake_elab):
    dat, metadata = sandbox
    dat.commit(["-m", "Test run"])
    assert json.loads(metadata.read_text())["status"] == "running"

    dat.push([])

    record = json.loads(metadata.read_text())
    assert record["status"] == "finished"
    assert "finished" in record
    # Current run dir synced to DATA.
    assert len(fake_rclone) == 1
    assert str(dat.DATA_ROOT) in fake_rclone[0][1]
    assert fake_elab[0]["status"] == "finished"


def test_push_without_commit_sets_finished(sandbox, fake_rclone):
    dat, metadata = sandbox

    dat.push([])

    record = json.loads(metadata.read_text())
    assert record["status"] == "finished"
