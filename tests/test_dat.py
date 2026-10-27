import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

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

    def _rclone_copy(source, destination, exclude=None):
        calls.append((str(source), str(destination), exclude))
        # Mimic rclone copying the tree.
        if os.path.isdir(source):
            for root, dirs, files in os.walk(source):
                rel = os.path.relpath(root, source)
                dest_dir = (os.path.join(destination, rel)
                            if rel != "." else destination)
                os.makedirs(dest_dir, exist_ok=True)
                for name in files:
                    if exclude and name == exclude:
                        continue
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

    # The contents of DATA/templates land directly in RUN, not RUN/templates.
    assert (dat.RUN / "input.h5").read_text() == "data"
    assert len(fake_rclone) == 1
    assert str(fake_rclone[0][0]).endswith("templates")
    assert fake_rclone[0][1] == str(dat.RUN)


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
    # Two copies: the data sync, then the final metadata push.
    assert len(fake_rclone) == 2
    assert str(dat.DATA_ROOT) in fake_rclone[0][1]
    # The data sync excludes the running metadata so the archive never holds
    # a stale "running" status.
    assert fake_rclone[0][2] == "metadata.json"
    assert fake_elab[0]["status"] == "finished"
    # DATA receives the final, finished metadata.
    data_record = json.loads((dat.DATA_ROOT / "metadata.json").read_text())
    assert data_record["status"] == "finished"
    assert "finished" in data_record


def test_push_without_commit_sets_finished(sandbox, fake_rclone):
    dat, metadata = sandbox

    dat.push([])

    record = json.loads(metadata.read_text())
    assert record["status"] == "finished"


def test_push_failed_transfer_keeps_running(sandbox, monkeypatch):
    dat, metadata = sandbox
    dat.commit(["-m", "Test run"])
    assert json.loads(metadata.read_text())["status"] == "running"

    def _fail(source, destination, exclude=None):
        raise RuntimeError("transfer failed")

    monkeypatch.setattr(dat, "rclone_copy", _fail)

    with pytest.raises(RuntimeError):
        dat.push([])

    record = json.loads(metadata.read_text())
    assert record["status"] == "running"


def test_pull_rejects_traversal(sandbox, fake_rclone):
    dat, _ = sandbox

    for bad in ["../..", "/etc", "foo/../../bar", "/abs/../x"]:
        with pytest.raises(SystemExit):
            dat.pull([bad])

    assert len(fake_rclone) == 0


def test_rclone_copy_uses_data_safety_flags(sandbox, monkeypatch):
    dat, _ = sandbox
    calls = []

    def _run(cmd, check):
        calls.append(cmd)

    monkeypatch.setattr(subprocess, "run", _run)

    dat.rclone_copy("/src", "/dst")

    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[0] == "rclone"
    assert cmd[1] == "copy"
    assert "--ignore-existing" in cmd
    assert "--immutable" in cmd
    assert cmd[-2:] == ["/src", "/dst"]


def test_unknown_command_exits_2(sandbox, monkeypatch):
    dat, _ = sandbox
    monkeypatch.setattr(sys, "argv", ["dat", "os"])
    with pytest.raises(SystemExit) as excinfo:
        dat.main()
    assert excinfo.value.code == 2


def test_set_status_uses_metadata_extra_fields():
    from dat.journal import get_status, set_status

    entry = create_entry()
    set_status(entry, "running")

    metadata = entry["metadata"]
    # Custom fields live directly under metadata, with elabftw as a sibling.
    assert metadata["extra_fields"]["status"]["value"] == "running"
    assert "extra_fields" not in metadata.get("elabftw", {})
    assert get_status(entry) == "running"


@pytest.fixture()
def elab_http(monkeypatch):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.record_request()
            self.send_response(201)
            self.send_header("Location", "/api/v2/experiments/42")
            self.end_headers()

        def do_PATCH(self):
            self.record_request()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"id": 42}')

        def record_request(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.command, self.path, self.headers, body))

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    monkeypatch.setenv("ELAB_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("ELAB_KEY", "synthetic-api-key")
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield requests
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_elab_create_reads_location_header(elab_http):
    from dat.journal import ElabStorage

    entry = ElabStorage().create()

    assert entry["id"] == 42
    method, path, headers, _ = elab_http[0]
    assert (method, path) == ("POST", "/api/v2/experiments")
    assert headers["Authorization"] == "synthetic-api-key"


def test_elab_save_merges_custom_fields(elab_http):
    from dat.journal import ElabStorage, set_status

    entry = {"id": 42, "title": "Test run"}
    set_status(entry, "running")
    ElabStorage().save(entry)

    method, path, headers, body = elab_http[0]
    assert (method, path) == ("PATCH", "/api/v2/experiments/42")
    assert headers["Authorization"] == "synthetic-api-key"
    assert body["title"] == "Test run"
    assert body["metadatamerge"] == entry["metadata"]
    assert "metadata" not in body


def test_commit_preserves_id_and_metadata_after_failed_save(
        sandbox, fake_elab, monkeypatch):
    dat, metadata = sandbox
    dat.local_storage.save({"title": "Untitled", "metadata": {
        "extra_fields": {"code_revision": {"type": "text", "value": "abc123"}}
    }})
    elab = dat.ElabStorage
    save = elab.save

    def fail_save(self, entry):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(elab, "save", fail_save)
    dat.commit(["-m", "Test run"])

    record = json.loads(metadata.read_text())
    assert record["id"] == 1
    assert record["metadata"]["extra_fields"]["code_revision"]["value"] == "abc123"

    monkeypatch.setattr(elab, "save", save)
    dat.commit(["-m", "Test run"])

    assert len(fake_elab) == 1
    assert fake_elab[0]["id"] == 1
