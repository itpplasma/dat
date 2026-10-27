"""
Interface to electronic lab journal https://elabftw.tugraz.at/
Uses the official eLabFTW API v2 client (elabapi-python).
"""

import json
import os

import elabapi_python

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
        if not ELAB_URL or not ELAB_KEY:
            raise ValueError("ELAB_URL and ELAB_KEY must be set.")
        configuration = elabapi_python.Configuration()
        configuration.host = ELAB_URL.rstrip("/") + "/api/v2"
        configuration.api_key["Authorization"] = ELAB_KEY
        self.experiments = elabapi_python.ExperimentsApi(
            elabapi_python.ApiClient(configuration))

    def load(self, entry):
        raise NotImplementedError

    def create(self):
        _, _, headers = self.experiments.post_experiment_with_http_info(
            body={"title": "Untitled"})
        entry = create_entry("Untitled")
        entry["id"] = int(headers["Location"].rstrip("/").rsplit("/", 1)[-1])
        return entry

    def save(self, entry):
        if "id" in entry:
            # Merge custom fields without replacing server-managed metadata.
            body = {"title": entry.get("title", "Untitled"),
                    "metadatamerge": entry.get("metadata", {})}
            self.experiments.patch_experiment(body=body, id=entry["id"])
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
