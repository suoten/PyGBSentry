#!/usr/bin/env python3
"""P1-34: HashChain audit log verifier.

Verifies the integrity of the hash-chained audit log produced by
``HashChainSink`` (see ``backend/app/main.py``).

The audit log is JSON-lines, where each line has the shape::

    {"timestamp": "...", "level": "...", "module": "...",
     "message": "...", "prev_hash": "...", "hash": "..."}

Integrity rules verified:
  1. Each entry's ``prev_hash`` equals the previous entry's ``hash``
     (the very first entry's ``prev_hash`` must be ``"0" * 64``).
  2. Each entry's ``hash`` equals the SHA256 of the JSON encoding of the
     entry *without* the ``hash`` field, i.e.::

         sha256(json.dumps(
             {"timestamp": ..., "level": ..., "module": ...,
              "message": ..., "prev_hash": ...},
             ensure_ascii=False,
         ).encode("utf-8")).hexdigest()

This mirrors exactly how ``HashChainSink.write`` computes the hash, including
key insertion order and default JSON separators (``", "`` / ``": "``).

Usage::

    python verify_hash_chain.py --file /app/logs/audit.log

Exits with code 0 when the chain is intact, code 1 when any broken link or
malformed entry is detected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any, Dict, List, Optional, Tuple

GENESIS_HASH = "0" * 64

# Fields that form the signed payload, in the exact insertion order used by
# HashChainSink.write. The ``hash`` field is intentionally excluded.
SIGNED_FIELDS = ("timestamp", "level", "module", "message", "prev_hash")


def _compute_hash(entry: Dict[str, Any]) -> str:
    """Recompute the SHA256 hash for an entry the same way HashChainSink does."""
    payload = {field: entry[field] for field in SIGNED_FIELDS}
    entry_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(entry_bytes).hexdigest()


def _load_entries(path: str) -> List[Tuple[int, str]]:
    """Read the audit log file and return (line_number, raw_line) for non-blank lines."""
    entries: List[Tuple[int, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            entries.append((line_no, stripped))
    return entries


def verify_chain(path: str) -> bool:
    """Verify the hash chain of the audit log at ``path``.

    Returns ``True`` if the chain is intact, ``False`` otherwise. Details about
    any problems are printed to stdout.
    """
    try:
        entries = _load_entries(path)
    except OSError as e:
        print(f"[ERROR] Cannot read file '{path}': {e}")
        return False

    if not entries:
        print(f"[INFO] File '{path}' contains no audit entries. Chain is trivially intact.")
        return True

    print(f"[INFO] Verifying {len(entries)} audit entr{'y' if len(entries) == 1 else 'ies'} from '{path}'...")

    # The hash value that the current entry's ``prev_hash`` field must equal.
    # ``None`` means the anchor was lost (e.g. previous entry malformed) and
    # linkage can no longer be checked, although per-entry hash recomputation
    # still runs.
    expected_prev_hash: Optional[str] = GENESIS_HASH
    prev_line_no: Optional[int] = None
    broken = False
    verified = 0

    for line_no, raw in entries:
        # 1. Parse the JSON line.
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[BROKEN] line {line_no}: malformed JSON ({e.msg})")
            broken = True
            expected_prev_hash = None
            prev_line_no = line_no
            continue

        if not isinstance(entry, dict):
            print(f"[BROKEN] line {line_no}: JSON is not an object")
            broken = True
            expected_prev_hash = None
            prev_line_no = line_no
            continue

        # 2. Ensure all required fields are present.
        missing = [f for f in SIGNED_FIELDS + ("hash",) if f not in entry]
        if missing:
            print(f"[BROKEN] line {line_no}: missing field(s): {', '.join(missing)}")
            broken = True
            expected_prev_hash = None
            prev_line_no = line_no
            continue

        current_hash = entry["hash"]
        entry_prev_hash = entry["prev_hash"]

        # 3. Linkage check: this entry's prev_hash must equal the previous
        #    entry's hash (or the genesis hash for the first entry).
        linkage_ok = True
        if expected_prev_hash is None:
            print(
                f"[BROKEN] line {line_no}: linkage cannot be verified — previous entry "
                f"(line {prev_line_no}) was malformed; prev_hash='{entry_prev_hash}'"
            )
            linkage_ok = False
            broken = True
        elif entry_prev_hash != expected_prev_hash:
            if prev_line_no is None:
                detail = f"expected genesis hash '{GENESIS_HASH}'"
            else:
                detail = f"expected previous hash '{expected_prev_hash}' (from line {prev_line_no})"
            print(
                f"[BROKEN] line {line_no}: prev_hash mismatch — got '{entry_prev_hash}', {detail}"
            )
            linkage_ok = False
            broken = True

        # 4. Hash recomputation check (independent of linkage): the recorded
        #    ``hash`` must equal the SHA256 of the signed payload.
        hash_ok = True
        try:
            recomputed = _compute_hash(entry)
        except KeyError as e:
            print(f"[BROKEN] line {line_no}: missing signed field while hashing: {e}")
            hash_ok = False
            broken = True
        else:
            if recomputed != current_hash:
                print(
                    f"[BROKEN] line {line_no}: hash mismatch — recorded '{current_hash}' "
                    f"does not match recomputed '{recomputed}' (entry may be tampered)"
                )
                hash_ok = False
                broken = True

        if linkage_ok and hash_ok:
            verified += 1

        # Advance: the next entry's prev_hash should match this entry's recorded hash.
        expected_prev_hash = current_hash
        prev_line_no = line_no

    if broken:
        print(
            f"[FAIL] Chain verification FAILED — {verified} of {len(entries)} "
            f"entr{'y was' if verified == 1 else 'ies were'} fully verified."
        )
        return False

    print(
        f"[OK] Chain intact — all {verified} of {len(entries)} "
        f"entr{'y' if verified == 1 else 'ies'} verified successfully."
    )
    return True


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the integrity of a PyGBSentry HashChain audit log.",
    )
    parser.add_argument(
        "--file",
        required=True,
        help="Path to the audit.log file (JSON lines produced by HashChainSink).",
    )
    args = parser.parse_args(argv)

    ok = verify_chain(args.file)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
