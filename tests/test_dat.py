import json
import os
import sys

import pytest

# Point the data directories at sandbox folders before importing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    temp = tmp_path / "temp"
    main = tmp_path / "main"
    archive = tmp_path / "archive"
    temp.mkdir()
    main.mkdir()
    archive.mkdir()
    monkeypatch.setenv("DAT_TEMP", str(temp))
    monkeypatch.setenv("DAT_MAIN", str(main))
    monkeypatch.setenv("DAT_ARCHIVE", str(archive))
    monkeypatch.chdir(tmp_path)
    metadata = tmp_path / "metadata.json"

    import dat.dat as dat
    # Re-read the directory configuration under the patched environment.
    dat.DATA_TEMP = temp
    dat.DATA_MAIN = main
    dat.DATA_ARCHIVE = archive
    dat.local_storage = dat.JSONStorage(metadata)
    return dat, metadata


def test_push_copies_to_main_and_records(sandbox):
    dat, metadata = sandbox
    (dat.DATA_TEMP / "run1").mkdir()
    (dat.DATA_TEMP / "run1" / "out.h5").write_text("data")

    dat.push(["run1"])

    assert (dat.DATA_MAIN / "run1" / "out.h5").read_text() == "data"
    record = json.loads(metadata.read_text())
    assert record["runs"]["run1"]["main"] == str(dat.DATA_MAIN / "run1")
    assert record["runs"]["run1"]["temp"] == str(dat.DATA_TEMP / "run1")


def test_push_refuses_overwrite(sandbox):
    dat, _ = sandbox
    (dat.DATA_TEMP / "run1").mkdir()
    (dat.DATA_MAIN / "run1").mkdir()

    with pytest.raises(FileExistsError):
        dat.push(["run1"])


def test_pull_copies_from_main_to_temp(sandbox):
    dat, metadata = sandbox
    (dat.DATA_MAIN / "run1").mkdir()
    (dat.DATA_MAIN / "run1" / "out.h5").write_text("data")

    dat.pull(["run1"])

    assert (dat.DATA_TEMP / "run1" / "out.h5").read_text() == "data"
    record = json.loads(metadata.read_text())
    assert record["runs"]["run1"]["temp"] == str(dat.DATA_TEMP / "run1")


def test_archive_moves_to_archive_and_records(sandbox):
    dat, metadata = sandbox
    (dat.DATA_MAIN / "run1").mkdir()
    (dat.DATA_MAIN / "run1" / "out.h5").write_text("data")

    dat.archive(["run1"])

    assert not (dat.DATA_MAIN / "run1").exists()
    assert (dat.DATA_ARCHIVE / "run1" / "out.h5").read_text() == "data"
    record = json.loads(metadata.read_text())
    assert record["runs"]["run1"]["archive"] == str(dat.DATA_ARCHIVE / "run1")


def test_archive_refuses_overwrite(sandbox):
    dat, _ = sandbox
    (dat.DATA_MAIN / "run1").mkdir()
    (dat.DATA_ARCHIVE / "run1").mkdir()

    with pytest.raises(FileExistsError):
        dat.archive(["run1"])


@pytest.mark.parametrize("run", ["../escape", "/absolute", "a/b", "..", ".", ".hidden", "a..b"])
def test_run_names_reject_path_traversal(sandbox, run):
    dat, _ = sandbox
    with pytest.raises(SystemExit):
        dat.push([run])
    with pytest.raises(SystemExit):
        dat.pull([run])
    with pytest.raises(SystemExit):
        dat.archive([run])
