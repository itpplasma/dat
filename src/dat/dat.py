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


def pull(args):
    """Pull a subdirectory from DATA into the current directory (RUN)."""
    if not args:
        raise SystemExit("Usage: dat pull <path>")
    path = args[0]
    # Require a normalized relative path that stays inside DATA: reject
    # absolute paths and any traversal out of the DATA root.
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
    print(f"Pulling {source} into {RUN}...")
    rclone_copy(source, RUN)
    print("Pulled.")


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

    # Sync results to DATA first while the run is still marked running, so a
    # failed transfer leaves the run state consistent and a retry still sees
    # a running run. Only mark the run finished after the transfer succeeds.
    # The managed metadata file is excluded here because it still holds the
    # running status; the final, finished metadata is pushed separately below.
    rclone_copy(RUN, DATA_ROOT, exclude="metadata.json")

    # Mark the run finished and persist the final metadata.
    set_status(entry, STATUS_FINISHED)
    set_field(entry, "finished", time.strftime("%Y-%m-%dT%H:%M:%S"))

    print(f"Updating {local_storage.filename}...")
    local_storage.save(entry)

    # Push the final (finished) metadata to DATA so the archived record does
    # not permanently report a running status. A failure here leaves the local
    # metadata finished and DATA without (or with stale) metadata; a retry of
    # push simply re-syncs the finished metadata.
    rclone_copy(local_storage.filename, DATA_ROOT)

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


def split_message(message):
    """Split a commit message into title and optional body."""
    title, _, body = message.partition("\n")
    return title.strip(), body.strip()


def rclone_copy(source, destination, exclude=None):
    """Unidirectional copy of source into destination via rclone.

    Data-safety flags: --ignore-existing prevents overwriting files that are
    already present and --immutable refuses to modify existing remote files.
    """
    print(f"Syncing {source} -> {destination}")
    cmd = ["rclone", "copy", "--ignore-existing", "--immutable"]
    if exclude:
        cmd += ["--exclude", exclude]
    cmd += [source, destination]
    subprocess.run(cmd, check=True)


def main():
    print("This is Dat.")
    if len(sys.argv) < 2:
        print("Usage: dat <command> [args]")
        print("Commands: pull, commit, push")
        sys.exit(1)
    command_name = sys.argv[1]
    command = COMMANDS.get(command_name)
    if command is None:
        print(f"Unknown command: {command_name}", file=sys.stderr)
        sys.exit(2)
    command(sys.argv[2:])


COMMANDS = {
    "pull": pull,
    "commit": commit,
    "push": push,
}


if __name__ == "__main__":
    main()
