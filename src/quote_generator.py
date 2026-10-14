import random
import argparse
import os
import json
import re
import base64
import hashlib
import pickle
import sys
import subprocess
from collections import Counter
from datetime import datetime

import pos_tagger as pt

# ---------------------------------------------------------------------------
# Corpus & n-gram config
# ---------------------------------------------------------------------------
_DEFAULT_CORPUS = [
    "data/my_quotes/general/fortune_corpus.txt",
    "data/my_quotes/general/real_quotes.txt",
]
_MY_QUOTES_ROOT = "data/my_quotes"
_MARKOV = {}

_SEED_MAP_PATH = "models/seed_map.json"
_SEP = "\x1f"
_END_PUNCT = {".", "!", "?"}
_BAD_START = {".", ",", ";", "!", "?", "'s", "'", "qotd", "qotd:",
              "of", "by", "in", "on", "at", "with", "from", "for", "under",
              "through", "beyond", "between", "within", "into", "without"}
_JUNK_TOKENS = {
    "knghtbrd", "swanson", "smirnoff", "hardcore", "paradoxum",
    "dells", "hanukkah", "pcline", "gosper", "linus", "bankhead",
}
_TECH_WORDS = {
    "debian", "linux", "kernel", "perl", "python", "cobol", "fortran",
    "program", "programs", "programmer", "programmers", "programming",
    "unix", "sysadmin", "sysadmins", "hacker", "hackers", "hacking",
    "glibc", "gcc", "irc", "emacs", "windows", "microsoft", "computer",
    "computers", "software", "hardware", "shell", "compiler", "code",
    "debug", "debugging", "bugs", "elisp", "bsd", "cdrom", "disk",
    "dist", "byte", "bytes", "modem", "internet", "rec.games",
}


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------
def _corpus_files_for(theme):
    """Prefer every *.txt under data/my_quotes/<theme>/, else the default corpus."""
    theme_dir = os.path.join(_MY_QUOTES_ROOT, theme)
    if os.path.isdir(theme_dir):
        files = sorted(os.path.join(theme_dir, f) for f in os.listdir(theme_dir) if f.endswith(".txt"))
        if files:
            return files
    return _DEFAULT_CORPUS


def _clean_corpus_sentences(theme="general"):
    verbs = {"is", "are", "was", "were", "can", "will", "must", "should",
             "would", "could", "may", "might", "don't", "won't", "have",
             "has", "had", "be", "been", "do", "does", "did", "become",
             "becomes", "need"}
    sents = []
    for path in _corpus_files_for(theme):
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8", errors="ignore"):
            orig = line.strip()
            if not orig:
                continue
            if any(ch.isdigit() for ch in orig):
                continue
            if any(not (ch.isalpha() or ch.isspace() or ch in ".,!?;-'") for ch in orig):
                continue
            if ":" in orig or "#" in orig:
                continue
            if any(re.match(r"[A-Z][a-z]{2,}", w) for w in orig.split()[1:]):
                continue
            s = orig.lower()
            toks = re.findall(r"[a-z']+|[.,!?;]", s)
            if len(toks) < 5 or len(toks) > 16:
                continue
            if toks[-1] not in _END_PUNCT:
                continue
            if any(len(w) > 11 for w in toks):
                continue
            if toks[0] in _BAD_START:
                continue
            if any(w in _JUNK_TOKENS or w in _TECH_WORDS for w in toks):
                continue
            if not any(w in verbs or pt.assign_role_by_pattern(w) in ("VERB", "VING", "MODAL") for w in toks):
                continue
            sents.append(toks)
    return sents


def _base_path(theme="general"):
    themed = os.path.join("models", f"learned_pairs_{theme}.json")
    if os.path.exists(themed):
        return themed
    return os.path.join("models", "learned_pairs.json")


# The locked base is a multi-megabyte JSON blob parsed on every cold start.
# We cache the parsed dict as a pickle keyed by the source file's mtime+size,
# so repeat boots skip the parse. The JSON stays the source of truth; the
# cache is disposable and lives under .cache/ (gitignored).
_CACHE_DIR = os.path.join("models", ".cache")
_CACHE_KEEP = 6


def _prune_model_cache(keep=_CACHE_KEEP):
    try:
        entries = [
            os.path.join(_CACHE_DIR, f)
            for f in os.listdir(_CACHE_DIR) if f.endswith(".pkl")
        ]
        if len(entries) <= keep:
            return
        entries.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for path in entries[keep:]:
            try:
                os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


