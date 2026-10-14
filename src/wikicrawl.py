"""Whitelist-gated web lookup so Wale can read Wikipedia without wandering.

Nothing is ever fetched unless the URL's host is on the whitelist. Wikipedia
ships enabled out of the box; more hosts go in ``data/whitelist.txt`` (one host
per line, ``#`` for comments). Standard library only, so it fits the rest of
the bot (no pip installs).

Typical use::

    import wikicrawl
    info = wikicrawl.lookup("markov chain")
    if info:
        print(info["extract"])
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from html.parser import HTMLParser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

import pos_tagger as pt  # noqa: E402
WHITELIST_FILE = os.path.join(BASE_DIR, "data", "whitelist.txt")

# Built-in hosts. Matching is suffix-based, so "wikipedia.org" also allows
# "en.wikipedia.org", "vi.wikipedia.org", and so on.
WHITELIST = {
    "wikipedia.org",
    "wikimedia.org",
    "wiktionary.org",
    "wikiquote.org",
    "wikibooks.org",
    "wikisource.org",
    "wikidata.org",
}

USER_AGENT = "WaleBot/1.0 (small educational markov chatbot)"
TIMEOUT = 6
MAX_BYTES = 750_000
MIN_INTERVAL = 0.4      # seconds between requests, to be polite to the API
_last_request = 0.0


def _throttle():
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()

WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
WIKI_HOST = "{lang}.wikipedia.org"


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------
def load_whitelist(path=WHITELIST_FILE):
    """The built-in hosts plus anything listed in data/whitelist.txt."""
    hosts = set(WHITELIST)
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                host = line.strip().lower()
                if host and not host.startswith("#"):
                    hosts.add(host)
    except OSError:
        pass
    return hosts


def host_allowed(host, whitelist=None):
    """True if ``host`` equals or is a subdomain of any whitelisted host."""
    host = (host or "").lower().split(":")[0]
    if not host:
        return False
    allowed = WHITELIST if whitelist is None else whitelist
    return any(host == a or host.endswith("." + a) for a in allowed)


def _validate(url, whitelist=None):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"blocked scheme: {parsed.scheme or '(none)'}")
    if not host_allowed(parsed.hostname, whitelist):
        raise ValueError(f"host not on whitelist: {parsed.hostname or '(none)'}")
    return parsed


def fetch(url, whitelist=None, max_bytes=MAX_BYTES, timeout=TIMEOUT):
    """Fetch a whitelisted URL and return its body as text. Raises otherwise.

    Retries once on 429 (rate limit), after a short pause."""
    _validate(url, whitelist)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(2):
        _throttle()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read(max_bytes + 1)
                charset = "utf-8"
                try:
                    charset = resp.headers.get_content_charset() or charset
                except Exception:
                    pass
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt == 0:
                time.sleep(1.5)
                continue
            raise
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return data.decode(charset, errors="replace")


class _Stripper(HTMLParser):
    """Turn an HTML page into readable text (no external parser needed)."""

    def __init__(self):
        super().__init__()
        self._skip = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("p", "br", "div", "li", "h1", "h2", "h3", "tr"):
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def text(self):
        raw = "".join(self._parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        return raw.strip()


def fetch_text(url, whitelist=None, **kwargs):
    """Fetch a whitelisted page and strip the HTML down to plain text."""
    stripper = _Stripper()
    stripper.feed(fetch(url, whitelist, **kwargs))
    return stripper.text()


# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------
def _get_json(url, whitelist=None, timeout=TIMEOUT):
    return json.loads(fetch(url, whitelist, timeout=timeout))


def search(query, lang="en", whitelist=None):
    """Return the best matching article title, or None."""
    params = {
        "action": "opensearch",
        "format": "json",
        "limit": 1,
        "namespace": 0,
        "search": query,
    }
    url = WIKI_API.format(lang=lang) + "?" + urllib.parse.urlencode(params)
    try:
        data = _get_json(url, whitelist)
    except Exception:
        return None
    titles = data[1] if isinstance(data, list) and len(data) > 1 else []
    return titles[0] if titles else None


def summary(title, lang="en", sentences=6, whitelist=None):
    """Return {'title', 'extract', 'url'} for an article, or None."""
    if not title:
        return None
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "explaintext": 1,
        "exintro": 1,
        "exsentences": sentences,
        "redirects": 1,
        "titles": title,
    }
    url = WIKI_API.format(lang=lang) + "?" + urllib.parse.urlencode(params)
    try:
        data = _get_json(url, whitelist)
        pages = data["query"]["pages"]
    except Exception:
        return None
    for page in pages.values():
        extract = (page.get("extract") or "").strip()
        if not extract:
            continue
        name = page.get("title", title)
        return {
            "title": name,
            "extract": extract,
            "url": "https://" + WIKI_HOST.format(lang=lang) + "/wiki/"
            + urllib.parse.quote(name.replace(" ", "_")),
        }
    return None


def suggestion(query, lang="en", whitelist=None):
    """Wikipedia's 'did you mean' for a query, or None."""
    params = {
        "action": "query",
        "format": "json",
        "list": "search",
        "srsearch": query,
        "srlimit": 1,
        "srinfo": "suggestion",
    }
    url = WIKI_API.format(lang=lang) + "?" + urllib.parse.urlencode(params)
    try:
        data = _get_json(url, whitelist)
    except Exception:
        return None
    found = (data.get("query", {}).get("searchinfo") or {}).get("suggestion")
    if found and found.strip().lower() != query.strip().lower():
        return found.strip()
    return None


