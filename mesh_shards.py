#!/usr/bin/env python3
"""
mesh_shards.py - Streaming JSON-Lines shard helpers for the mesh pipeline.

The editor export (ue.py) can produce millions of static-mesh / foliage
entries (a single Jeju export is ~6M entries / ~2.7 GB). Loading that as one
JSON document (`json.load`) blows up memory (MemoryError). Instead the
pipeline streams entries through *shards*: a directory of `.jsonl` files,
one JSON object per line, capped at SHARD_SIZE entries each. Every stage
(ue.py -> import_meshes.py -> convert2.py) reads/writes entries one at a
time, so peak memory is bounded to a single entry regardless of total count.

Format:
    <out_dir>/<prefix>_00000.jsonl
    <out_dir>/<prefix>_00001.jsonl
    ...
Each line is `json.dumps(entry)`. `iter_entries` reads every `*.jsonl` in
the directory in sorted (== write) order.

This module is intentionally dependency-free (stdlib only) so ue.py can use
it inside the UE editor's Python runtime, which can't import mt_paths.
"""
from __future__ import annotations

import glob
import json
import os

# Entries per shard file. ~200k flat mesh entries is roughly 90 MB of JSONL
# — small enough to load one shard if ever needed, large enough that a full
# Jeju export is a few dozen files, not thousands.
SHARD_SIZE = 200_000


class ShardWriter:
    """Append entries one at a time; rolls to a new shard file every
    `shard_size` entries. Clears any pre-existing shards with the same prefix
    in the target dir first (so a re-run never mixes stale + fresh data)."""

    def __init__(self, out_dir, prefix="part", shard_size=SHARD_SIZE):
        self.dir = str(out_dir)
        self.prefix = prefix
        self.shard_size = shard_size
        self.count = 0
        self._shard_idx = 0
        self._f = None
        self._n_in_shard = 0
        os.makedirs(self.dir, exist_ok=True)
        for p in glob.glob(os.path.join(self.dir, f"{prefix}_*.jsonl")):
            try:
                os.remove(p)
            except OSError:
                pass

    def _open_new(self):
        if self._f is not None:
            self._f.close()
        path = os.path.join(self.dir, f"{self.prefix}_{self._shard_idx:05d}.jsonl")
        self._f = open(path, "w", encoding="utf-8")
        self._shard_idx += 1
        self._n_in_shard = 0

    def write(self, entry):
        if self._f is None or self._n_in_shard >= self.shard_size:
            self._open_new()
        self._f.write(json.dumps(entry, ensure_ascii=False))
        self._f.write("\n")
        self._n_in_shard += 1
        self.count += 1

    def close(self):
        if self._f is not None:
            self._f.close()
            self._f = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def shard_files(in_dir, prefix=None):
    """Sorted list of shard file paths in `in_dir`."""
    pat = f"{prefix}_*.jsonl" if prefix else "*.jsonl"
    return sorted(glob.glob(os.path.join(str(in_dir), pat)))


def iter_entries(in_dir, prefix=None, exclude_prefixes=None):
    """Yield every entry across all shard files, in write order. O(1) memory
    per entry. Re-callable (re-opens files) so callers can make multiple
    passes over the same shard set.

    exclude_prefixes: optional iterable of filename prefixes to skip (e.g.
    ('fol',) to read actor shards but not foliage)."""
    excl = tuple(exclude_prefixes or ())
    for path in shard_files(in_dir, prefix):
        if excl and os.path.basename(path).startswith(tuple(p + "_" for p in excl)):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)


def count_entries(in_dir, prefix=None):
    """Count entries across all shards without materializing them."""
    n = 0
    for path in shard_files(in_dir, prefix):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
    return n


def has_shards(in_dir, prefix=None):
    return bool(shard_files(in_dir, prefix))