def _load_base_data(path):
    """Load the base JSON, transparently serving/warming a pickle cache."""
    cache = None
    try:
        st = os.stat(path)
        cache = os.path.join(
            _CACHE_DIR, f"{os.path.basename(path)}.{int(st.st_mtime)}.{st.st_size}.pkl"
        )
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                return pickle.load(f)
    except Exception:
        cache = None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if cache:
        try:
            os.makedirs(_CACHE_DIR, exist_ok=True)
            tmp = cache + ".tmp"
            with open(tmp, "wb") as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, cache)
            _prune_model_cache()
        except Exception:
            pass
    return data


def _load_markov(theme="general"):
    """Load the *locked* base: word-pair + sentence-form statistics only.

    No sentence is stored or read here — the base is frozen data that the bot
    never writes back to.
    """
    if theme in _MARKOV:
        return _MARKOV[theme]
    data = _load_base_data(_base_path(theme))
    starts = Counter(data.get("starts", {}))
    f1 = {w: Counter(c) for w, c in data.get("bigrams", {}).items()}
    f2 = {}
    for key, nxt in data.get("trigrams", {}).items():
        a, _, b = key.partition(_SEP)
        f2[(a, b)] = Counter(nxt)
    markov = {"starts": starts, "f1": f1, "f2": f2}
    _MARKOV[theme] = markov
    return markov


# ---------------------------------------------------------------------------
# Token-level sampling: each next word comes from the previous tokens only.
# Chaos is reinterpreted as sampling temperature (no word substitution).
# ---------------------------------------------------------------------------
# Optional truncation on top of temperature sampling: keep only the top-K
# candidates and/or the smallest set whose scaled mass reaches top-P. Both are
# off by default; enable with WALE_TOP_K / WALE_TOP_P. This prunes the long
# tail of bizarre continuations without touching the corpus.
_TOP_K = int(os.environ.get("WALE_TOP_K", "0") or 0)
_TOP_P = float(os.environ.get("WALE_TOP_P", "0") or 0.0)


def _sample(keys, weights, temperature, top_k=None, top_p=None):
    if not keys:
        return None
    total = sum(weights)
    if total <= 0:
        return random.choice(keys)
    if temperature <= 0.05:
        best_idx = max(range(len(keys)), key=lambda i: weights[i])
        if weights[best_idx] / total >= 0.5:
            return keys[best_idx]
    if top_k is None:
        top_k = _TOP_K
    if top_p is None:
        top_p = _TOP_P
    scaled = [max(w, 1e-9) ** (1.0 / max(temperature, 1e-3)) for w in weights]
    order = sorted(range(len(keys)), key=lambda i: scaled[i], reverse=True)
    if top_k and top_k > 0:
        order = order[:top_k]
    if top_p and 0.0 < top_p < 1.0:
        mass = sum(scaled) or 1.0
        acc, kept = 0.0, []
        for i in order:
            kept.append(i)
            acc += scaled[i]
            if acc / mass >= top_p:
                break
        order = kept
    return random.choices([keys[i] for i in order],
                          weights=[scaled[i] for i in order], k=1)[0]


def _wc(counter, temperature=1.0, top_k=None, top_p=None):
    keys = list(counter.keys())
    if not keys:
        return None
    return _sample(keys, [counter[k] for k in keys], temperature, top_k, top_p)


def _next_token(m, tokens, temperature):
    """Blend trigram (70%) + bigram (30%) continuation from the previous tokens."""
    pairs = {}
    if len(tokens) >= 2:
        trig = m["f2"].get((tokens[-2], tokens[-1]))
        if trig:
            for tok, cnt in trig.items():
                pairs[tok] = pairs.get(tok, 0.0) + 0.7 * cnt
    bi = m["f1"].get(tokens[-1])
    if bi:
        for tok, cnt in bi.items():
            pairs[tok] = pairs.get(tok, 0.0) + 0.3 * cnt
    if not pairs:
        return None
    items = list(pairs.items())
    return _sample([t for t, _ in items], [w for _, w in items], temperature)


_NEUTRAL = ["quiet", "things", "still", "need", "tending", "."]


