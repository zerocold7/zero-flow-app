"""Speech-recognition benchmark: run the engine's own transcription on the test clips
and score what comes out.

    venv\\Scripts\\python.exe tools\\bench\\make_clips.py          (once)
    venv\\Scripts\\python.exe tools\\bench\\bench_stt.py --label before
    venv\\Scripts\\python.exe tools\\bench\\bench_stt.py --label turbo --model mobiuslabsgmbh/faster-whisper-large-v3-turbo
    venv\\Scripts\\python.exe tools\\bench\\bench_stt.py --compare before after

Scores, per language and condition:
  errors    character error rate against what was said (punctuation, case, Arabic
            vowel marks and letter variants such as أ/إ/ا ignored)
  ends .    share of sentences ending in a full stop or question mark
  invented  clips with words that were never said: a tail after the real sentence
            ("... before Friday afternoon. Thank you."), or any text at all from a
            clip with no speech in it
  time      seconds spent transcribing, per clip

Uses the engine's settings from .env (model, device) unless --model is given. Results
go to tools/bench/results/<label>.json (git-ignored).
"""
import argparse
import difflib
import json
import os
import re
import sys
import time


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CLIPS = os.path.join(HERE, "clips")
RESULTS = os.path.join(HERE, "results")

ARABIC_MARKS = re.compile(r"[ً-ْٰـ]")
PUNCT = re.compile(r"[^\w\s]|_")


def normalise(text, lang):
    text = text.lower()
    if lang == "ar":
        text = ARABIC_MARKS.sub("", text)
        for variants, plain in (("أإآ", "ا"), ("ى", "ي"), ("ة", "ه")):
            text = re.sub(f"[{variants}]", plain, text)
    return " ".join(PUNCT.sub(" ", text).split())


def edit_distance(a, b):
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def invented_tail(ref, hyp):
    """Words the transcript has beyond the end of what was said.

    After the last word both share, the transcript may still hold a misheard version of
    the sentence's last words ("nine" as "9") — those are errors, not inventions. Only
    words past that count: "... before friday afternoon thank you" invents two."""
    r, h = ref.split(), hyp.split()
    blocks = [b for b in difflib.SequenceMatcher(None, r, h, autojunk=False).get_matching_blocks()
              if b.size]
    if not blocks:
        return h if not r else []
    last = blocks[-1]
    extra = len(h) - (last.b + last.size) - (len(r) - (last.a + last.size))
    return h[len(h) - extra:] if extra > 0 else []


def score(case, hyp):
    lang, ref = case["lang"], case["ref"]
    if not ref:
        return {"invented": bool(hyp.strip()), "extra": hyp.strip()}
    nref, nhyp = normalise(ref, lang), normalise(hyp or "", lang)
    tail = invented_tail(nref, nhyp)
    return {
        "chars": len(nref),
        "errors": edit_distance(nref, nhyp),
        "ends": bool(re.search(r"[.?!؟]\s*$", hyp or "")),
        "invented": bool(tail),
        "extra": " ".join(tail),
    }


def run(label, model_name, runs, clips=CLIPS, no_filter=False, vocabulary=False):
    if model_name:
        os.environ["WHISPER_MODEL_NAME"] = model_name
    os.environ.setdefault("ZEROFLOW_LOG_DIR", os.path.join(RESULTS, "logs"))
    os.makedirs(os.environ["ZEROFLOW_LOG_DIR"], exist_ok=True)
    sys.path.insert(0, ROOT)
    from zeroflow import stt     # after the overrides above: settings are read on import
    import soundfile as sf

    if not vocabulary:                               # the same hint on every PC
        stt.load_vocabulary = lambda: []
    if no_filter:                                    # the engine before 2.0 phase 2
        stt.trim_invented_ending = lambda words, audio: words
    stt.model = stt.load_whisper_model()
    cases = json.load(open(os.path.join(clips, "index.json"), encoding="utf-8"))
    rows = []
    for attempt in range(runs):
        for case in cases:
            audio, _ = sf.read(os.path.join(clips, case["file"]), dtype="float32")
            started = time.perf_counter()
            text, _ = stt.transcribe_audio(audio, case["lang"])
            took = time.perf_counter() - started
            rows.append({**case, "run": attempt, "hyp": text or "", "seconds": took,
                         **score(case, text or "")})
            mark = "!" if rows[-1]["invented"] else " "
            print(f"{mark} {case['file']:<26} {case['lang']} {took:5.2f}s  {(text or '')[:70]}")
    result = {"label": label, "model": stt.WHISPER_MODEL_NAME,
              "runtime": stt.model_runtime, "runs": runs, "rows": rows}
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, f"{label}.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result


