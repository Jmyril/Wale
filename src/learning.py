"""Loose grammar gate + a pair-based learning memory for Wale.

Wale never keeps a whole sentence you feed it. When it learns, it only
remembers how words sit next to each other:

  - bigrams / trigrams  -> which word tends to follow which ("cặp từ")
  - sentence starts      -> which words are allowed to open a sentence
  - sentence ends        -> how sentences usually close

So it cannot parrot a ready-made line back at you; it can only rebuild a new
one out of the word-pairs it was taught. Sentence *form* is kept, sentences
themselves are not.

When you type something, Wale first squints at it:

  - if it *looks* grammatical (a shallow heuristic, not a real parser), it
    swallows the word pairs right away;
  - if it looks wrong, Wale sulks. Repeat yourself enough and it gives up
    and learns it anyway.
"""

import hashlib
import json
import os
import re
from collections import Counter

import pos_tagger as pt

import quote_generator as qg

STORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "models",
    "user_brain.json",
)

REPEAT_THRESHOLD = 2   # 2nd sighting of bad grammar is enough to teach it
MIN_TOKENS = 2
MAX_TOKENS = 24

_SEP = "\x1f"          # joins a pair into a trigram-context key
_TOKEN_RE = re.compile(r"[a-z']+|[.,!?;]")
# Same, but keeps digits: used for the session-only layer so a taught value
# like "4" survives. The persistent brain stays digit-free on purpose.
_SESSION_TOKEN_RE = re.compile(r"[a-z0-9']+|[.,!?;]")


def tokenize(text):
    return _TOKEN_RE.findall((text or "").lower())


def tokenize_session(text):
    return _SESSION_TOKEN_RE.findall((text or "").lower())


def loose_grammar_check(tokens):
    """A deliberately shallow sniff test. Good enough is good enough."""
    if len(tokens) < MIN_TOKENS or len(tokens) > MAX_TOKENS:
        return False

    words = [t for t in tokens if t.isalpha()]
    if not words:
        return False

    roles = [pt.assign_role_by_pattern(w) for w in words]

    def verbish():
        if any(r in ("VERB", "VING", "MODAL") for r in roles):
            return True
        # crude third-person "-s": "the cat sits..." -> treat sits as a verb
        for i in range(1, len(words)):
            if words[i].endswith("s") and roles[i] == "NOUN" and roles[i - 1] in ("NOUN", "DET", "PRON"):
                return True
        return False

    # needs at least one verb-ish word
    if not verbish():
        return False
    # shouldn't dangle on a bare function word
    if roles[-1] == "FUNC":
        return False
    # three function words in a row is almost certainly babble
    run = 0
    for r in roles:
        run = run + 1 if r == "FUNC" else 0
        if run >= 3:
            return False

    return True


def _fingerprint(tokens):
    """A short hash of a sentence. Lets us recognise repeats without storing
    the sentence itself."""
    digest = hashlib.blake2b(" ".join(tokens).encode("utf-8"), digest_size=16).digest()
    return digest.hex()


def _bump(table, key, nxt):
    row = table.setdefault(key, {})
    row[nxt] = row.get(nxt, 0) + 1


