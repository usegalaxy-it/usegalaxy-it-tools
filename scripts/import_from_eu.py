#!/usr/bin/env python3
"""Compare the tools files of usegalaxy-eu-tools with the ones in files/.

For every tools yaml/yml in the top level of the usegalaxy-eu-tools submodule:

  * not in files/   -> propose to import it. If EU has its lockfile too, propose to
                       import that as well: trim it with trim-revisions, then run
                       scripts/sync_all.sh.
  * already there   -> compare the tool lists and propose to integrate the changes
                       (tools new in EU, changed in EU, only in files/).

Lockfiles of the files already in files/ are never touched: sync_all.sh manages them.
Edits are done on the text of the file, so comments, section headers and layout of
files/ are preserved; the EU text of a tool is copied as it is.
Every edit is re-parsed and checked before anything is written.

Examples:
  scripts/import_from_eu.py                  # all the files, interactive
  scripts/import_from_eu.py -f tools_iuc     # only one file
  scripts/import_from_eu.py -n -v            # what would be proposed, change nothing
"""

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap

import yaml

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EU_SUBMODULE = "usegalaxy-eu-tools"
PREVIEW = 25  # tools listed per category unless -v / 'l'
Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


class Quit(Exception):
    pass


class FileError(Exception):
    pass


def die(msg, code=1):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def ask(prompt, choices, default):
    """Ask for one letter among choices; Enter gives the default, q quits."""
    shown = "/".join(c.upper() if c == default else c for c in choices)
    while True:
        try:
            answer = input("%s [%s] " % (prompt, shown)).strip().lower()
        except EOFError:
            print()
            raise Quit()
        answer = answer or default
        if answer in choices:
            if answer == "q":
                raise Quit()
            return answer
        print("  choose one of: " + ", ".join(choices))


# --------------------------------------------------------------------------- parsing


def canon(entry):
    return json.dumps(entry, sort_keys=True, default=str)


class Block:
    """A tool entry: lines [start, end) of the file."""

    def __init__(self, start, end, data):
        self.start = start
        self.end = end
        self.data = data
        self.key = (data["name"], data["owner"])


class ToolsFile:
    def __init__(self, path, text=None):
        self.path = path
        self.name = os.path.basename(path)
        if text is None:
            with open(path) as fh:
                text = fh.read()
        self.text = text
        self.lines = text.splitlines()
        try:
            doc = yaml.load(text, Loader=Loader) or {}
        except yaml.YAMLError as exc:
            raise FileError("%s: invalid YAML: %s" % (self.name, exc))
        if not isinstance(doc, dict):
            raise FileError("%s: top level is not a mapping" % self.name)
        self.header = {k: v for k, v in doc.items() if k != "tools"}
        self.tools_line, self.blocks = self._split_blocks()
        listed = doc.get("tools") or []
        if len(listed) != len(self.blocks):
            raise FileError(
                "%s: cannot map the text of 'tools:' to its entries (%d entries, %d text blocks)"
                % (self.name, len(listed), len(self.blocks))
            )
        self.groups = {}  # key -> unique entries (exact repeats collapsed)
        self.by_key = {}  # key -> indexes of its blocks
        seen = {}
        for idx, block in enumerate(self.blocks):
            self.by_key.setdefault(block.key, []).append(idx)
            c = canon(block.data)
            if c not in seen.setdefault(block.key, set()):
                seen[block.key].add(c)
                self.groups.setdefault(block.key, []).append(block.data)

    def _split_blocks(self):
        lines = self.lines
        tools_line = next(
            (i for i, l in enumerate(lines) if re.match(r"^tools:\s*(#.*)?$", l)), None
        )
        self.indent = None
        if tools_line is None:
            return None, []
        blocks, indent, i = [], None, tools_line + 1
        while i < len(lines):
            line = lines[i]
            m = re.match(r"^(\s*)- ", line)
            if m and (indent is None or len(m.group(1)) == indent):
                indent = len(m.group(1))
                last, j = i, i + 1
                while j < len(lines):
                    nxt = lines[j]
                    if nxt.strip() == "":
                        j += 1
                    elif len(nxt) - len(nxt.lstrip()) > indent:
                        last = j
                        j += 1
                    else:
                        break
                text = textwrap.dedent("\n".join(lines[i:last + 1]))
                try:
                    parsed = yaml.load(text, Loader=Loader)
                except yaml.YAMLError as exc:
                    raise FileError("%s: line %d: invalid entry: %s" % (self.name, i + 1, exc))
                if (
                    not isinstance(parsed, list)
                    or len(parsed) != 1
                    or not isinstance(parsed[0], dict)
                    or "name" not in parsed[0]
                    or "owner" not in parsed[0]
                ):
                    raise FileError("%s: line %d: entry without name/owner" % (self.name, i + 1))
                blocks.append(Block(i, last + 1, parsed[0]))
                i = last + 1
            else:
                stripped = line.lstrip()
                if (
                    indent is not None
                    and stripped
                    and not stripped.startswith("#")
                    and len(line) - len(stripped) < indent
                ):
                    break  # next top-level key
                i += 1
        self.indent = indent
        return tools_line, blocks


