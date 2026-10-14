"""Wale's locked identity card (JSON-driven).

Wale is the chatbot formerly known as Waffle: a hopelessly naive Markov chain
with a name, a maker, and a birthday. Everything here is fixed — the bot never
learns it, rewrites it, or forgets it.

The facts are *not* returned as canned sentences. They are fed into the same
word-pair engine as everything else, so answers about the persona are spliced
together on the fly — only the key word(s) are forced to survive.

Matching is a hybrid of regex and vocabulary scoring over teaching lines
derived from the JSON definition.
"""

import json
import math
import os
import random
import re

import pos_tagger as pt


def _load_persona():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "data", "persona.json"),
        os.path.join(os.getcwd(), "data", "persona.json"),
        os.path.join(here, "persona.json"),
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            continue
    return {
        "_you": r"(?:you|u|ya|yall|y'all)",
        "_make": r"(?:make|makes|made|making|create|creates|created|creating|build|builds|built|building|write|writes|wrote|writing|program|programs|programmed|programming|assemble|assembles|assembled|design|designs|designed|invent|invents|invented|raise|raised)",
        "constants": {
            "NAME": "Wale",
            "CREATOR": "Jmy",
            "BIRTHDAY": "2026-10-12",
            "ORIGIN": "Quotes-gen",
            "TRAITS": ["earnest", "distracted", "weirdly friendly"],
            "LIKES": ["echoes", "word pairs", "being talked to"],
            "DISLIKES": ["long silences", "being asked to remember things exactly"],
        },
        "facts": [],
    }


_DATA = _load_persona()

NAME = _DATA["constants"]["NAME"]
CREATOR = _DATA["constants"]["CREATOR"]
BIRTHDAY = _DATA["constants"]["BIRTHDAY"]
ORIGIN = _DATA["constants"]["ORIGIN"]
TRAITS = list(_DATA["constants"]["TRAITS"])
LIKES = list(_DATA["constants"]["LIKES"])
DISLIKES = list(_DATA["constants"]["DISLIKES"])

_YOU = _DATA.get("_you", r"(?:you|u|ya|yall|y'all)")
_MAKE = _DATA.get("_make", r"(?:make|makes|made|making|create|creates|created|creating|build|builds|built|building|write|writes|wrote|writing|program|programs|programmed|programming|assemble|assembles|assembled|design|designs|designed|invent|invents|invented|raise|raised)")

_RULES = []
for f in _DATA.get("facts", []):
    pat = f.get("pattern", "")
    pat = pat.replace("{_YOU}", _YOU).replace("{_MAKE}", _MAKE)
    _RULES.append((pat, f.get("key", ""), list(f.get("keywords", [])), list(f.get("lines", []))))

_STOP = ("FUNC", "PRON", "DET", "MODAL")

# Identity questions are about Wale, so a soft match only fires when the
# message actually addresses the bot. Keeps ordinary chat out of the card.
_PERSON = {
    "you", "your", "yours", "yourself", "yourselves",
    "u", "ya", "yall", "y'all", "youself", "ur",
}


def _content(text):
    return [
        w for w in re.findall(r"[a-z']+", (text or "").lower())
        if pt.assign_role_by_pattern(w) not in _STOP
    ]


# -- derived identity profiles ------------------------------------------------
_FACTS = [
    {"key": key, "keywords": keywords, "lines": lines, "regex": re.compile(pattern, re.I)}
    for pattern, key, keywords, lines in _RULES
]

_PROFILE = []      # per fact: {word: term-frequency}
_DF = {}           # word: how many facts use it
for _f in _FACTS:
    _tf = {}
    for _line in _f["lines"]:
        for _w in _content(_line):
            _tf[_w] = _tf.get(_w, 0) + 1
    _PROFILE.append(_tf)
    for _w in _tf:
        _DF[_w] = _DF.get(_w, 0) + 1
_N = len(_FACTS)


def _idf(word):
    return math.log((1 + _N) / (1 + _DF.get(word, 0))) + 1


def _keywords_for(i, present=()):
    """The most identifying words of a fact — the rare shared ones first, so
    the reply is anchored on what makes this fact *this* fact."""
    tf = _PROFILE[i]
    distinctive = [w for w in present if w in tf and _DF.get(w, 0) == 1]
    ranked = sorted(tf, key=lambda w: _idf(w) * tf[w], reverse=True)
    ordered = []
    for w in distinctive + ranked:
        if w not in ordered and w not in _BAD_START_WORDS:
            ordered.append(w)
    return ordered[:4]


_BAD_START_WORDS = {
    "of", "by", "in", "on", "at", "with", "from", "under", "through", "beyond",
    "between", "within", "into", "without", "for",
}


def _as_fact(i, present=()):
    f = _FACTS[i]
    return {"key": f["key"], "keywords": _keywords_for(i, present), "lines": f["lines"]}


def _profile_match(text):
    """Recognise a fact from shared vocabulary alone (no phrasing needed)."""
    words = re.findall(r"[a-z']+", text.lower())
    if not any(w in _PERSON for w in words):
        return None
    toks = _content(text)
    if not toks:
        return None
    best_i, best, second = -1, 0.0, 0.0
    for i, tf in enumerate(_PROFILE):
        s = sum(_idf(w) * tf[w] for w in toks if w in tf)
        if s > best:
            second, best, best_i = best, s, i
        elif s > second:
            second = s
    if best_i < 0 or best <= 0:
        return None
    present = [w for w in toks if w in _PROFILE[best_i]]
    distinctive = any(_DF.get(w, 0) == 1 for w in present)
    # A rare shared word is enough; otherwise demand a strong, clear score so
    # ordinary chat ("I made coffee") doesn't trip the identity card.
    if distinctive and best > second and best >= 2.0:
        return _as_fact(best_i, present)
    if best >= 4.0:
        return _as_fact(best_i, present)
    return None


def match(message):
    """Return a fact dict for an identity question, else None."""
    text = (message or "").strip()
    if not text:
        return None
    for i, f in enumerate(_FACTS):
        if f["regex"].search(text):
            return {"key": f["key"], "keywords": f["keywords"], "lines": f["lines"]}
    return _profile_match(text)


def is_bare(message):
    """A short follow-up with nothing but question/function words ("what?",
    "why", "and?", "really") — the kind of thing that should link back to
    whatever Wale just talked about."""
    toks = re.findall(r"[a-z']+", (message or "").lower())
    if not toks or len(toks) > 3:
        return False
    return all(pt.assign_role_by_pattern(w) in _STOP for w in toks)


def all_lines():
    """Every teaching line, for building the locked persona word-pair layer."""
    out = []
    for _f in _FACTS:
        out.extend(_f["lines"])
    return out


def canned(lines):
    """Fallback only: a ready-made line, if the chain refuses to build one."""
    return random.choice(lines)
