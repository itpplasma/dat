"""
Interface to electronic lab journal https://elabftw.tugraz.at/
See https://alexgu2008.github.io/elabftw_api_support/
"""

import elabapy
import json
import os

STATUS_RUNNING = "running"
STATUS_FINISHED = "finished"

# Automatic metadata fields recorded for every committed run.
AUTO_FIELDS = ("title", "message", "status", "started", "finished")


def create_entry(title="Untitled"):
    entry = {}
    entry["title"] = title
    return entry


def copy_fields(from_entry, to_entry):
    for key in from_entry:
        to_entry[key] = from_entry[key]


def has_title(entry):
    if not "title" in entry:
        return False
    if entry["title"] in ["", "Untitled", None]:
        return False
    return True


def set_field(entry, name, value):
    """Store a field in eLabFTW-standard metadata inside an entry."""
    metadata = entry.setdefault("metadata", {})
    # eLabFTW stores custom fields directly under metadata.extra_fields,
    # with metadata.elabftw as a sibling.
    extra = metadata.setdefault("extra_fields", {})
    extra[name] = {"type": "text", "value": str(value)}
    # Keep a plain copy for quick local access.
    entry[name] = str(value)


def get_field(entry, name):
    """Read a field from eLabFTW-standard metadata (falls back to plain key)."""
    metadata = entry.get("metadata", {})
    extra = metadata.get("extra_fields", {})
    if name in extra:
        return extra[name].get("value")
    return entry.get(name)


def set_status(entry, status):
    set_field(entry, "status", status)


def get_status(entry):
    value = get_field(entry, "status")
    return value


class Storage:
    def load(self, entry):
        pass

    def save(self, entry):
        pass


class ElabStorage(Storage):
    def __init__(self):
        ELAB_URL = os.environ.get("ELAB_URL")
        ELAB_KEY = os.environ.get("ELAB_KEY")
        self.manager = elabapy.Manager(endpoint=ELAB_URL, token=ELAB_KEY)

    def load(self, entry):
        raise NotImplementedError

    def create(self):
        experiment = self.manager.create_experiment()
        if experiment["result"] == "success":
            entry = create_entry("Untitled")
            entry["id"] = experiment["id"]
            return entry
        raise ValueError("Failed to create experiment on eLabFTW server.")

    def save(self, entry):
        if "id" in entry:
            # eLabFTW expects the metadata serialised as a JSON string.
            content = {"title": entry.get("title", "Untitled"),
                       "metadata": json.dumps(entry.get("metadata", {}))}
            self.manager.post_experiment(entry["id"], content)
        else:
            raise ValueError("entry['id'] is empty. Use create().")


class HDF5Storage(Storage):
    def __init__(self, filename):
        self.filename = filename

    def load(self, entry):
        raise NotImplementedError

    def save(self, entry):
        raise NotImplementedError


class JSONStorage(Storage):
    def __init__(self, filename):
        self.filename = filename

    def load(self):
        with open(self.filename, "r") as f:
            return json.load(f)

    def save(self, entry):
        with open(self.filename, "w") as f:
            json.dump(entry, f, indent=2, sort_keys=True)

    def exists(self):
        return os.path.exists(self.filename)
