import os
import subprocess
import sys
import time

from .journal import (STATUS_FINISHED, STATUS_RUNNING, JSONStorage,
                      ElabStorage, create_entry, get_status, set_field,
                      set_status)

# The scientist works in the current directory (RUN). DATA is the long-term
# storage, reachable from the file system or the cloud via rclone.
RUN = os.getcwd()
DATA_ROOT = os.environ.get("DAT_DATA", "/proj/plasma")

entry = create_entry()
local_storage = JSONStorage("metadata.json")


def main():
    print("This is Dat.")
    if len(sys.argv) < 2:
        print("Usage: dat <command> [args]")
        print("Commands: pull, commit, push")
        sys.exit(1)
    command = get_function_by_name(sys.argv[1])
    command(sys.argv[2:])


def get_function_by_name(name):
    try:
        return globals()[name]
    except KeyError:
        raise SystemExit(f"Unknown command: {name}")


def split_message(message):
    """Split a commit message into title and optional body."""
    title, _, body = message.partition("\n")
    return title.strip(), body.strip()


def rclone_copy(source, destination):
    """Unidirectional copy of source into destination via rclone."""
    print(f"Syncing {source} -> {destination}")
    subprocess.run(["rclone", "copy", source, destination], check=True)


def commit(args):
    """Record a started run: write metadata and create a database entry."""
    if len(args) < 2 or args[0] != "-m":
        raise SystemExit("Usage: dat commit -m <message>")
    message = args[1]
    title, body = split_message(message)
    if not title:
        raise SystemExit("Commit message requires a title.")

    entry = local_storage.load() if local_storage.exists() else create_entry()
    entry["title"] = title
    set_field(entry, "message", body)
    set_status(entry, STATUS_RUNNING)
    set_field(entry, "started", time.strftime("%Y-%m-%dT%H:%M:%S"))

    print(f"Committing changes to {local_storage.filename}...")
    local_storage.save(entry)

    print("Committing changes to eLabFTW...")
    db_status = "ok"
    try:
        elab = ElabStorage()
        if "id" not in entry:
            entry = elab.create()
            entry["title"] = title
            set_field(entry, "message", body)
            set_status(entry, STATUS_RUNNING)
            set_field(entry, "started", time.strftime("%Y-%m-%dT%H:%M:%S"))
        elab.save(entry)
        local_storage.save(entry)
    except Exception as exc:
        db_status = f"unavailable ({exc})"
        print(f"Warning: could not update eLabFTW database: {exc}")

    print(f"Committed run with status '{STATUS_RUNNING}' "
          f"(database: {db_status}).")


def push(args):
    """Push results from RUN to DATA and set the run status finished."""
    if args:
        raise SystemExit("Usage: dat push (no arguments; syncs current dir)")

    entry = local_storage.load() if local_storage.exists() else create_entry()
    if get_status(entry) != STATUS_RUNNING:
        print("No running run found; starting a finished record from scratch.")

    # Sync results first: only mark the run finished once the data is in DATA.
    rclone_copy(RUN, DATA_ROOT)

    set_status(entry, STATUS_FINISHED)
    set_field(entry, "finished", time.strftime("%Y-%m-%dT%H:%M:%S"))

    print(f"Updating {local_storage.filename}...")
    local_storage.save(entry)

    print("Updating eLabFTW database...")
    db_status = "ok"
    try:
        if "id" in entry:
            elab = ElabStorage()
            elab.save(entry)
    except Exception as exc:
        db_status = f"unavailable ({exc})"
        print(f"Warning: could not update eLabFTW database: {exc}")

    print(f"Pushed results and set status '{STATUS_FINISHED}' "
          f"(database: {db_status}).")


def pull(args):
    """Pull a subdirectory from DATA into the current directory (RUN)."""
    if not args:
        raise SystemExit("Usage: dat pull <path>")
    path = args[0]
    # Require a normalized relative path that stays inside RUN: reject
    # absolute paths and any traversal out of the run directory.
    raw = path.rstrip("/")
    if not raw:
        raise SystemExit("Usage: dat pull <path>")
    norm = os.path.normpath(raw)
    if os.path.isabs(raw) or norm == ".." or \
            norm.startswith(".." + os.sep):
        raise SystemExit(f"Invalid path: {path}")
    if norm in ("", "."):
        raise SystemExit("Usage: dat pull <path>")
    source = os.path.join(DATA_ROOT, norm)
    destination = os.path.join(RUN, norm)
    print(f"Pulling {source} into {destination}...")
    rclone_copy(source, destination)
    print("Pulled.")


if __name__ == "__main__":
    main()