def build_sentence(theme="general", chaos=0.6):
    m = _load_markov(theme)
    temperature = 0.4 + chaos * 1.0
    for _ in range(30):
        w1 = _wc(m["starts"], temperature)
        if w1 is None or w1 in _BAD_START:
            continue
        toks = [w1]
        guard = 0
        while len(toks) < 20 and guard < 30:
            guard += 1
            nxt = _next_token(m, toks, temperature)
            if nxt is None:
                break
            if nxt in {",", ";", "!"}:
                if len(toks) >= 6:
                    break
                continue
            toks.append(nxt)
            if nxt in _END_PUNCT:
                break
        if len(toks) >= 5 and toks[-1] in _END_PUNCT:
            return toks
    return list(_NEUTRAL)


# ---------------------------------------------------------------------------
# Vowel-sound helpers for a/an
# ---------------------------------------------------------------------------
_SILENT_H = {"hour","hours","honest","honesty","honor","honour","honors","honours",
              "honorable","heir","heirs","heiress","herb","herbs","herbal","homage"}
_U_LONG = {"unit","units","unique","user","users","united","universal","universities",
           "university","uniform","uniforms","useful","usual","usually","union","unions",
           "utah","eunuch","euphemism","eulogy"}

def _is_vowel_sound(word):
    w = word.lower()
    if w in _SILENT_H:
        return True
    if w[0] in "aeiou" and w not in _U_LONG:
        return True
    return False


# ---------------------------------------------------------------------------
# Seeds (tracing)
# ---------------------------------------------------------------------------
def quote_to_seed(text):
    """Map a quote to a fixed-length seed (always 67 chars).

    Reversible only through the seed registry (models/seed_map.json), not by
    the seed itself. Hash is deterministic, so the same quote always yields the
    same 67-char seed on any machine.
    """
    seed = _seed_code(text)
    registry = _load_seed_registry()
    if seed not in registry:
        registry[seed] = text.strip()
        _save_seed_registry(registry)
    return seed


def seed_to_quote(seed):
    """Recover the quote behind a 67-char seed, or None if unknown."""
    if not seed:
        return None
    seed = seed.strip()
    registry = _load_seed_registry()
    q = registry.get(seed)
    if q:
        return q
    try:
        q = base64.urlsafe_b64decode(seed.encode("ascii")).decode("utf-8").strip()
        if len(q) >= 10 and q[-1] in ".!?":
            return q
    except Exception:
        pass
    return None


