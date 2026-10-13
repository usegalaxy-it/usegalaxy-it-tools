# usegalaxy.it tools repository

Repository to manage tools update/installation in Usegalaxy.it.

Documentation available [here](https://usegalaxy-it.github.io/documentation/tools.html)

## Repository layout

| Path | Content |
| --- | --- |
| `files/` | The tools files of usegalaxy.it: `*.yaml` (tool lists) and `*.yaml.lock` (pinned revisions) |
| `usegalaxy-eu-tools/` | Git submodule with the tools files and scripts of [usegalaxy-eu-tools](https://github.com/usegalaxy-eu/usegalaxy-eu-tools) |
| `scripts/import_from_eu.py` | Compares the EU yaml files with `files/` and imports/integrates them |
| `scripts/sync_all.sh` | Fixes and updates the lockfiles of `files/` (uses the scripts of the EU submodule) |
| `scripts/lint_all.sh` | Validates the yaml files of `files/` with the EU schema |
| `scripts/install_all.sh` | Installs the lockfiles of `files/` on the Galaxy server with `shed-tools` |
| `trim-revisions/` | `trim_revisions.py` and the reports of the trimmed lockfiles |

### Requirements

```bash
pip install -r requirements.txt        # bioblend, ephemeris, pykwalify, PyYAML
git submodule update --init usegalaxy-eu-tools
```

---

## 1. Import tools from usegalaxy-eu-tools

`scripts/import_from_eu.py` compares every tools yaml of the `usegalaxy-eu-tools` submodule with the ones in `files/`.
It is interactive: nothing is written without a confirmation. The lockfiles already in `files/` are never touched
(see [section 2](#2-update-the-lockfiles)).

### 1.1 Update the EU submodule (optional)

The script works on the commit of the submodule currently checked out. To compare with the latest EU version:

```bash
git submodule update --remote usegalaxy-eu-tools
```

### 1.2 See what is different (dry run)

```bash
scripts/import_from_eu.py -n          # all the files, nothing is asked or written
scripts/import_from_eu.py -n -v       # list every tool instead of the first 25
```

The first thing printed is a status table with one row per EU file: `NEW (not in files/)`, `identical`, or
`differs: +added -removed ~changed`.

### 1.3 Import a yml that is not in `files/`

Use `-f` to work on a single file (the name can be given with or without extension, and the option can be repeated).
Example with `asaim.yaml`:

```bash
scripts/import_from_eu.py -f asaim
```

```
usegalaxy-eu-tools @ b602eed  ->  files

  file        EU tools  files/ tools  status
  -------------------------------------------------------
  asaim.yaml        30             -  NEW (not in files/)

== asaim.yaml: NOT in files/ (30 tools; lockfile in EU: yes) ==
  Import asaim.yaml into files/? [y/N/q] y
  Also import asaim.yaml.lock (to trim with trim-revisions, then sync)? [Y/n/q] n
```

- The yaml is copied to `files/asaim.yaml`.
- If the `install_*` settings of the EU file differ from the ones used by the files already in `files/`, the script
  asks whether to use the `files/` ones in the imported file (default: yes).
- The question about the lockfile can be answered `n`: the trim step of
  [section 2.1](#21-new-yml-imported-from-eu) reads the EU lockfile directly from the submodule and writes the trimmed one
  into `files/`. Answering `y` gives the same result, because the trim step overwrites the copy.

### 1.4 Compare a yml that is already in `files/`

Example with `tools_iuc.yaml`:

```bash
scripts/import_from_eu.py -f tools_iuc     # one file
scripts/import_from_eu.py                  # all the files
```

```
== tools_iuc.yaml: 3 new in EU, 2 changed in EU, 1 only in files/ ==

  New in EU, not in files/ -> would be ADDED: 3
    + abricate (iuc)  [tool_panel_section_label=Annotation]
    + angsd (iuc)  [tool_panel_section_label=Annotation]
    + gem_check_memote (iuc)  [tool_panel_section_label=Metabolomics]
  Apply to all 3? (i = one by one, l = list all) [y/N/i/l/q] y

  Different in EU -> would be UPDATED to the EU version: 2
    ~ annotatemyids (iuc): tool_panel_section_label: 'Annotation Changed' -> 'Annotation'
    ~ argnorm (iuc): tool_panel_section_label: 'Custom Panel' -> 'Annotation'
  Apply to all 2? (i = one by one, l = list all) [y/N/i/l/q] y

  In files/ but not in EU (removed upstream or specific to usegalaxy.it) -> would be REMOVED: 1
    - it_only_tool (iuc)  [tool_panel_section_label=Annotation]
  Apply to all 1? (i = one by one, l = list all) [y/N/i/l/q] n
```

(abbreviated output; the tool names above are only an example)

Tools are matched by `(name, owner)`. The differences are grouped in three categories and, for each of them, you answer:

| Answer | Meaning |
| --- | --- |
| `y` | apply to all |
| `n` | skip (default) |
| `i` | go one by one (`a` = yes to all the rest) |
| `l` | list all the tools of the category |
| `q` | quit |

| Category | Applied change |
| --- | --- |
| New in EU, not in `files/` | The tool is **added**, in the same section as in the EU file |
| Different in EU (e.g. another panel section) | The tool is **updated** to the EU version |
| In `files/` but not in EU | The tool is **removed**. Review it first: it may be specific to usegalaxy.it |

Edits are made on the text of the file, so comments, section headers and layout are kept. Before writing, the script
re-parses the result and checks that only the selected differences are gone; if the check fails, nothing is written.
Top-level settings (`install_repository_dependencies`, etc.) are only reported, never changed. Running the script again
after applying everything finds no differences.

After the import, the lockfile of the file needs to be created or updated: see [section 2](#2-update-the-lockfiles).

---

## 2. Update the lockfiles

The lockfiles in `files/` list the Toolshed revisions to install. They are not edited by hand:

- a lockfile coming from EU lists **all** the revisions of every tool, so it is trimmed first with
  `trim-revisions/trim_revisions.py`, which keeps the **3 most recent** revisions of each tool;
- `scripts/sync_all.sh` then fixes the lockfiles (e.g. adds the missing tools) and updates the tools to the latest
  revisions;
- `scripts/lint_all.sh` validates the yaml files.

### 2.1 New yml imported from EU

Example with `asaim`:

```bash
# 1. trim the EU lockfile into files/
python3 trim-revisions/trim_revisions.py usegalaxy-eu-tools/asaim.yaml.lock \
    --output files/asaim.yaml.lock \
    --keep 3 \
    --report trim-revisions/reports/trim_report.asaim.tsv

# 2. fix and update all the lockfiles of files/
scripts/sync_all.sh

# 3. validate the yaml files
scripts/lint_all.sh

# 4. review
git diff files/
```

| Option of `trim_revisions.py` | Default | Meaning |
| --- | --- | --- |
| `INPUT` | | `*.yaml.lock` file to trim |
| `--output` | required | Where to write the trimmed lockfile |
| `--keep` | 3 | How many revisions to keep for each tool |
| `--report` | `trim_report.tsv` | TSV report: name, owner, revisions before and after, kept and removed, warnings |
| `--threads` | 3 | Parallel requests to the Toolshed |

Notes on the trim step:

- The most recent revisions are taken from the Galaxy Toolshed (the revisions in the lockfile are in alphabetical
  order, so the file does not tell which ones are the newest). It needs network access to
  `toolshed.g2.bx.psu.edu`.
- If the order of a tool cannot be determined, or the Toolshed does not answer, the entry is left **unchanged** and
  the reason is written in the `warning` column of the report. Check that column before going on.
- The file is edited as text: only the revision lines are removed, everything else is kept as it was.
- Keep the default of 3 threads: with more parallel requests the Toolshed rate-limits.
- Commit the report (`trim-revisions/reports/trim_report.<name>.tsv`) together with the lockfile.

### 2.2 yml already in `files/`

After integrating the changes of a yml with [section 1.4](#14-compare-a-yml-that-is-already-in-files):

```bash
scripts/sync_all.sh       # adds the lockfile entries of the new tools and updates the revisions
scripts/lint_all.sh
git diff files/
```

`sync_all.sh` and `lint_all.sh` work on **all** the files in `files/`. `sync_all.sh` queries the Toolshed and can add
newer revisions: the lists can grow again after every sync. When that happens, trim the lockfile again. The script
reads the whole input before writing the output, so the same file can be used as input and output:

```bash
python3 trim-revisions/trim_revisions.py files/asaim.yaml.lock \
    --output files/asaim.yaml.lock \
    --keep 3 \
    --report trim-revisions/reports/trim_report.asaim.tsv
```

### 2.3 Things to know

- **Removing revisions from a lockfile does not uninstall them from Galaxy.** `shed-tools install` installs what is
  listed and does not remove anything: on the servers where old revisions are already installed, they stay until they
  are uninstalled in a separate step.
- **Workflows with old versions.** On new installations the removed revisions will not be there, so workflows pinned to
  an old version of a tool might not find it.
