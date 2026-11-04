"""Every link between the guides leads somewhere.

Each explanation lives in one place and the others point to it ("see HARDWARE.md §4"),
so a pointer whose file or heading was renamed would leave the reader at a dead end.
Checks every relative link in the Markdown files — the file, and the #heading anchor
as GitHub builds it from the heading's text.
"""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$", re.MULTILINE)
CODE = re.compile(r"```.*?```", re.DOTALL)


def markdown_files() -> list[str]:
    tracked = subprocess.run(["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.split()
    return [os.path.join(ROOT, name) for name in tracked]


def anchors(path: str) -> set[str]:
    """The #anchors GitHub gives this file's headings: lower case, punctuation and
    emoji dropped, spaces to hyphens, a repeated heading numbered -1, -2, ..."""
    with open(path, encoding="utf-8") as f:
        text = CODE.sub("", f.read())
    seen, found = {}, set()
    for heading in HEADING.findall(text):
        heading = re.sub(r"`|\*\*|\*|<[^>]+>", "", heading)
        heading = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
        slug = re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        found.add(slug if count == 0 else f"{slug}-{count}")
    return found


class TestLinks(unittest.TestCase):
    def test_every_relative_link_leads_to_a_file_and_heading(self):
        broken = []
        for path in markdown_files():
            with open(path, encoding="utf-8") as f:
                text = CODE.sub("", f.read())
            for target in LINK.findall(text):
                if re.match(r"^[a-z]+:", target):            # https:, mailto:
                    continue
                file_part, _, anchor = target.partition("#")
                linked = os.path.normpath(os.path.join(os.path.dirname(path), file_part)) \
                    if file_part else path
                where = os.path.relpath(path, ROOT)
                if not os.path.exists(linked):
                    broken.append(f"{where}: {target} (no such file)")
                elif anchor and linked.endswith(".md") and anchor not in anchors(linked):
                    broken.append(f"{where}: {target} (no such heading)")
        self.assertEqual(broken, [])


if __name__ == "__main__":
    unittest.main()