def diff(eu, it):
    """(added, removed, changed) keys, going from files/ to EU."""
    added = [k for k in eu.groups if k not in it.groups]
    removed = [k for k in it.groups if k not in eu.groups]
    changed = [
        k
        for k in eu.groups
        if k in it.groups
        and sorted(canon(e) for e in eu.groups[k]) != sorted(canon(e) for e in it.groups[k])
    ]
    return added, removed, changed


# --------------------------------------------------------------------------- editing


def eu_blocks_of(eu, key):
    """Text of the (unique) EU blocks of a tool, separated by a blank line."""
    out, seen = [], set()
    for b in eu.blocks:
        if b.key == key and canon(b.data) not in seen:
            seen.add(canon(b.data))
            if out:
                out.append("")
            out.extend(eu.lines[b.start:b.end])
    return out


def apply_changes(eu, it, add, remove, change):
    """New lines of the files/ file with the selected changes applied."""
    add, remove, change = set(add), set(remove), set(change)
    delta = (it.indent - eu.indent) if it.blocks and eu.blocks else 0

    def shift(lines):
        """EU text re-indented to the indentation of the tool list of files/."""
        if not delta:
            return list(lines)
        shifted = []
        for l in lines:
            if not l.strip():
                shifted.append(l)
            elif delta > 0:
                shifted.append(" " * delta + l)
            else:
                shifted.append(l[min(-delta, len(l) - len(l.lstrip())):])
        return shifted

    # New tools go right after the tool that precedes them in the EU file (so they land
    # in the same section); before the first tool if there is no such tool. A section
    # comment of EU that files/ does not have yet comes along with the tool.
    it_comments = {l.strip() for l in it.lines if l.strip().startswith("#")}
    inserts, anchor, placed, prev_end = {}, -1, set(), eu.tools_line + 1
    for b in eu.blocks:
        if b.key in it.by_key:
            anchor = it.by_key[b.key][-1]
        elif b.key in add and (b.key, canon(b.data)) not in placed:
            placed.add((b.key, canon(b.data)))
            leading = [
                l for l in eu.lines[prev_end:b.start]
                if l.strip().startswith("#") and l.strip() not in it_comments
            ]
            it_comments.update(l.strip() for l in leading)
            inserts.setdefault(anchor, []).append((leading, shift(eu.lines[b.start:b.end])))
        prev_end = b.end

    out = list(it.lines[:it.tools_line + 1])
    pos, drop_blank, done = it.tools_line + 1, False, set()

    def emit_head():
        for leading, block in inserts.get(-1, []):
            out.extend(leading + block + [""])

    if not it.blocks:
        emit_head()
    for idx, b in enumerate(it.blocks):
        gap = it.lines[pos:b.start]
        if drop_blank and gap and gap[0].strip() == "":
            gap = gap[1:]
        drop_blank = False
        out += gap
        if idx == 0:
            emit_head()
        if b.key in remove:
            drop_blank = True
        elif b.key in change:
            if b.key not in done:
                done.add(b.key)
                out += shift(eu_blocks_of(eu, b.key))
            else:
                drop_blank = True  # further copy of the same tool
        else:
            out += it.lines[b.start:b.end]
        for leading, block in inserts.get(idx, []):
            out += [""] + leading + block
        pos = b.end
    tail = it.lines[pos:]
    if drop_blank and tail and tail[0].strip() == "":
        tail = tail[1:]
    return out + tail


