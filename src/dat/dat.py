import os
import shutil
import sys

from .journal import create_entry, has_title, JSONStorage

# Data directories. Defaults match the ITPcp layout; override via environment
# variables when working elsewhere (e.g. Nextcloud shares).
DATA_TEMP = os.environ.get("DAT_TEMP", "/temp")
DATA_MAIN = os.environ.get("DAT_MAIN", "/proj/plasma")
DATA_ARCHIVE = os.environ.get("DAT_ARCHIVE", "/proj/plasma/archive")

entry = create_entry()
local_storage = JSONStorage("metadata.json")


def main():
    print("This is Dat.")
    if len(sys.argv) < 2:
        print("Usage: dat <command> [args]")
        print("Commands: commit, push, pull, archive")
        sys.exit(1)
    command = get_function_by_name(sys.argv[1])
    command(sys.argv[2:])


def get_function_by_name(name):
    try:
        return globals()[name]
    except KeyError:
        raise SystemExit(f"Unknown command: {name}")


def commit(args):
    global entry

    if local_storage.exists():
        entry = local_storage.load()
    if not has_title(entry):
        entry["title"] = input("Title: ")

    print(f"Committing changes to {local_storage.filename}...")
    local_storage.save(entry)

    print("Committing changes to eLabFTW...")

    print("Changes committed.")


def push(args):
    if not args:
        raise SystemExit("Usage: dat push <run>")
    run = args[0]
    src = os.path.join(DATA_TEMP, run)
    dst = os.path.join(DATA_MAIN, run)
    if not os.path.exists(src):
        raise SystemExit(f"Temporary run {src} not found.")
    print(f"Pushing {run} from {DATA_TEMP} to {DATA_MAIN}...")
    copy_tree(src, dst)
    record_run(run, temp=src, main=dst)
    print("Pushed.")


def pull(args):
    if not args:
        raise SystemExit("Usage: dat pull <run>")
    run = args[0]
    src = os.path.join(DATA_MAIN, run)
    dst = os.path.join(DATA_TEMP, run)
    if not os.path.exists(src):
        raise SystemExit(f"Main run {src} not found.")
    print(f"Pulling {run} from {DATA_MAIN} to {DATA_TEMP}...")
    copy_tree(src, dst)
    record_run(run, temp=dst, main=src)
    print("Pulled.")


def archive(args):
    if not args:
        raise SystemExit("Usage: dat archive <run>")
    run = args[0]
    src = os.path.join(DATA_MAIN, run)
    dst = os.path.join(DATA_ARCHIVE, run)
    if not os.path.exists(src):
        raise SystemExit(f"Main run {src} not found.")
    os.makedirs(DATA_ARCHIVE, exist_ok=True)
    print(f"Archiving {run} from {DATA_MAIN} to {DATA_ARCHIVE}...")
    move(src, dst)
    record_run(run, archive=dst)
    print("Archived.")


def copy_tree(src, dst):
    """Copy a directory tree, refusing to write over existing files."""
    if os.path.exists(dst):
        raise FileExistsError(
            f"Destination {dst} already exists; refusing to overwrite.")
    shutil.copytree(src, dst)


def move(src, dst):
    """Move a path, refusing to write over existing files."""
    if os.path.exists(dst):
        raise FileExistsError(
            f"Destination {dst} already exists; refusing to overwrite.")
    shutil.move(src, dst)


def record_run(run, **locations):
    """Update the metadata record with run locations."""
    entry = local_storage.load() if local_storage.exists() else create_entry()
    runs = entry.setdefault("runs", {})
    run_record = runs.setdefault(run, {})
    if "archive" in locations:
        # Once archived the run leaves the main directory.
        run_record["main"] = locations["main"] if "main" in locations else run_record.get("main")
        run_record["archive"] = locations["archive"]
    else:
        run_record.update(locations)
    local_storage.save(entry)


if __name__ == "__main__":
    main()
