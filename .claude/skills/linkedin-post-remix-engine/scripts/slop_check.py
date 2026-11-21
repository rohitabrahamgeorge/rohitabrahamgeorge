"""Mechanical AI-slop lint for a draft post (first gate only).

  python slop_check.py draft.txt [--source source.txt]

This catches the patterns a regex can see. It does NOT replace the Kinner comment
engine's Phase 5 audit loop, which still has to be run by reading the draft.
Exit code 1 if any hard failure is found.
"""
import re
import sys

HARD = {
    "em dash": r"—|–",
    "ampersand": r"&",
    "negation pivot (not X, it's Y)": r"\b(it'?s|this is|that'?s)\s+not\s+(about\s+)?[^.?!\n]{1,60}[,;.]\s*(it'?s|it is|but|this is)\b"
                                      r"|\bnot\s+(because|about)\b[^.?!\n]{1,60}\bbut\b|\bisn'?t\s+[^.?!\n]{1,40}[.,]\s*it'?s\b",
    "stance announcement": r"\b(hot take|unpopular opinion|i'?d push back|let me be clear|here'?s the thing|"
                           r"let that sink in|read that again)\b",
    "two-camp split": r"\b(the ones who|those who)\b[^.\n]{3,80}[.,;]\s*(the rest|everyone else|those who|the ones who)\b"
                      r"|\bsome (will|people)\b[^.\n]{3,80}\bothers\b",
}
VOCAB = ["leverage", "synergize", "delve", "dive deep", "deep dive", "landscape", "tapestry", "game-changer",
         "game changer", "unlock", "unleash", "elevate", "supercharge", "seamless", "robust", "furthermore",
         "moreover", "indeed", "certainly", "in conclusion", "to summarize", "navigate the", "realm",
         "ever-evolving", "fast-paced", "in today's", "it's important to note", "harness", "empower",
         "revolutionize", "paradigm", "testament", "pivotal", "foster", "transformative",
         "touch base", "i'd be happy to", "don't hesitate", "at the end of the day", "the secret sauce",
         "buckle up", "here's why", "here's how", "spoiler", "the truth is", "plot twist", "full stop"]
SOFT = {
    "ends on a question": lambda t, L: L and L[-1].rstrip().endswith("?"),
    "reflex tricolon (X, Y, and Z.)": lambda t, L: len(re.findall(r"\b\w+, \w+,? and \w+[.!]", t)) >= 2,
    "metronome rhythm (5+ one-line paragraphs in a row under 8 words)":
        lambda t, L: re.search(r"(?:^[^\n]{1,45}\n\n?){5,}", t, re.M) is not None,
    "too many emoji (>2)": lambda t, L: len(re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", t)) > 2,
    "arrow/checkmark bullets": lambda t, L: re.search(r"^\s*(→|➡|✅|✔|👉|🔥)", t, re.M) is not None,
}


def main():
    path = sys.argv[1]
    text = open(path).read()
    src = open(sys.argv[sys.argv.index("--source") + 1]).read() if "--source" in sys.argv else ""
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    low = text.lower()
    fails, warns = [], []
    for name, rx in HARD.items():
        for m in re.finditer(rx, text, re.I):
            fails.append(f"{name}: …{text[max(0, m.start() - 30):m.end() + 30]!r}…")
    for w in VOCAB:
        if re.search(r"\b" + re.escape(w) + r"\b", low):
            fails.append(f"banned word: {w!r}")
    for name, fn in SOFT.items():
        if fn(text, lines):
            warns.append(name)
    if src:  # verbatim carry-over from the source post
        def sents(t):
            return [s.strip().lower() for s in re.split(r"(?<=[.!?])\s+|\n+", t) if len(s.split()) >= 7]
        ss = set(sents(src))
        copied = [s for s in sents(text) if s in ss]
        for s in copied:
            fails.append(f"copied verbatim from source: {s[:90]!r}")
    print("HARD FAILS:" if fails else "HARD FAILS: none")
    for f in fails:
        print("  x", f)
    print("REVIEW:" if warns else "REVIEW: none")
    for w in warns:
        print("  ?", w)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