def verify(new_text, it, eu, expected):
    """Re-parse the edited text: only the selected differences must be gone."""
    new = ToolsFile(it.path, new_text)
    got = [set(x) for x in diff(eu, new)]
    if got != expected:
        raise FileError(
            "internal check failed on %s (the edit does not give the expected result); "
            "nothing was written" % it.name
        )


# --------------------------------------------------------------------------- display


def fmt_entry(entry):
    return ", ".join("%s=%s" % (k, v) for k, v in entry.items() if k not in ("name", "owner"))


def fmt_tool(key, entries):
    return "%s (%s)  [%s]" % (key[0], key[1], "; ".join(fmt_entry(e) for e in entries))


def fmt_change(key, eu_entries, it_entries):
    if len(eu_entries) == 1 and len(it_entries) == 1:
        old, new = it_entries[0], eu_entries[0]
        parts = [
            "%s: %r -> %r" % (f, old.get(f), new.get(f))
            for f in sorted(set(old) | set(new))
            if old.get(f) != new.get(f)
        ]
        return "%s (%s): %s" % (key[0], key[1], "; ".join(parts))
    return "%s (%s): files/ %s -> EU %s" % (
        key[0],
        key[1],
        [fmt_entry(e) for e in it_entries],
        [fmt_entry(e) for e in eu_entries],
    )


def show(lines, verbose):
    limit = len(lines) if verbose else PREVIEW
    for line in lines[:limit]:
        print("    " + line)
    if len(lines) > limit:
        print("    ... and %d more (answer 'l' to list them all)" % (len(lines) - limit))


def choose(title, keys, fmt):
    """Ask what to do with a category of differences; return the selected keys."""
    if not keys:
        return []
    print("\n  %s: %d" % (title, len(keys)))
    show([fmt(k) for k in keys], False)
    while True:
        answer = ask("  Apply to all %d? (i = one by one, l = list all)" % len(keys), "ynilq", "n")
        if answer == "l":
            show([fmt(k) for k in keys], True)
        elif answer == "y":
            return list(keys)
        elif answer == "n":
            return []
        else:
            picked = []
            for pos, key in enumerate(keys):
                print("    " + fmt(key))
                a = ask("    apply? (a = yes to all the rest)", "ynaq", "n")
                if a == "y":
                    picked.append(key)
                elif a == "a":
                    picked.extend(keys[pos:])
                    break
            return picked


# --------------------------------------------------------------------------- actions


def yaml_scalar(value):
    return str(value).lower() if isinstance(value, bool) else str(value)


def reference_settings(files_dir):
    """install_* settings shared by every yaml already in files/ (None if they differ)."""
    ref = None
    for p in sorted(glob.glob(os.path.join(files_dir, "*"))):
        if not p.endswith((".yaml", ".yml")):
            continue
        try:
            header = ToolsFile(p).header
        except FileError:
            continue
        settings = {k: v for k, v in header.items() if k.startswith("install_")}
        if ref is None:
            ref = settings
        elif ref != settings:
            return None
    return ref or None


def import_new(eu, files_dir, dry_run, ref):
    lock = eu.path + ".lock"
    has_lock = os.path.isfile(lock)
    print(
        "\n== %s: NOT in files/ (%d tools; lockfile in EU: %s) =="
        % (eu.name, len(eu.groups), "yes" if has_lock else "no")
    )
    if dry_run:
        print("  would propose to import %s%s" % (eu.name, " + %s.lock" % eu.name if has_lock else ""))
        return None
    if ask("  Import %s into files/?" % eu.name, "ynq", "n") != "y":
        return None
    text = eu.text
    differing = {k: v for k, v in (ref or {}).items() if k in eu.header and eu.header[k] != v}
    if differing:
        print("  EU settings differ from the ones used by the files already in files/:")
        for k, v in differing.items():
            print("    %s: EU %s, files/ %s" % (k, yaml_scalar(eu.header[k]), yaml_scalar(v)))
        if ask("  Use the files/ settings in the imported file?", "ynq", "y") == "y":
            for k, v in differing.items():
                text, n = re.subn(r"(?m)^%s:.*$" % re.escape(k), "%s: %s" % (k, yaml_scalar(v)),
                                  text, count=1)
                if not n:
                    print("  warning: could not edit '%s', left as in EU" % k)
    with open(os.path.join(files_dir, eu.name), "w") as fh:
        fh.write(text)
    result = {"yaml": eu.name, "lock": None}
    if not has_lock:
        print("  (no lockfile in EU: sync_all.sh will generate it)")
    elif ask(
        "  Also import %s.lock (to trim with trim-revisions, then sync)?" % eu.name, "ynq", "y"
    ) == "y":
        shutil.copyfile(lock, os.path.join(files_dir, eu.name + ".lock"))
        result["lock"] = eu.name + ".lock"
    return result


