"""
Interface to electronic lab journal https://elabftw.tugraz.at/
See https://alexgu2008.github.io/elabftw_api_support/
"""

import elabapy
import json
import os

def create_entry(title):
    entry = {}
    entry["title"] = title
    return entry

def copy_fields(from_entry, to_entry):
    for key in from_entry:
        to_entry[key] = from_entry[key]


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
            self.manager.post_experiment(entry["id"], entry)
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
            json.dump(entry, f)