class UserBrain:
    """Stores word-pair statistics and sentence form. Not sentences."""

    def __init__(self, path=STORE_PATH):
        self.path = path
        self.seen = {}         # fingerprint -> how many times typed
        self.learned = set()   # fingerprints already absorbed
        self.bigrams = {}      # word -> {next word: count}
        self.trigrams = {}     # "w1\x1fw2" -> {next word: count}
        self.starts = {}       # word -> times seen opening a sentence
        self.ends = {}         # punctuation -> times seen closing a sentence
        self._load()

    # -- persistence -------------------------------------------------------
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        raw_learned = data.get("learned", [])
        old_format = any(isinstance(item, list) for item in raw_learned)

        if old_format or "bigrams" not in data:
            # migrate an old sentence-storing brain into pair statistics only
            self.bigrams, self.trigrams = {}, {}
            self.starts, self.ends = {}, {}
            for tokens in raw_learned:
                if isinstance(tokens, list) and tokens:
                    self._count_tokens(tokens)
                    self.seen[_fingerprint(tokens)] = 1
                    self.learned.add(_fingerprint(tokens))
        else:
            self.seen = {str(k): int(v) for k, v in data.get("seen", {}).items()}
            self.learned = {str(x) for x in raw_learned}
            self.bigrams = {k: dict(v) for k, v in data.get("bigrams", {}).items()}
            self.trigrams = {k: dict(v) for k, v in data.get("trigrams", {}).items()}
            self.starts = dict(data.get("starts", {}))
            self.ends = dict(data.get("ends", {}))

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "seen": self.seen,
                        "learned": sorted(self.learned),
                        "bigrams": self.bigrams,
                        "trigrams": self.trigrams,
                        "starts": self.starts,
                        "ends": self.ends,
                    },
                    f,
                    ensure_ascii=False,
                )
        except Exception:
            pass

    # -- statistics --------------------------------------------------------
    def _count_tokens(self, tokens):
        """Turn one sentence into word-pairs + sentence-form counts. The
        sentence body is thrown away afterwards."""
        if not tokens:
            return
        if tokens[0] not in qg._BAD_START:
            self.starts[tokens[0]] = self.starts.get(tokens[0], 0) + 1
        if tokens[-1] in qg._END_PUNCT:
            self.ends[tokens[-1]] = self.ends.get(tokens[-1], 0) + 1
        for a, b in zip(tokens, tokens[1:]):
            _bump(self.bigrams, a, b)
        for a, b, c in zip(tokens, tokens[1:], tokens[2:]):
            _bump(self.trigrams, a + _SEP + b, c)

    def has_seen(self, tokens):
        return _fingerprint(list(tokens)) in self.learned

    def learn(self, tokens):
        """Learn the word pairs of a sentence (used by the ingest tool)."""
        tokens = list(tokens)
        if not tokens:
            return False
        fp = _fingerprint(tokens)
        if fp in self.learned:
            return False
        self._count_tokens(tokens)
        self.seen[fp] = self.seen.get(fp, 0) + 1
        self.learned.add(fp)
        return True

    # -- integration with the live Markov chain ----------------------------
    def restore_into(self, markov):
        """Merge stored pair/sentence-form stats into the Markov chain."""
        for word, nxt in self.bigrams.items():
            counter = markov["f1"].setdefault(word, Counter())
            for n, c in nxt.items():
                counter[n] += c
        for key, nxt in self.trigrams.items():
            a, _, b = key.partition(_SEP)
            counter = markov["f2"].setdefault((a, b), Counter())
            for n, c in nxt.items():
                counter[n] += c
        for word, c in self.starts.items():
            markov["starts"][word] += c

    def _absorb(self, markov, tokens):
        """Push one just-learned sentence's pairs into the live chain. No
        sentence is stored anywhere."""
        for a, b in zip(tokens, tokens[1:]):
            markov["f1"].setdefault(a, Counter())[b] += 1
        for a, b, c in zip(tokens, tokens[1:], tokens[2:]):
            markov["f2"].setdefault((a, b), Counter())[c] += 1
        if tokens and tokens[0] not in qg._BAD_START:
            markov["starts"][tokens[0]] += 1

    # -- the grammar-gated entry point -------------------------------------
    def observe(self, text, markov):
        tokens = tokenize(text)
        if not tokens:
            return {"status": "empty"}

        fp = _fingerprint(tokens)
        count = self.seen.get(fp, 0) + 1
        self.seen[fp] = count

        if fp in self.learned:
            return {"status": "known", "count": count}

        grammatical = loose_grammar_check(tokens)
        repeated = count >= REPEAT_THRESHOLD

        if grammatical or repeated:
            self._count_tokens(tokens)
            self._absorb(markov, tokens)
            self.learned.add(fp)
            self._save()
            status = "learned" if grammatical else "learned_repeat"
            return {"status": status, "count": count}

        self._save()
        return {"status": "rejected", "count": count}
