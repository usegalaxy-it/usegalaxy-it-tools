#!/usr/bin/env python3
"""Keep only the N most recent revisions of each tool in a Galaxy *.yaml.lock file.

Recency is taken from the Galaxy Tool Shed: get_ordered_installable_revisions returns
installable changesets oldest -> newest (Mercurial changelog order). If a locked revision
is missing from that list, /metadata (numeric_revision) is used as a fallback. Entries
whose order cannot be fully determined are left untouched and reported.

The file is edited as text: only "  - <revision>" lines are removed, everything else
(header, entry order, quoting, sections, duplicated entries) is kept byte-for-byte.

Usage:
    trim_revisions.py INPUT --output OUTPUT [--keep 3] [--report trim_report.tsv]

Only the Python standard library is required.
"""
import argparse
import concurrent.futures
import json
import re
import sys
import time
import urllib.parse
import urllib.request

TOOLSHED_API = "https://toolshed.g2.bx.psu.edu/api/repositories"

HEADER_RE = re.compile(r"^(install_repository_dependencies|install_resolver_dependencies|install_tool_dependencies): \S+$")
NAME_RE = re.compile(r"^- name: (\S+)$")
OWNER_RE = re.compile(r"^  owner: (\S+)$")
REVISIONS_RE = re.compile(r"^  revisions:$")
REV_RE = re.compile(r"^  - (\S+)$")
SECTION_RE = re.compile(r"^  tool_panel_section_(label|id): .+$")


class ParseError(Exception):
    pass


def unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def parse(lines):
    """Split the file into header lines and tool entries.

    Each entry is a dict with name, owner and 'lines': a list of (kind, text, revision)
    where kind is 'rev' for revision lines and 'other' otherwise.
    """
    header, entries = [], []
    cur = None
    in_revisions, n_revs = False, 0
    seen_tools = False
    for lineno, line in enumerate(lines, 1):
        text = line.rstrip("\n")
        m = NAME_RE.match(text)
        if m:
            if not seen_tools:
                raise ParseError(f"line {lineno}: tool entry before 'tools:'")
            cur = {"name": m.group(1), "owner": None, "lines": [], "lineno": lineno,
                   "has_revisions": False}
            entries.append(cur)
            cur["lines"].append(("other", line, None))
            in_revisions = False
            continue
        if cur is None:
            if HEADER_RE.match(text) and not seen_tools:
                header.append(line)
            elif text == "tools:" and not seen_tools:
                header.append(line)
                seen_tools = True
            else:
                raise ParseError(f"line {lineno}: unexpected header line {text!r}")
            continue
        m = REV_RE.match(text)
        if m:
            if not in_revisions:
                raise ParseError(f"line {lineno}: revision outside a 'revisions:' block")
            cur["lines"].append(("rev", line, unquote(m.group(1))))
            n_revs += 1
            continue
        if in_revisions and n_revs == 0:
            raise ParseError(f"line {lineno}: empty 'revisions:' block")
        in_revisions = False
        m = OWNER_RE.match(text)
        if m and cur["owner"] is None:
            cur["owner"] = m.group(1)
        elif REVISIONS_RE.match(text) and not cur["has_revisions"]:
            in_revisions, n_revs = True, 0
            cur["has_revisions"] = True
        elif not SECTION_RE.match(text):
            raise ParseError(f"line {lineno}: unexpected line {text!r}")
        cur["lines"].append(("other", line, None))
    if in_revisions and n_revs == 0:
        raise ParseError("end of file: empty 'revisions:' block")
    if not seen_tools:
        raise ParseError("no 'tools:' key found")
    for e in entries:
        if e["owner"] is None:
            raise ParseError(f"line {e['lineno']}: entry {e['name']} has no owner")
    return header, entries


def get_json(url, retries=5, timeout=60):
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return json.load(resp)
        except Exception as exc:  # network errors, rate limiting, bad JSON
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url}: {last}")


