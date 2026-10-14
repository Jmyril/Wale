"""Feed Wale some reading material.

Point it at text files, subtitle files, or whole folders of conversation data
and it will pull out clean, lowercase sentences and either:

  --brain   learn the word pairs from them into Wale's memory
            (models/user_brain.json). Sentences are folded into bigram/
            trigram counts + sentence-form stats and then discarded, so the
            bot can never parrot a whole line back. Good for short chat lines
            like "hey what's up" that the quote filter would drop.
  --theme   drop them into a corpus folder (data/my_quotes/<theme>/) for the
            Markov core to read like any other theme.

Examples
--------
    # learn from a folder of movie dialogue
    python3 src/ingest.py ~/data/dailydialog --brain

    # build a new theme corpus from subtitle files
    python3 src/ingest.py ~/subs/*.srt --theme movies --name subtitles

    # pipe text straight in
    cat dialogue.txt | python3 src/ingest.py - --brain

    # rebuild the locked base from a quote theme corpus
    python3 src/ingest.py --from-theme general --brain --store models/learned_pairs.json
"""

import argparse
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

import learning  # noqa: E402

DEFAULT_MIN = 2
DEFAULT_MAX = 24

_SRT_TIME = re.compile(r"^\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}")
_SPEAKER = re.compile(r"^[A-Z][A-Za-z0-9 .'_-]{0,24}:\s*")
_MARKUP = re.compile(r"\{\\[^}]*\}|<[^>]+>|\[[^\]]*\]|\([^)]*\)")


def read_texts(paths):
    """Yield (name, text) for every input file (or the piped stdin)."""
    for path in paths:
        if path == "-":
            yield "<stdin>", sys.stdin.read()
            continue
        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for name in sorted(files):
                    if name.lower().endswith((".txt", ".srt", ".md", ".text")):
                        full = os.path.join(root, name)
                        yield full, _read(full)
        else:
            yield path, _read(path)


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as exc:
        print(f"  ! skipped {path}: {exc}", file=sys.stderr)
        return ""


def strip_srt(text):
    """Kill subtitle index/time lines so only the spoken lines remain."""
    kept = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.isdigit() or "-->" in s or _SRT_TIME.match(s):
            continue
        kept.append(s)
    return "\n".join(kept)


def clean(text):
    text = strip_srt(text)
    text = _MARKUP.sub(" ", text)          # drop stage directions, tags
    out_lines = []
    for line in text.splitlines():
        line = _SPEAKER.sub("", line.strip())   # "JOHN: hello" -> "hello"
        line = line.lstrip("-*>#").strip()
        if line:
            out_lines.append(line)
    text = " ".join(out_lines)
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"[^a-zA-Z'\s.,!?;]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def sentences(text, lo, hi):
    for chunk in re.split(r"(?<=[.!?;])\s+", clean(text)):
        tokens = learning.tokenize(chunk)
        if not (lo <= len(tokens) <= hi):
            continue
        if not any(t.isalpha() for t in tokens):
            continue
        yield tokens


def render(tokens):
    return re.sub(r"\s+([.,!?;])", r"\1", " ".join(tokens))


def main():
    ap = argparse.ArgumentParser(description="Ingest conversation text into Wale.")
    ap.add_argument("inputs", nargs="*", help="files, folders, or - for stdin")
    ap.add_argument("--brain", action="store_true", help="learn word pairs into a memory store")
    ap.add_argument("--store", help="memory path for --brain (default models/user_brain.json)")
    ap.add_argument("--theme", help="write a corpus file into data/my_quotes/<theme>/")
    ap.add_argument("--name", default="corpus", help="corpus filename (with --theme)")
    ap.add_argument("--from-theme", help="build from a quote theme corpus (uses the quote filters)")
    ap.add_argument("--min-tokens", type=int, default=DEFAULT_MIN)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX)
    ap.add_argument("--out", help="explicit output path (overrides --theme/--name)")
    args = ap.parse_args()

    if not args.brain and not args.theme and not args.out:
        ap.error("choose at least one of --brain / --theme / --out")
    if not args.inputs and not args.from_theme:
        ap.error("give some inputs, or use --from-theme")

    seen = set()
    kept = []
    total_files = 0

    if args.from_theme:
        import quote_generator as qg
        for tokens in qg._clean_corpus_sentences(args.from_theme):
            key = " ".join(tokens)
            if key in seen:
                continue
            seen.add(key)
            kept.append(tokens)
        print(f"  theme '{args.from_theme}': +{len(kept)} sentences")
    else:
        for name, text in read_texts(args.inputs):
            total_files += 1
            n_before = len(kept)
            for tokens in sentences(text, args.min_tokens, args.max_tokens):
                key = " ".join(tokens)
                if key in seen:
                    continue
                seen.add(key)
                kept.append(tokens)
            print(f"  {name}: +{len(kept) - n_before} sentences")

    if not kept:
        print("Nothing survived filtering. Loosen --min-tokens/--max-tokens?", file=sys.stderr)
        return 1

    if args.out or args.theme:
        theme = args.theme or "general"
        out_path = args.out or os.path.join(BASE_DIR, "data", "my_quotes", theme, f"{args.name}.txt")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for tokens in kept:
                f.write(render(tokens) + "\n")
        print(f"wrote {len(kept)} sentences -> {out_path}")

    if args.brain:
        brain = learning.UserBrain(path=args.store) if args.store else learning.UserBrain()
        added = 0
        for tokens in kept:
            if brain.has_seen(tokens):
                continue
            if brain.learn(tokens):
                added += 1
        brain._save()
        pairs = sum(len(v) for v in brain.bigrams.values())
        print(f"taught Wale {added} new sentences as word-pairs -> {brain.path}")
        print(f"  ({pairs} distinct word pairs now stored, zero sentences kept)")

    print(f"done: {total_files} file(s), {len(kept)} unique sentences.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