def summary(result):
    groups = {}
    for row in result["rows"]:
        groups.setdefault((row["lang"], row["condition"]), []).append(row)
    table = {}
    for key, rows in sorted(groups.items()):
        speech = [r for r in rows if "chars" in r]
        table[key] = {
            "n": len(rows),
            "errors": (sum(r["errors"] for r in speech) / sum(r["chars"] for r in speech)
                       if speech else None),
            "ends": sum(r["ends"] for r in speech) / len(speech) if speech else None,
            "invented": sum(r["invented"] for r in rows),
            "time": sum(r["seconds"] for r in rows) / len(rows),
        }
    return table


def show(result):
    print(f"\n{result['label']}: {result['model']} · {result['runtime']} · {result['runs']} run(s)")
    print(f"{'':<16}{'n':>4}{'errors':>9}{'ends .':>9}{'invented':>10}{'time':>8}")
    for (lang, cond), s in summary(result).items():
        err = f"{s['errors']:.1%}" if s["errors"] is not None else "—"
        ends = f"{s['ends']:.0%}" if s["ends"] is not None else "—"
        print(f"{lang + ' ' + cond:<16}{s['n']:>4}{err:>9}{ends:>9}{s['invented']:>10}{s['time']:>7.2f}s")
    examples = [r for r in result["rows"] if r["invented"]]
    if examples:
        print("\ninvented text:")
        for r in examples:
            print(f"  {r['file']:<26} {r['lang']}  «{r['extra']}»")


def compare(a, b):
    sa, sb = summary(a), summary(b)
    print(f"\n{a['label']} → {b['label']}")
    print(f"{'':<16}{'errors':>18}{'ends .':>14}{'invented':>12}{'time':>16}")
    for key in sa:
        x, y = sa[key], sb.get(key)
        if not y:
            continue
        err = (f"{x['errors']:.1%} → {y['errors']:.1%}" if x["errors"] is not None else "—")
        ends = (f"{x['ends']:.0%} → {y['ends']:.0%}" if x["ends"] is not None else "—")
        print(f"{key[0] + ' ' + key[1]:<16}{err:>18}{ends:>14}"
              f"{str(x['invented']) + ' → ' + str(y['invented']):>12}"
              f"{x['time']:>7.2f} → {y['time']:.2f}s")


def load(label):
    with open(os.path.join(RESULTS, f"{label}.json"), encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--label", default="run")
    parser.add_argument("--model", help="a WHISPER_MODEL_NAME to try instead of .env's")
    parser.add_argument("--runs", type=int, default=1, help="repeat every clip this often")
    parser.add_argument("--clips", default="clips",
                        help="folder under tools/bench: clips (synthetic) or mine (your voice)")
    parser.add_argument("--vocabulary", action="store_true",
                        help="prime Whisper with this PC's vocabulary, as the engine does")
    parser.add_argument("--no-filter", action="store_true",
                        help="leave invented endings in, to compare with the filter on")
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    parser.add_argument("--show", metavar="LABEL", help="print a saved result again")
    args = parser.parse_args()
    if args.compare:
        compare(load(args.compare[0]), load(args.compare[1]))
    elif args.show:
        show(load(args.show))
    else:
        show(run(args.label, args.model, args.runs, os.path.join(HERE, args.clips),
                 args.no_filter, args.vocabulary))