def integrate(eu, it, args):
    if it.tools_line is None:
        raise FileError("%s in files/ has no block-style 'tools:' list: edit it by hand" % it.name)
    added, removed, changed = diff(eu, it)
    print(
        "\n== %s: %d new in EU, %d changed in EU, %d only in files/ =="
        % (eu.name, len(added), len(changed), len(removed))
    )
    for k in sorted(set(eu.header) | set(it.header)):
        if eu.header.get(k) != it.header.get(k):
            print(
                "  note: top-level '%s' differs (files/: %r, EU: %r) - not touched"
                % (k, it.header.get(k), eu.header.get(k))
            )
    if not (added or removed or changed):
        return None

    def f_add(k):
        return "+ " + fmt_tool(k, eu.groups[k])

    def f_chg(k):
        return "~ " + fmt_change(k, eu.groups[k], it.groups[k])

    def f_rm(k):
        return "- " + fmt_tool(k, it.groups[k])

    cats = [
        ("New in EU, not in files/ -> would be ADDED", added, f_add),
        ("Different in EU -> would be UPDATED to the EU version", changed, f_chg),
        ("In files/ but not in EU (removed upstream or specific to usegalaxy.it) -> would be REMOVED",
         removed, f_rm),
    ]
    if args.dry_run:
        for title, keys, fmt in cats:
            if keys:
                print("\n  %s: %d" % (title, len(keys)))
                show([fmt(k) for k in keys], args.verbose)
        return None

    sel_add, sel_chg, sel_rm = (choose(t, k, f) for t, k, f in cats)
    if not (sel_add or sel_chg or sel_rm):
        print("\n  nothing applied")
        return None
    new_lines = apply_changes(eu, it, sel_add, sel_rm, sel_chg)
    new_text = "\n".join(new_lines) + "\n"
    verify(
        new_text, it, eu,
        [set(added) - set(sel_add), set(removed) - set(sel_rm), set(changed) - set(sel_chg)],
    )
    with open(it.path, "w") as fh:
        fh.write(new_text)
    print("\n  %s updated: +%d added, ~%d updated, -%d removed"
          % (os.path.relpath(it.path, REPO_DIR), len(sel_add), len(sel_chg), len(sel_rm)))
    return {"yaml": eu.name, "counts": (len(sel_add), len(sel_chg), len(sel_rm))}


# --------------------------------------------------------------------------- main


def eu_yaml_paths(eu_dir):
    paths = []
    for p in sorted(glob.glob(os.path.join(eu_dir, "*"))):
        base = os.path.basename(p)
        if (
            os.path.isfile(p)
            and base.endswith((".yaml", ".yml"))
            and not base.startswith(".")
            and not base.endswith(".not-installable-revisions.yaml")
        ):
            paths.append(p)
    return paths