def _seed_code(text):
    """50-byte blake2b -> urlsafe base64, unpadded -> exactly 67 chars."""
    digest = hashlib.blake2b(text.strip().encode("utf-8"), digest_size=50).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _load_seed_registry():
    path = _SEED_MAP_PATH
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_seed_registry(registry):
    try:
        os.makedirs(os.path.dirname(_SEED_MAP_PATH), exist_ok=True)
        with open(_SEED_MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Post-processing
# ---------------------------------------------------------------------------
def fix_articles(text):
    words = text.split()
    out = []
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else None
        if w in ("a", "an") and nxt and nxt[0].isalpha():
            vs = _is_vowel_sound(nxt)
            if w == "a" and vs:
                out.append("an")
            elif w == "an" and not vs:
                out.append("a")
            else:
                out.append(w)
        else:
            out.append(w)
    return " ".join(out)


def fix_case(text):
    text = text.strip()
    words = text.split()
    words = ["I" if w == "i" else w for w in words]
    if words:
        words[0] = words[0].capitalize()
    text = " ".join(words)
    if text and text[-1] not in ".?!":
        text += "."
    text = text.replace("  ", " ").replace(" ,", ",").replace(" ?", "?").replace(" .", ".").replace(" ;", ";")
    return text


def sanity_check(text):
    words = [w for w in text.replace(",", " ").replace(";", " ").replace("—", " ").split()]
    if len(words) < 3:
        return False
    if max(len(w) for w in words) > 15:
        return False
    if sum(1 for w in words if len(w) > 10) > 1:
        return False
    verbs = {"is", "are", "was", "were", "can", "will", "must", "should", "could", "may", "might",
             "becomes", "seems", "do", "have", "had", "has", "don't", "never", "you", "what"}
    if not any(w in verbs or (w.isalpha() and pt.assign_role_by_pattern(w) in ("VERB", "VING", "MODAL")) for w in words):
        return False
    return True


# ---------------------------------------------------------------------------
# Generation entry points
# ---------------------------------------------------------------------------
def generate_phrase(theme="general", chaos=0.6):
    for _ in range(25):
        toks = build_sentence(theme, chaos)
        sentence = fix_articles(" ".join(toks))
        sentence = fix_case(sentence)
        if sanity_check(sentence):
            return sentence
    return "Quiet things still need tending."


def generate_full_quote(theme="general", chaos=0.6):
    return generate_phrase(theme, chaos)


def generate_paragraph(theme="general", num_sentences=8, chaos=0.6):
    transitions = ["Moreover, ", "Thus, ", "Yet, ", "In the end, ", "Therefore, ",
                   "Consequently, ", "Simply put, ", "Indeed, ", "Beyond this, "]
    paragraph = []
    for i in range(num_sentences):
        sentence = generate_full_quote(theme=theme, chaos=chaos)
        if i > 0 and random.random() < 0.5:
            trans = random.choice(transitions)
            sentence = trans + sentence[0].lower() + sentence[1:]
        paragraph.append(sentence)
    return " ".join(paragraph)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_quotes", type=int, default=5)
    parser.add_argument("--theme", default="general")
    parser.add_argument("--chaos", type=float, default=0.6, help="0..1 sampling temperature (0 = closest to corpus)")
    parser.add_argument("--paragraph", action="store_true")
    parser.add_argument("--sentences", type=int, default=8, help="Number of sentences in the paragraph")
    parser.add_argument("--raw", action="store_true", help="Print only the quote text")
    parser.add_argument("--svg", action="store_true", help="Export to a stylish SVG image")
    parser.add_argument("--image", action="store_true", help="Export to a professional PNG image (requires venv)")
    parser.add_argument("--seed", help="Reproduce a specific quote from its seed (use --to-seed to make one)")
    parser.add_argument("--to-seed", help="Print the seed for a given quote, then exit")
    parser.add_argument("--quote", help="Pump an outside quote straight through the pipeline (seed + optional svg/image)")
    args = parser.parse_args()

    if args.to_seed:
        print(quote_to_seed(args.to_seed))
        sys.exit(0)

    chaos = max(0.0, min(1.0, args.chaos))
    theme = args.theme if os.path.isdir(os.path.join("data", "my_quotes", args.theme)) else "general"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.paragraph:
        final_text = generate_paragraph(theme=theme, num_sentences=args.sentences, chaos=chaos)
        if args.raw:
            print(final_text)
        else:
            print(f"\n--- [THEME: {theme.upper()}] DEEP PERSPECTIVE ---\n")
            print(final_text)
            print("\n" + "=" * 60 + "\n")
        base_name = f"paragraph_{theme.upper()}_{timestamp}"
        if args.svg:
            from svg_generator import generate_svg
            generate_svg(final_text, theme=theme.upper(), output_path=f"{base_name}.svg")
        if args.image:
            output_dir = "output_images"
            if not os.path.exists(output_dir): os.makedirs(output_dir)
            out_path = os.path.join(output_dir, f"{base_name}.png")
            venv_python = os.path.join(os.getcwd(), "venv", "bin", "python")
            if os.path.exists(venv_python):
                subprocess.run([venv_python, "src/image_generator.py", final_text, theme.upper(), out_path, "Paragraph"])
    else:
        output_dir = "output_images"
        if args.image and not os.path.exists(output_dir): os.makedirs(output_dir)
        venv_python = os.path.join(os.getcwd(), "venv", "bin", "python")
        import uuid

        seeded_quotes = []
        if args.quote:
            seeded_quotes = [args.quote]
        elif args.seed:
            q = seed_to_quote(args.seed)
            if q is not None:
                seeded_quotes = [q]

        for i in range(len(seeded_quotes) or args.num_quotes):
            final_text = seeded_quotes[i] if seeded_quotes else generate_full_quote(theme=theme, chaos=chaos)
            q_id = str(uuid.uuid4())
            print(f"[{theme.upper()}|chaos{chaos:.2f}] {final_text}" if not args.raw else final_text)

            base_name = f"quote_{theme.upper()}_{timestamp}_{i+1}"
            if args.svg:
                from svg_generator import generate_svg
                generate_svg(final_text, theme=theme.upper(), output_path=f"{base_name}.svg")
            if args.image:
                out_path = os.path.join(output_dir, f"{base_name}.png")
                if os.path.exists(venv_python):
                    subprocess.run([venv_python, "src/image_generator.py", final_text, theme.upper(), out_path, q_id])