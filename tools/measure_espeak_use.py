"""Phase 7, the espeak-ng decision: how many words the Reader hands to espeak-ng (the
GPL-3 fallback for words outside Kokoro's English dictionary), and which ones.

    venv\\Scripts\\python tools\\measure_espeak_use.py [text files ...]

Without files it reads the project's own English docs. Without espeak those words
are skipped (kokoro: "OOD words will be skipped"), so this is the share of words a
Reader without espeak would leave out.
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = ["README.md", "CONTEXT.md", "ARCHITECTURE.md", "CONFIGURATION.md", "docs/*.md"]


class Counting:
    def __init__(self, inner):
        self.inner, self.words = inner, []

    def __call__(self, token):
        self.words.append(token.text)
        return self.inner(token)


def plain(text: str) -> str:
    """Markdown down to readable prose: no code, links, tables or markup."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[|#*_>]", " ", text)
    return re.sub(r"[^\x00-\x7f]", " ", text)          # English only: drop Arabic


def main(paths):
    from misaki import en, espeak
    fallback = Counting(espeak.EspeakFallback(british=False))
    g2p = en.G2P(trf=False, british=False, fallback=fallback, unk="")
    files = paths or [f for p in DEFAULT for f in glob.glob(os.path.join(ROOT, p))]
    total = 0
    for path in files:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = plain(f.read())
        for paragraph in (p for p in text.split("\n\n") if p.strip()):
            _, tokens = g2p(" ".join(paragraph.split()))
            total += sum(1 for t in tokens if re.search(r"[A-Za-z]", t.text))
    words = fallback.words
    print(f"files: {len(files)}, words read: {total}, sent to espeak: {len(words)} "
          f"({100 * len(words) / max(total, 1):.2f}%)")
    unique = sorted(set(words), key=str.lower)
    print(f"distinct: {len(unique)}: {', '.join(unique[:80])}")


if __name__ == "__main__":
    main(sys.argv[1:])
