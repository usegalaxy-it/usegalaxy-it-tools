# scripts

## import_from_eu.py

Compares the tools files (`*.yaml` / `*.yml`) of the `usegalaxy-eu-tools` submodule with the ones in `files/`, and proposes to import or integrate the differences. It is interactive: nothing is written without a confirmation.

Lockfiles of the files already in `files/` are never touched: they are managed by `sync_all.sh`.

### Requirements

- Python 3
- PyYAML (already in `requirements.txt`)
- the `usegalaxy-eu-tools` submodule checked out (the script initializes it if the directory is empty)

The script works on the commit of the submodule currently checked out. To compare with a newer version of the EU repository, update the submodule first.

### Usage

```bash
scripts/import_from_eu.py                  # all the files, interactive
scripts/import_from_eu.py -f tools_iuc     # only one file (can be repeated)
scripts/import_from_eu.py -n               # dry run: show the proposals, change nothing
scripts/import_from_eu.py -n -v            # dry run, list every tool
```

| Option | Description |
| --- | --- |
| `-f`, `--file NAME` | Only this file, e.g. `tools_iuc` or `tools_iuc.yaml`. Can be repeated. |
| `-n`, `--dry-run` | Show what would be proposed. Asks nothing, writes nothing. |
| `-v`, `--verbose` | With `--dry-run`, list every tool instead of the first 25. |
| `--eu-dir DIR` | `usegalaxy-eu-tools` checkout (default: the submodule). |
| `--files-dir DIR` | Destination directory (default: `files/`). |

The script starts with a status table with one row per EU file: `NEW (not in files/)`, `identical`, or `differs: +added -removed ~changed`.

### What it does

**File not in `files/`**

1. Proposes to import the yaml.
2. If the EU lockfile exists, proposes to import it too. Trim it with `trim-revisions`, then run `sync_all.sh`.
3. If the `install_*` settings of the EU file differ from the ones used by the files already in `files/`, asks whether to use the `files/` ones in the imported file (default: yes).

**File already in `files/`**

Tools are matched by `(name, owner)` and the differences are grouped in three categories. For each one you can answer:

| Answer | Meaning |
| --- | --- |
| `y` | apply to all |
| `n` | skip (default) |
| `i` | go one by one (`a` = yes to all the rest) |
| `l` | list all the tools of the category |
| `q` | quit |

| Category | Applied change |
| --- | --- |
| New in EU, not in `files/` | The tool is **added**. |
| Different in EU (e.g. another panel section) | The tool is **updated** to the EU version. |
| In `files/` but not in EU | The tool is **removed**. Review it first: it may be specific to usegalaxy.it. |

### Behaviour

- Edits are made on the text of the file, so comments, section headers and layout of `files/` are kept. The EU text of a tool is copied as it is, re-indented if needed.
- A new tool is inserted after the tool that precedes it in the EU file, so it ends up in the same section. A section comment missing in `files/` comes along with it.
- Top-level settings (`install_repository_dependencies`, etc.) of a file already in `files/` are only reported, never changed.
- Before writing, the script re-parses the result and checks that only the selected differences are gone. If the check fails, nothing is written.
- The script is idempotent: running it again after applying everything finds no differences.

### Suggested workflow

```bash
git submodule update --remote usegalaxy-eu-tools   # optional: newer EU version
scripts/import_from_eu.py -n                       # see what is going on
scripts/import_from_eu.py -f <file>                # integrate one file
# imported lockfiles: trim-revisions on files/<name>.yaml.lock
scripts/sync_all.sh                                # generate/update the lockfiles
scripts/lint_all.sh                                # validate with the EU schema
git diff files/                                    # review
```

### Notes

- The EU files contain repeated identical `(name, owner)` entries. They are treated as one tool when comparing, so counts are per unique tool. Importing a whole new file copies it as it is.
- Files without a `tools:` list (e.g. `zizmor.yml`) and `*.not-installable-revisions.yaml` files are ignored.
- A file in `files/` with no block-style `tools:` list cannot be merged automatically: the script reports it and leaves it alone.
- Files that exist only in `files/` (e.g. `usegalaxyit_dev.yaml`) are listed and ignored.
- Exit code is `2` if the file passed with `-f` does not exist in the EU repository, `1` on other fatal errors.