def split_json_file(src_path, out_dir, shard_size=SHARD_SIZE,
                    group_to_prefix=None, default_prefix="sm"):
    """Stream a monolithic static_meshes.json into JSONL shards WITHOUT
    loading it whole. Extracts every object that is an element of an array
    (i.e. every entry inside static_meshes.<group>[]). Dependency-free: a
    small char-level state machine tracks string/escape state and bracket
    nesting, capturing each array-element object's text and json.loads-ing
    only that one object at a time.

    GROUP-AWARE: the JSON key whose array an entry lives in (e.g. "actors"
    or "foliage" under static_meshes) is tracked, and each entry is routed
    to a shard set chosen by `group_to_prefix` (default: foliage -> "fol",
    everything else -> `default_prefix`). This lets a later build read only
    the actor shards (skip "fol_*") to drop foliage.

    Works for the {"static_meshes": {"actors": [...], "foliage": [...]}}
    shape ue.py produces, and is robust to arbitrary nesting inside an entry
    (inner arrays/objects/strings are handled). Returns the total entry count.
    """
    if group_to_prefix is None:
        group_to_prefix = {"foliage": "fol"}

    writers = {}  # prefix -> ShardWriter (lazily created)

    def writer_for(group):
        prefix = group_to_prefix.get(group, default_prefix)
        w = writers.get(prefix)
        if w is None:
            w = ShardWriter(out_dir, prefix=prefix, shard_size=shard_size)
            writers[prefix] = w
        return w

    stack = []              # container stack: '{' or '['
    array_name_stack = []   # parallel to '[' pushes: the key naming each array
    in_string = False
    escape = False
    capturing = False       # inside an array-element object we're collecting
    depth = 0               # brace depth while capturing
    buf = []
    cur_str = []            # chars of the string currently being read (uncaptured)
    last_string = None      # most recently completed string token
    last_key = None         # most recent string that was an object key (str + ':')
    total = 0
    try:
        with open(src_path, "r", encoding="utf-8") as f:
            while True:
                chunk = f.read(1 << 20)  # 1 MB
                if not chunk:
                    break
                for ch in chunk:
                    if capturing:
                        buf.append(ch)
                        if in_string:
                            if escape:
                                escape = False
                            elif ch == "\\":
                                escape = True
                            elif ch == '"':
                                in_string = False
                        else:
                            if ch == '"':
                                in_string = True
                            elif ch == "{":
                                depth += 1
                            elif ch == "}":
                                depth -= 1
                                if depth == 0:
                                    group = array_name_stack[-1] if array_name_stack else None
                                    writer_for(group).write(json.loads("".join(buf)))
                                    total += 1
                                    buf = []
                                    capturing = False
                        continue
                    # --- not capturing: track containers / strings / keys ---
                    if in_string:
                        if escape:
                            escape = False
                            cur_str.append(ch)
                        elif ch == "\\":
                            escape = True
                            cur_str.append(ch)
                        elif ch == '"':
                            in_string = False
                            last_string = "".join(cur_str)
                        else:
                            cur_str.append(ch)
                        continue
                    if ch == '"':
                        in_string = True
                        cur_str = []
                    elif ch == ":":
                        last_key = last_string
                    elif ch == "{":
                        if stack and stack[-1] == "[":
                            capturing = True
                            depth = 1
                            buf = [ch]
                        else:
                            stack.append("{")
                    elif ch == "}":
                        if stack and stack[-1] == "{":
                            stack.pop()
                    elif ch == "[":
                        stack.append("[")
                        array_name_stack.append(last_key)
                    elif ch == "]":
                        if stack and stack[-1] == "[":
                            stack.pop()
                            if array_name_stack:
                                array_name_stack.pop()
    finally:
        for w in writers.values():
            w.close()
    return total


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python mesh_shards.py <src.json> <out_dir>")
        print("  Splits group-aware: foliage -> fol_*.jsonl, actors -> sm_*.jsonl")
        sys.exit(1)
    n = split_json_file(sys.argv[1], sys.argv[2])
    print(f"Split {n} entries into shards under {sys.argv[2]} "
          f"(actors -> sm_*, foliage -> fol_*)")