def eu_revision(eu_dir):
    try:
        out = subprocess.check_output(
            ["git", "-C", eu_dir, "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


def find_in_files(files_dir, name):
    stem = os.path.splitext(name)[0]
    for ext in (".yaml", ".yml"):
        p = os.path.join(files_dir, stem + ext)
        if os.path.isfile(p):
            return p
    return None


def select(eu_files, wanted):
    if not wanted:
        return eu_files
    by_name = {f.name: f for f in eu_files}
    by_stem = {os.path.splitext(f.name)[0]: f for f in eu_files}
    chosen = []
    for w in wanted:
        w = os.path.basename(w)
        if w.endswith(".lock"):
            w = w[:-5]
        f = by_name.get(w) or by_stem.get(w) or by_stem.get(os.path.splitext(w)[0])
        if f is None:
            die("'%s' is not a tools file in usegalaxy-eu-tools. Available: %s"
                % (w, ", ".join(sorted(by_stem))), code=2)
        if f not in chosen:
            chosen.append(f)
    return chosen


def print_table(rows):
    widths = [max(len(r[i]) for r in rows) for i in range(4)]
    for n, r in enumerate(rows):
        print("  %s  %s  %s  %s" % (
            r[0].ljust(widths[0]), r[1].rjust(widths[1]), r[2].rjust(widths[2]), r[3]))
        if n == 0:
            print("  " + "-" * (sum(widths[:3]) + 6 + widths[3]))


def main():
    default_eu = os.path.join(REPO_DIR, EU_SUBMODULE)
    ap = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog=__doc__.split("\n\n", 1)[1],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("-f", "--file", action="append", metavar="NAME",
                    help="only this file, e.g. tools_iuc or tools_iuc.yaml (can be repeated)")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="show what would be proposed; ask nothing, change nothing")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="with --dry-run, list every tool instead of the first %d" % PREVIEW)
    ap.add_argument("--eu-dir", default=default_eu, help="usegalaxy-eu-tools checkout (default: %(default)s)")
    ap.add_argument("--files-dir", default=os.path.join(REPO_DIR, "files"),
                    help="destination directory (default: %(default)s)")
    args = ap.parse_args()
    eu_dir, files_dir = os.path.abspath(args.eu_dir), os.path.abspath(args.files_dir)

    if not os.path.isdir(files_dir):
        die("%s does not exist" % files_dir)
    if not eu_yaml_paths(eu_dir) and eu_dir == default_eu:
        print("Initializing the %s submodule..." % EU_SUBMODULE)
        subprocess.call(["git", "-C", REPO_DIR, "submodule", "update", "--init", EU_SUBMODULE])
    if not eu_yaml_paths(eu_dir):
        die("no tools yaml found in %s" % eu_dir)

    eu_files, skipped = [], []
    for p in eu_yaml_paths(eu_dir):
        try:
            f = ToolsFile(p)
        except FileError as exc:
            die(str(exc))
        (eu_files if f.blocks else skipped).append(f)
    chosen = select(eu_files, args.file)

    entries, rows = [], [("file", "EU tools", "files/ tools", "status")]
    for eu in chosen:
        it_path, it = find_in_files(files_dir, eu.name), None
        status, usable = "NEW (not in files/)", True
        if it_path:
            try:
                it = ToolsFile(it_path)
                added, removed, changed = diff(eu, it)
                status = "identical" if not (added or removed or changed) else (
                    "differs: +%d -%d ~%d" % (len(added), len(removed), len(changed)))
                if eu.header != it.header:
                    status += " [top-level settings differ]"
            except FileError as exc:
                status, usable = "ERROR in files/: %s" % exc, False
        if usable:
            entries.append((eu, it))
        rows.append((eu.name, str(len(eu.groups)), str(len(it.groups)) if it else "-", status))

    print("usegalaxy-eu-tools @ %s  ->  %s" % (eu_revision(eu_dir), os.path.relpath(files_dir, REPO_DIR)))
    print()
    print_table(rows)
    only_it = sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(files_dir, "*"))
        if p.endswith((".yaml", ".yml"))
        and os.path.splitext(os.path.basename(p))[0] not in {os.path.splitext(f.name)[0] for f in eu_files}
    )
    if only_it and not args.file:
        print("\n  only in files/ (no EU counterpart, ignored): " + ", ".join(only_it))
    if skipped and not args.file:
        print("  skipped from EU (no 'tools:' list): " + ", ".join(f.name for f in skipped))

    imported, updated = [], []
    ref = reference_settings(files_dir)  # taken before importing anything
    try:
        for eu, it in entries:
            try:
                if it is None:
                    res = import_new(eu, files_dir, args.dry_run, ref)
                    if res:
                        imported.append(res)
                else:
                    res = integrate(eu, it, args)
                    if res:
                        updated.append(res)
            except FileError as exc:
                print("\nERROR: %s" % exc)
    except Quit:
        print("\nStopped.")

    if imported or updated:
        print("\n== Summary ==")
        for r in imported:
            print("  imported: %s%s" % (r["yaml"], " + " + r["lock"] if r["lock"] else ""))
        for r in updated:
            print("  updated:  %s (+%d ~%d -%d)" % ((r["yaml"],) + r["counts"]))
        print("\n  Next steps:")
        locks = [r["lock"] for r in imported if r["lock"]]
        if locks:
            print("   1. trim-revisions on: " + ", ".join("files/" + l for l in locks))
        step = 2 if locks else 1
        print("   %d. scripts/sync_all.sh   (generates/updates the lockfiles)" % step)
        print("   %d. git diff files/       (review)" % (step + 1))


if __name__ == "__main__":
    main()
