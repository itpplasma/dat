# dat
Research data management inspired by git

`dat` records scientific code runs and syncs their data between the
working directory (`RUN`) and long-term storage (`DATA`) using
[rclone](https://rclone.org/). Run metadata is stored in `metadata.json`
using the [eLabFTW](https://www.elabftw.net/) metadata standard and mirrored
as an experiment entry in the eLabFTW database.

## Workflow

1. (optional) Pull required inputs and templates from DATA to RUN:
   `dat pull <path>`
2. Start the run, e.g. `slurm <run_code>`.
3. Commit the started run to the database:
   `dat commit -m <message>`
4. When the run finished, push results from RUN to DATA:
   `dat push`

## Configuration

* `DAT_DATA` — root of long-term DATA storage (file system path or an
  rclone remote, e.g. `nextcloud:data`). Defaults to `/proj/plasma`.
* `ELAB_URL`, `ELAB_KEY` — eLabFTW API endpoint and token used to create
  and update the experiment entry.

## Commands

* `dat pull <path>` — unidirectional copy of `DATA/<path>` into the
  current directory (RUN).
* `dat commit -m <message>` — write the title (and optional body after a
  newline) plus automatically retrieved information to `metadata.json` and
  create a database entry with status `running`.
* `dat push` — unidirectionally copy the current directory from RUN to DATA
  (immutable; existing files are never overwritten), then push the final
  `metadata.json` with status `finished` and update the database.