def toolshed_order(name, owner, locked):
    """Return (ordered revisions oldest->newest, warning) for the given repository."""
    query = urllib.parse.urlencode({"name": name, "owner": owner})
    order = get_json(f"{TOOLSHED_API}/get_ordered_installable_revisions?{query}")
    missing = [r for r in locked if r not in order]
    if not missing:
        return order, ""
    # Fallback: rank every metadata revision (also non-installable ones) by numeric_revision.
    repos = get_json(f"{TOOLSHED_API}?{query}")
    repos = [r for r in repos if r["name"] == name and r["owner"] == owner]
    if len(repos) != 1:
        return None, f"not ordered: {','.join(missing)} (repository lookup failed)"
    metadata = get_json(f"{TOOLSHED_API}/{repos[0]['id']}/metadata?downloadable_only=false")
    numeric = {v["changeset_revision"]: v["numeric_revision"] for v in metadata.values()}
    still_missing = [r for r in locked if r not in numeric]
    if still_missing:
        return None, f"not ordered: {','.join(still_missing)}"
    return sorted(numeric, key=numeric.get), f"metadata fallback for {','.join(missing)}"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("input", help="*.yaml.lock file to trim")
    parser.add_argument("--output", required=True, help="where to write the trimmed lock file")
    parser.add_argument("--keep", type=int, default=3, help="revisions to keep per tool (default: 3)")
    parser.add_argument("--report", default="trim_report.tsv", help="TSV report (default: trim_report.tsv)")
    parser.add_argument("--threads", type=int, default=3, help="parallel Tool Shed requests (default: 3)")
    args = parser.parse_args()

    with open(args.input) as handle:
        lines = handle.readlines()
    try:
        header, entries = parse(lines)
    except ParseError as exc:
        sys.exit(f"Parse error in {args.input}: {exc}")

    def revisions(entry):
        return [r for kind, _, r in entry["lines"] if kind == "rev"]

    # One Tool Shed lookup per distinct (name, owner) that needs trimming.
    todo = {}
    for e in entries:
        revs = revisions(e)
        if len(revs) > args.keep:
            todo.setdefault((e["name"], e["owner"]), set()).update(revs)

    def lookup(key):
        try:
            return key, toolshed_order(key[0], key[1], todo[key])
        except Exception as exc:
            return key, (None, f"Tool Shed error: {exc}")

    orders = {}
    with concurrent.futures.ThreadPoolExecutor(args.threads) as pool:
        for i, (key, result) in enumerate(pool.map(lookup, todo), 1):
            orders[key] = result
            if i % 100 == 0:
                print(f"  {i}/{len(todo)} repositories queried", file=sys.stderr)

    out = list(header)
    report = [("name", "owner", "n_before", "n_after", "kept", "removed", "warning")]
    trimmed = removed_total = warnings = 0
    for e in entries:
        revs = revisions(e)
        keep, warning = set(revs), ""
        if len(revs) > args.keep:
            order, warning = orders[(e["name"], e["owner"])]
            if order is None:
                warning += "; entry left unchanged"
            else:
                ranked = [r for r in order if r in set(revs)]
                keep = set(ranked[-args.keep:])
        if warning:
            warnings += 1
        for kind, line, rev in e["lines"]:
            if kind != "rev" or rev in keep:
                out.append(line)
        removed = [r for r in revs if r not in keep]
        if removed:
            trimmed += 1
            removed_total += len(removed)
        report.append((e["name"], e["owner"], str(len(revs)), str(len(revs) - len(removed)),
                       ",".join(r for r in revs if r in keep), ",".join(removed), warning))

    with open(args.output, "w") as handle:
        handle.writelines(out)
    with open(args.report, "w") as handle:
        for row in report:
            handle.write("\t".join(row) + "\n")

    total = sum(len(revisions(e)) for e in entries)
    print(f"{len(entries)} entries, {trimmed} trimmed, {removed_total} of {total} revisions removed, "
          f"{warnings} warnings (see {args.report})")


if __name__ == "__main__":
    main()
