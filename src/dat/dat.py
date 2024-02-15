import os
import sys

from .journal import create_entry, has_title, JSONStorage

entry = create_entry()
local_storage = JSONStorage("metadata.json")

def main():
    print("This is Dat.")
    command = get_function_by_name(sys.argv[1])
    command(sys.argv[2:])


def get_function_by_name(name):
    return globals()[name]


def commit(args):
    global entry

    if local_storage.exists():
        entry = local_storage.load()
    if not has_title(entry):
        entry["title"] = input("Title: ")

    print("Committing changes to {local_storage.filename}...")
    local_storage.save(entry)

    print("Committing changes to eLabFTW...")

    print("Changes committed.")


if __name__ == "__main__":
    main()