# ---------------------------------------------------------------------------
# Disk cache: a fetched intro is reused across runs so we don't hammer the
# API (and can answer offline once warm). Keyed by language + query; only
# successful lookups are stored. Disable with WALE_WIKI_CACHE=0.
# ---------------------------------------------------------------------------
CACHE_DIR = os.environ.get("WALE_WIKI_CACHE_DIR") or os.path.join(BASE_DIR, ".cache", "wikicrawl")
CACHE_TTL = int(os.environ.get("WALE_WIKI_CACHE_TTL", str(7 * 24 * 3600)))
CACHE_ENABLED = os.environ.get("WALE_WIKI_CACHE", "1") != "0"


def _cache_path(query, lang):
    key = hashlib.sha1(f"{lang}\x1f{query}".encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, key + ".json")


def cache_get(query, lang):
    if not CACHE_ENABLED:
        return None
    try:
        with open(_cache_path(query, lang), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if CACHE_TTL and time.time() - data.get("ts", 0) > CACHE_TTL:
        return None
    return data.get("info")


def cache_put(query, lang, info):
    if not CACHE_ENABLED or not info:
        return
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = _cache_path(query, lang)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"query": query, "lang": lang, "ts": time.time(), "info": info},
                f,
                ensure_ascii=False,
            )
        os.replace(tmp, path)
    except OSError:
        pass


def cache_clear():
    """Delete every cached lookup. Returns how many entries were removed."""
    removed = 0
    try:
        for name in os.listdir(CACHE_DIR):
            if name.endswith(".json"):
                try:
                    os.remove(os.path.join(CACHE_DIR, name))
                    removed += 1
                except OSError:
                    pass
    except OSError:
        pass
    return removed


def lookup(query, lang="en", whitelist=None, use_cache=True):
    """Search Wikipedia for ``query`` and return its intro summary.

    If the best hit is missing or a disambiguation page ("X may refer to:"),
    fall back to Wikipedia's spelling suggestion once. Successful lookups are
    cached on disk and reused (unless ``use_cache`` is False).
    """
    if use_cache:
        hit = cache_get(query, lang)
        if hit:
            return hit
    title = search(query, lang, whitelist)
    info = summary(title, lang, whitelist=whitelist) if title else None
    if info and "may refer to" not in info["extract"].lower():
        cache_put(query, lang, info)
        return info
    suggested = suggestion(query, lang, whitelist)
    if suggested:
        alt = summary(suggested, lang, whitelist=whitelist)
        if alt:
            cache_put(query, lang, alt)
            return alt
    return info


# ---------------------------------------------------------------------------
# Turning a chat message into a lookup
# ---------------------------------------------------------------------------
_TOPIC_PATTERNS = [
    re.compile(
        r"^\s*(?:what|who|which|where)\s+(?:is|are|was|were|'s|s)\s+"
        r"(?P<topic>.+?)\s*[?.!]*$",
        re.I,
    ),
    re.compile(
        r"^\s*(?:tell me about|tell me of|tell me more about|what about|"
        r"what do you know about|do you know about|know anything about|"
        r"explain|define|describe|search for|look up|lookup|wiki)\s+"
        r"(?P<topic>.+?)\s*[?.!]*$",
        re.I,
    ),
    re.compile(
        r"^\s*(?:info|information|facts)\s+(?:on|about)\s+(?P<topic>.+?)\s*[?.!]*$",
        re.I,
    ),
]

_TOPIC_STOP = {"a", "an", "the", "this", "that", "these", "those", "your", "my"}

