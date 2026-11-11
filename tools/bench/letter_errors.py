"""Which letters does Dictation get wrong? Lists every word that came out different from
what was said, letter by letter, from a saved bench_stt result.

    venv\\Scripts\\python.exe tools\\bench\\record_mine.py                  (your own voice, once)
    venv\\Scripts\\python.exe tools\\bench\\bench_stt.py --clips mine --label mine-now
    venv\\Scripts\\python.exe tools\\bench\\letter_errors.py mine-now [ar|en]

It ends with the swaps that repeat (ب→ف, ق→ك …) and how many wrong words differ in
their FIRST letter. Run it after a change to the engine's speech path (the model, its
precision, the hint) and compare the two summaries: that is the test for "some letters
of the words I say come out wrong". The clips are the same audio each time, so a
different answer is the engine's, not the microphone's.
"""
import difflib
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
MARKS = re.compile(r"[ً-ْٰـ]")
PUNCT = re.compile(r"[^\w\s]|_")


def words(text: str) -> list[str]:
    return PUNCT.sub("", MARKS.sub("", text.lower())).split()


def wrong_words(ref: str, hyp: str) -> list[tuple[str, str]]:
    """(said, heard) for each word that differs, where the two line up one to one."""
    a, b = words(ref), words(hyp)
    pairs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "replace" and i2 - i1 == j2 - j1:
            pairs += list(zip(a[i1:i2], b[j1:j2], strict=True))
    return pairs


def letter_swaps(said: str, heard: str) -> list[tuple[str, str, int]]:
    """(letter said, letter heard, position) for each letter that was swapped."""
    swaps = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, said, heard, autojunk=False).get_opcodes():
        if tag == "replace" and i2 - i1 == j2 - j1:
            swaps += [(said[i1 + k], heard[j1 + k], i1 + k) for k in range(i2 - i1)]
    return swaps


def main(label: str, lang: str | None) -> None:
    with open(os.path.join(HERE, "results", f"{label}.json"), encoding="utf-8") as f:
        rows = [r for r in json.load(f)["rows"] if r.get("hyp") and (lang is None or r["lang"] == lang)]
    counts, first, total = Counter(), 0, 0
    for row in rows:
        for said, heard in wrong_words(row["ref"], row["hyp"]):
            swaps = letter_swaps(said, heard)
            total += 1
            first += any(position == 0 for _, _, position in swaps)
            counts.update((a, b) for a, b, _ in swaps)
            print(f"{row['file']:<18} said {said}  heard {heard}   "
                  + " ".join(f"{a}→{b}" for a, b, _ in swaps or [("?", "?", 0)]))
    print(f"\n{label}: {len(rows)} clips, {total} wrong words, {first} of them wrong in the first letter")
    for (a, b), n in counts.most_common(8):
        print(f"  {a} → {b}   {n}x")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