# Filler people type before the actual question: "uhm what is X", "so tell me...".
_FILLER = re.compile(
    r"^(?:u+h+m*|u+m+|a+h+|e+r+m*|h+m+|s+o+|w+e+l+l+|h+e+y+|o+k+a?y?|"
    r"l+i+k+e+|p+l+e+a+s+e+|y+o+u+ k+n+o+w+)\b[\s,]*",
    re.I,
)


def _strip_filler(text):
    prev = None
    while text != prev:
        prev = text
        text = _FILLER.sub("", text).strip()
    return text


def topic_from(message):
    """Pull a lookup topic out of a question, or None if it isn't one."""
    text = _strip_filler((message or "").strip())
    if not text or len(text) > 200:
        return None
    for pattern in _TOPIC_PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        topic = m.group("topic").strip(" ?.!,\"'")
        topic = re.sub(r"\s+", " ", topic)
        words = topic.split()
        if words and words[0].lower() in _TOPIC_STOP:
            topic = " ".join(words[1:])
        if not topic or not any(ch.isalpha() for ch in topic):
            continue
        if len(topic.split()) > 8:
            continue
        return topic
    return None


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_STOP_ROLES = ("FUNC", "PRON", "DET", "MODAL")


def sentences(text, min_words=3, max_words=60):
    """Split an extract into usable sentences, dropping only tiny fragments.

    Long intro sentences are kept on purpose: they are where the subject's own
    vocabulary lives. The markov walk caps its own length anyway.
    """
    out = []
    for chunk in _SENT_SPLIT.split((text or "").strip()):
        chunk = chunk.strip()
        if not chunk:
            continue
        words = [w for w in re.findall(r"[a-z']+", chunk.lower()) if w.isalpha()]
        if min_words <= len(words) <= max_words:
            out.append(chunk)
    return out


def key_terms(text, topic=None, limit=6):
    """Guess the words an extract *must* keep: the ones that carry its subject.

    A word scores higher when it repeats, is capitalised mid-sentence (a
    proper noun), appears in the asked-about topic, or is a noun rather than a
    verb. Everyday words (``commonwords.txt``) score lower. Order is most
    important first.
    """
    raw = text or ""
    proper = set()
    for sentence in _SENT_SPLIT.split(raw):
        words = sentence.split()
        for i, w in enumerate(words):
            core = w.strip(".,;:!?()\"'")
            if i > 0 and len(core) > 1 and core[:1].isupper() and core.isalpha():
                proper.add(core.lower())

    topic_words = set(re.findall(r"[a-z']+", (topic or "").lower()))
    counts = Counter()
    for w in re.findall(r"[a-z']+", raw.lower()):
        if len(w) < 3:
            continue
        if pt.assign_role_by_pattern(w) in _STOP_ROLES:
            continue
        counts[w] += 1

    scores = {}
    for w, count in counts.items():
        score = float(count)
        if w in proper:
            score += 3.0
        if w in topic_words:
            score += 5.0
        if w in pt.common_words_raw:
            score -= 2.0
        role = pt.assign_role_by_pattern(w)
        if role == "NOUN":
            score += 1.5
        elif role == "VERB":
            score += 0.5
        scores[w] = score

    return sorted(scores, key=lambda w: (scores[w], len(w)), reverse=True)[:limit]



# ---------------------------------------------------------------------------
# CLI: quick lookup, optionally teaching the result to the bot
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Whitelist-gated Wikipedia lookup.")
    ap.add_argument("query", nargs="+", help="what to look up")
    ap.add_argument("--lang", default="en", help="wikipedia language (default en)")
    ap.add_argument("--sentences", type=int, default=6, help="intro sentences to pull")
    ap.add_argument("--learn", action="store_true", help="fold the extract into Wale's memory")
    ap.add_argument("--store", help="memory path for --learn (default models/user_brain.json)")
    args = ap.parse_args()

    query = " ".join(args.query)
    info = lookup(query, lang=args.lang)
    if not info:
        print(f"no wikipedia article for {query!r}", file=sys.stderr)
        return 1

    print(f"# {info['title']} <{info['url']}>")
    print(info["extract"])

    if args.learn:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import learning  # noqa: E402
        brain = learning.UserBrain(path=args.store) if args.store else learning.UserBrain()
        added = 0
        for line in sentences(info["extract"]):
            if brain.learn(learning.tokenize(line)):
                added += 1
        brain._save()
        print(f"taught Wale {added} wiki sentences as word-pairs -> {brain.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
