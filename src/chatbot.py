"""Wale — a hopelessly naive Markov chatbot.

It has no idea what you just said. It only remembers words it once read in
some corpus and strings them back together with a perfectly straight face.
That is the whole intelligence budget.

The actual language model lives in ``quote_generator.py`` (bigram/trigram
token Markov chain). This module just wraps it in a talking parrot suit.
"""

import os
import random
import re
import sys
import json
from collections import Counter, deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import quote_generator as qg
import learning
import persona
import pos_tagger as pt
import calculator
import wikicrawl

# Neutral little noises the bot makes when it wants to sound like it listened.
_INTERJECTIONS = [
    "Huh?", "Oh...", "I see.", "Wait, what?", "Hmm...", "Uh-huh...",
    "Sure, sure.", "That's deep.", "Right...", "Interesting...", "Oh really?",
    "Wow.", "Okay then.", "Mhm.",
]

_END_PUNCT = qg._END_PUNCT

# Closed-class question openers (function words, not phrasings). Used only to
# tell "asking" from "telling" so questions never redefine the session layer.
_WH_QUESTIONS = {"what", "who", "whom", "whose", "which", "where", "when", "why", "how"}

# Base-continuation count above which a word counts as a "hub" and is barred
# from carrying session bigrams (see _learn_session).
_HUB_FREQ = 200

# How many valid candidate sentences to generate before picking the best one.
_N_BEST = int(os.environ.get("WALE_N_BEST", "6") or 6)


def _markov_from_brain(brain):
    """Turn a brain's pair statistics into a Markov layer (no sentences)."""
    starts = Counter(brain.starts)
    f1 = {w: Counter(c) for w, c in brain.bigrams.items()}
    f2 = {}
    for key, nxt in brain.trigrams.items():
        a, _, b = key.partition(learning._SEP)
        f2[(a, b)] = Counter(nxt)
    return {"starts": starts, "f1": f1, "f2": f2}


class WaleBot:
    """A chatbot whose only skill is sounding vaguely wise by accident."""

    def __init__(self, theme="general", chaos=0.8, name=persona.NAME, brain_path=None):
        self.theme = theme
        self.chaos = chaos
        self.name = name

        # Locked base knowledge: word pairs learned ahead of time from corpora.
        # Loaded read-only and never written back to, so learning can add new
        # pairs but can never edit or erase the base.
        self.base = qg._load_markov(theme)

        # Locked persona layer: Wale's identity facts, kept as word pairs so
        # answers about Jmy/its name/themselves are *spliced*, not recited.
        self.persona_layer = self._build_layer(persona.all_lines())

        # Learnable layer: what *you* typed (local, gitignored). A per-session
        # brain store can be handed in (used by the multi-user server).
        self.brain = learning.UserBrain(path=brain_path) if brain_path else learning.UserBrain()
        self.live = _markov_from_brain(self.brain)
        self.last_learning = {"status": "empty"}

        # Session-only associative layer: the word pairs of *this*
        # conversation's user turns, held in RAM and faded every turn. This is
        # how a taught association ("the apple is 4") is remembered — as plain
        # statistics, no rules, no fact table. Restart and it's gone, unless
        # WALE_PERSIST_SESSION=1 turns on the on-disk snapshot.
        self.session = {"starts": Counter(), "f1": {}, "f2": {}}
        self.session_weight = 10.0
        self.session_decay = 0.8
        self.persist_session = os.environ.get("WALE_PERSIST_SESSION", "0") == "1"
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.session_path = os.environ.get("WALE_SESSION_PATH") or os.path.join(
            root, "models", "user_session.json"
        )
        if self.persist_session:
            self._load_session()
        # Facts pre-taught for every run (data/presets.txt). Plain statements,
        # folded into the session layer at boot — data you own, not code.
        self._load_presets()

        # Short-term memory of *this* conversation only. Kept in RAM, never
        # written to disk, and it fades a little with every turn.
        self.memory = Counter()
        self.memory_decay = 0.75
        self.memory_size = 200

        # The identity fact currently in play. Lets a bare follow-up ("what?")
        # link back to it, without any hard-coded "what -> creator" rule.
        self.persona_topic = None
        self.persona_topic_ttl = 0
        self.persona_topic_life = 3

        # Whitelist-gated Wikipedia lookup. Only whitelisted hosts (see
        # src/wikicrawl.py and data/whitelist.txt) can ever be fetched.
        self.wiki_enabled = os.environ.get("WALE_WIKI", "1") != "0"
        self.wiki_lang = os.environ.get("WALE_WIKI_LANG", "en")
        self.wiki_cache = {}
        self.wiki_cache_order = []
        self.wiki_cache_max = 32

        # Anti-repeat: the last few things Wale said, so it doesn't hand back
        # the exact same line twice in a row. RAM only.
        self.recent = deque(maxlen=6)

    @staticmethod
    def _build_layer(lines):
        """Compile a locked list of sentences into a word-pair Markov layer."""
        brain = learning.UserBrain()
        # UserBrain loads the on-disk brain; a locked layer must not inherit it.
        brain.seen.clear()
        brain.learned.clear()
        brain.bigrams.clear()
        brain.trigrams.clear()
        brain.starts.clear()
        brain.ends.clear()
        for line in lines:
            toks = learning.tokenize(line)
            if toks:
                brain.learn(toks)
        return _markov_from_brain(brain)

    # -- "understanding" ---------------------------------------------------
    def _tokens(self, message):
        return re.findall(r"[a-z']+", (message or "").lower())

    def _remember(self, text, weight=1.0):
        """Hold on to the content words of a turn, so later turns can drift
        back toward what the conversation was about."""
        for w in self._tokens(text):
            if pt.assign_role_by_pattern(w) in ("FUNC", "PRON", "DET", "MODAL"):
                continue
            self.memory[w] += weight

    def _age_memory(self):
        """Let old words fade so the chat leans on the recent past."""
        for w in list(self.memory):
            self.memory[w] *= self.memory_decay
            if self.memory[w] < 0.05:
                del self.memory[w]
        if len(self.memory) > self.memory_size:
            for w, _ in self.memory.most_common()[self.memory_size:]:
                del self.memory[w]

    def reset(self):
        self.memory.clear()
        self.session = {"starts": Counter(), "f1": {}, "f2": {}}

    # -- session-only association (the "teaching") -------------------------
    def _decay_session(self):
        """Fade the session layer so recent turns dominate and old ones drift
        away. Same idea as the short-term memory, one level down."""
        s = self.session
        f = self.session_decay
        s["starts"] = Counter(
            {w: c * f for w, c in s["starts"].items() if c * f >= 0.05}
        )
        for w in list(s["f1"]):
            row = s["f1"][w]
            for t in list(row):
                row[t] *= f
                if row[t] < 0.05:
                    del row[t]
            if not row:
                del s["f1"][w]
        for key in list(s["f2"]):
            row = s["f2"][key]
            for t in list(row):
                row[t] *= f
                if row[t] < 0.05:
                    del row[t]
            if not row:
                del s["f2"][key]

    def _learn_session(self, text, decay=True):
        """Fold a user turn into the session layer as word pairs. Digits (and
        math signs) are kept here, unlike the persistent brain, so a value like
        '4' or a taught sum survives."""
        toks = learning.tokenize_session(text)
        if not toks:
            return
        # Treat every turn as a sentence: give it a terminal mark if it lacks
        # one, so a taught chain can actually finish.
        if toks[-1] not in qg._END_PUNCT:
            toks.append(".")
        if decay:
            self._decay_session()
        s = self.session
        if toks[0] not in qg._BAD_START:
            s["starts"][toks[0]] += 1
        for a, b in zip(toks, toks[1:]):
            # Keep the subject->value link in the trigram, but don't let a hub
            # word ("is", continued a thousand ways) carry a session bigram,
            # or two facts would contaminate each other ("apple is blue").
            if self._is_hub(a):
                continue
            s["f1"].setdefault(a, Counter())[b] += 1
        for a, b, c in zip(toks, toks[1:], toks[2:]):
            s["f2"].setdefault((a, b), Counter())[c] += 1
        if decay:
            self._save_session()

    def _is_hub(self, word):
        """A word the frozen base continues so often that a single taught pair
        about it is just noise."""
        return sum(self.base["f1"].get(word, {}).values()) >= _HUB_FREQ

    def _load_presets(self):
        """Pre-teach facts for every run from a plain text file: one statement
        per line, '#' comments allowed. Empty by default. This is data you own,
        not code baked in, and it still lives only in RAM."""
        path = os.environ.get("WALE_PRESETS")
        if not path:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(root, "data", "presets.txt")
        if not os.path.isfile(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            self._learn_session(line, decay=False)

    # -- optional session snapshot (WALE_PERSIST_SESSION=1) ----------------
    def _session_to_json(self):
        s = self.session
        return {
            "starts": dict(s["starts"]),
            "f1": {w: dict(row) for w, row in s["f1"].items()},
            "f2": {
                f"{a}{learning._SEP}{b}": dict(row)
                for (a, b), row in s["f2"].items()
            },
        }

    def _save_session(self):
        """Persist the session layer so taught facts survive a restart. Off by
        default; only runs when WALE_PERSIST_SESSION=1."""
        if not self.persist_session:
            return
        try:
            os.makedirs(os.path.dirname(self.session_path), exist_ok=True)
            tmp = self.session_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._session_to_json(), f, ensure_ascii=False)
            os.replace(tmp, self.session_path)
        except OSError:
            pass

    def _load_session(self):
        try:
            with open(self.session_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        s = self.session
        s["starts"] = Counter(data.get("starts", {}))
        s["f1"] = {w: Counter(row) for w, row in data.get("f1", {}).items()}
        s["f2"] = {}
        for key, row in data.get("f2", {}).items():
            a, _, b = key.partition(learning._SEP)
            s["f2"][(a, b)] = Counter(row)

    def _known(self, word):
        """A word is usable if either the locked base or the learnable layer
        has seen it."""
        for layer in (self.base, self.live, self.persona_layer, self.session):
            if word in layer["f1"] or word in layer["starts"]:
                return True
        return False

    def _seed_pool(self, message):
        """Candidate starting words: what you just said (heavily favoured),
        plus whatever the conversation still remembers."""
        known = [w for w in self._tokens(message) if self._known(w)]
        pool = [(w, 3.0) for w in known]
        seen = set(known)
        for w, c in self.memory.items():
            if w in seen or not self._known(w):
                continue
            pool.append((w, float(c)))
        return pool

    def _seed_word(self, message):
        """Naive reading: start on a word it recognises — usually yours, but
        sometimes an echo of something from earlier in the chat."""
        pool = self._seed_pool(message)
        if not pool:
            return None
        words, weights = zip(*pool)
        return random.choices(words, weights=weights, k=1)[0]

    def _required_words(self, message):
        """Content words from your message that Wale is *obliged* to keep in
        its reply — no matter how the chain wants to wander off."""
        if not message:
            return []
        required = []
        for w in self._tokens(message):
            if w in required:
                continue
            if pt.assign_role_by_pattern(w) in ("FUNC", "PRON", "DET", "MODAL"):
                continue
            if self._known(w):
                required.append(w)
        # Rarest first, so the anchor lands on the word that carries the
        # meaning (a taught value) instead of a ubiquitous one like "is".
        return sorted(required, key=self._word_freq)

    def _word_freq(self, word):
        """How common a word is across the layers — used to pick an anchor.
        Small total = rare = informative."""
        total = 0
        for layer in (self.base, self.live, self.session):
            total += sum(layer["f1"].get(word, {}).values())
            total += layer["starts"].get(word, 0)
        return total

    # -- sentence assembly -------------------------------------------------
    def _layers(self, layers=None):
        """Weighted layers for generation. The session layer is weighted high
        so what you just taught outshouts the huge frozen base, then fades."""
        if layers is not None:
            return layers
        return (
            (self.base, 1.0),
            (self.live, 1.2),
            (self.session, self.session_weight),
        )

    def _start_pool(self, layers=None):
        c = Counter()
        for layer, weight in self._layers(layers):
            for w, n in layer["starts"].items():
                c[w] += n * weight
        return c

    def _next_token(self, tokens, temperature, layers=None, prefer=None):
        """Blend trigram (70%) + bigram (30%) per layer, then mix the layers by
        weight on a normalised scale, so a tiny session layer can outshout the
        huge frozen base. The base is only ever read. ``prefer`` gives a set of
        words the walk should steer toward (used to keep a wiki answer's key
        terms)."""
        layers = self._layers(layers)
        pairs = {}
        for layer, weight in layers:
            raw = {}
            if len(tokens) >= 2:
                trig = layer["f2"].get((tokens[-2], tokens[-1]))
                if trig:
                    for tok, cnt in trig.items():
                        raw[tok] = raw.get(tok, 0.0) + 0.7 * cnt
            bi = layer["f1"].get(tokens[-1])
            if bi:
                for tok, cnt in bi.items():
                    raw[tok] = raw.get(tok, 0.0) + 0.3 * cnt
            total = sum(raw.values())
            if total <= 0:
                continue
            for tok, val in raw.items():
                pairs[tok] = pairs.get(tok, 0.0) + weight * val / total
        if not pairs:
            return None
        if prefer:
            for tok in pairs:
                if tok in prefer:
                    pairs[tok] *= 8.0
        items = list(pairs.items())
        return qg._sample([t for t, _ in items], [w for _, w in items], temperature)

    def _walk(self, start, temperature, layers=None, prefer=None):
        if start is None:
            start = qg._wc(self._start_pool(layers), temperature)
        if start is None or start in qg._BAD_START:
            return None
        toks = [start]
        guard = 0
        while len(toks) < 20 and guard < 30:
            guard += 1
            nxt = self._next_token(toks, temperature, layers, prefer)
            if nxt is None:
                break
            if nxt in {",", ";"}:
                if len(toks) >= 6:
                    break
                continue
            toks.append(nxt)
            if nxt in _END_PUNCT:
                break
        if len(toks) >= 4 and toks[-1] in _END_PUNCT:
            return toks
        return None

    def _session_has(self, word):
        """Whether the session layer knows anything about this word — i.e. you
        taught it something this run."""
        return bool(self.session["f1"].get(word)) or self.session["starts"].get(word, 0) > 0

    def _sentence(self, message=None):
        temperature = 0.4 + self.chaos * 0.5
        required = self._required_words(message)
        # Skip anchors the walk refuses to start on (stray punctuation, say).
        starters = [w for w in required if w not in qg._BAD_START]
        anchor = starters[0] if starters else (required[0] if required else None)

        # The session layer is only switched on when you actually asked about
        # something you taught. Otherwise a stray taught pair ("apple is 4")
        # would keep getting spliced into unrelated small talk.
        if anchor is not None and self._session_has(anchor):
            layers = None
        else:
            layers = ((self.base, 1.0), (self.live, 1.2))

        # Anchored: always start from a word you used, so it cannot be spliced
        # away. Any accepted walk contains that word by construction. The
        # rarest word leads, since it is the one carrying the meaning. We build
        # a small pool of valid candidates and keep the best-scoring one rather
        # than returning the first that merely passes sanity.
        candidates = []
        for _ in range(max(_N_BEST * 8, 40)):
            seed = anchor if anchor is not None else self._seed_word(message)
            self._collect_candidate(candidates, seed, temperature, layers, required)
            if len(candidates) >= _N_BEST:
                break

        # The chain refused to keep anything: allow free, unanchored tries.
        if not candidates:
            for _ in range(20):
                self._collect_candidate(candidates, None, temperature, layers, required)
                if len(candidates) >= _N_BEST:
                    break
        if candidates:
            return max(candidates, key=lambda item: item[0])[1]
        return "Quiet things still need tending."

    def _collect_candidate(self, pool, seed, temperature, layers, required):
        """Walk once; if the result passes sanity, score it into ``pool``."""
        toks = self._walk(seed, temperature, layers)
        if not toks:
            return
        sentence = qg.fix_case(qg.fix_articles(" ".join(toks)))
        if not qg.sanity_check(sentence):
            return
        pool.append((self._score_sentence(toks, required), sentence))

    def _score_sentence(self, toks, required):
        """Rank a candidate: reward the words the user used and a middling
        length, punish repetition, reward a clean ending. A pinch of randomness
        keeps replies from freezing on one phrasing."""
        score = random.random() * 0.4
        kept = set(toks)
        for w in required:
            if w in kept:
                score += 3.0
        length = len(toks)
        if 6 <= length <= 14:
            score += 1.0
        elif length < 4:
            score -= 2.0
        score -= 0.5 * (length - len(kept))
        if toks and toks[-1] in qg._END_PUNCT:
            score += 0.5
        return score

    def _persona_sentence(self, keywords, lines, required=None, avoid=()):
        """Splice an answer out of the word pairs of *these* lines only, so it
        cannot wander off into another fact. The chain does the talking; the
        key word(s) are forced to survive. When ``required`` is given, the
        walk is scored by how many of those words it keeps. ``avoid`` holds
        recent replies so the same line isn't handed back twice."""
        layer = self._build_layer(lines)
        temperature = 0.4 + self.chaos
        seeds = [k for k in keywords if k not in qg._BAD_START]
        anchor = seeds[0] if seeds else None
        required = [w for w in (required or []) if w not in qg._BAD_START]
        if not seeds and not required:
            return None
        avoid = set(avoid)

        best = None
        best_hits = -1
        attempts = 60 if not required else 160
        prefer = set(required) or None
        for _ in range(attempts):
            seed = random.choice(seeds) if seeds else None
            toks = self._walk(seed, temperature, layers=((layer, 1.0),), prefer=prefer)
            if not toks:
                continue
            sentence = qg.fix_case(qg.fix_articles(" ".join(toks)))
            if not qg.sanity_check(sentence):
                continue
            seen = sentence in avoid
            if not required:
                if anchor and anchor not in toks:
                    continue
                if seen:
                    continue
                return sentence
            hits = sum(1 for w in required if w in toks)
            score = hits - (100 if seen else 0)
            if score > best_hits:
                best, best_hits = sentence, score
            if hits == len(required) and not seen:
                return sentence
        return best if best_hits >= 0 else None

    def _persona_reply(self, fact):
        line = self._persona_sentence(
            fact["keywords"], fact["lines"], fact.get("required"), avoid=self.recent
        )
        if line:
            return line
        fresh = [l for l in fact["lines"] if l not in self.recent]
        return persona.canned(fresh or fact["lines"])

    # -- wikipedia (whitelist-gated) ----------------------------------------
    def _wiki_lookup(self, topic):
        if topic in self.wiki_cache:
            return self.wiki_cache[topic]
        try:
            info = wikicrawl.lookup(topic, lang=self.wiki_lang)
        except Exception:
            return None
        self.wiki_cache[topic] = info
        self.wiki_cache_order.append(topic)
        while len(self.wiki_cache_order) > self.wiki_cache_max:
            old = self.wiki_cache_order.pop(0)
            self.wiki_cache.pop(old, None)
        return info

    def _wiki_keywords(self, topic, lines):
        """Anchor the splice on topic words that actually show up in the
        summary — forcing the article's own vocabulary to drive the line."""
        low = " ".join(lines).lower()
        words = [
            w for w in self._tokens(topic)
            if w not in qg._BAD_START
            and pt.assign_role_by_pattern(w) not in ("FUNC", "PRON", "DET", "MODAL")
        ]
        present = sorted((w for w in words if w in low), key=len, reverse=True)
        return (present or words)[:3] or self._tokens(topic)[:2]

    def _session_association(self, message):
        """True if this session already tied a content word of the message to
        something (i.e. you taught it earlier). Then the session's own spliced
        answer should win over a web lookup. Purely statistical: no phrase list.
        """
        for w in self._tokens(message):
            if pt.assign_role_by_pattern(w) in ("FUNC", "PRON", "DET", "MODAL"):
                continue
            if self.session["f1"].get(w):
                return True
        return False

    def _wiki_reply(self, message):
        """Answer a knowledge question by splicing from a Wikipedia intro. Only
        on the whitelist does Wale even reach for the network; offline (or
        unknown topic) it just falls back to normal rambling.

        The extract is first mined for the words that carry its subject
        (``wikicrawl.key_terms`` plus the topic words); the splice is then
        scored to keep as many of those as it can, so the answer stays on the
        article instead of drifting into filler."""
        if not self.wiki_enabled:
            return None
        if self._session_association(message):
            return None
        topic = wikicrawl.topic_from(message)
        if not topic:
            return None
        info = self._wiki_lookup(topic)
        if not info:
            return None
        lines = wikicrawl.sentences(info["extract"])
        if not lines:
            return None

        low = " ".join(lines).lower()
        topic_words = [w for w in self._tokens(topic) if w not in qg._BAD_START]
        terms = wikicrawl.key_terms(info["extract"], topic=topic, limit=5)
        required = []
        for w in topic_words + terms:
            if w not in required and w in low:
                required.append(w)
        seeds = self._wiki_keywords(topic, lines) or terms or topic_words

        fact = {
            "key": "wiki",
            "keywords": seeds,
            "required": required or seeds,
            "lines": lines,
            "source": info["url"],
            "topic": info["title"],
        }
        self._remember(message)
        self._remember(info["extract"], weight=0.5)
        # Reuse the identity-fact machinery: the fact stays in play, so a bare
        # follow-up ("really?", "what?") keeps splicing from the same article.
        self.persona_topic = fact
        self.persona_topic_ttl = self.persona_topic_life
        return self._persona_reply(fact)

    # -- public API --------------------------------------------------------
    def _after_reply(self, message, out):
        # Only statements *teach* the session layer; questions ask, they don't
        # define. And a sum is the calculator's job, not something to memorise.
        if not self._is_question(message) and not calculator.solve(message):
            self._learn_session(message)
        self.recent.append(out)

    def reply(self, message):
        out = self._reply(message)
        self._after_reply(message, out)
        return out

    def reply_stream(self, message):
        """The same reply, delivered one word at a time so the web server can
        stream it to the browser. Generation is identical; only the transport
        differs. State (learning, recent, session) updates before the first
        word is yielded, so the caller can read ``last_learning`` right away."""
        out = self._reply(message)
        self._after_reply(message, out)
        yield from out.split(" ")

    def _is_question(self, message):
        text = (message or "").strip()
        if text.endswith("?"):
            return True
        toks = re.findall(r"[a-z']+", text.lower())
        return bool(toks) and toks[0] in _WH_QUESTIONS

    def _reply(self, message):
        # First: a loose grammar sniff. If it passes (or you've said it
        # before), the word combinations get absorbed into the chain.
        self._age_memory()
        self.last_learning = self.brain.observe(message, self.live)

        # A hand: if the message actually contains a sum, use the calculator
        # tool rather than guessing with word statistics.
        math = calculator.solve(message)
        if math:
            return f"{math['expr']} = {math['value']}."

        # Some questions are about Wale itself. Those are *also* spliced by the
        # same engine, but from the locked persona word-pairs, and the key
        # words are forced to survive so the fact never gets lost.
        fact = persona.match(message)
        if fact:
            self._remember(message)
            self.persona_topic = fact
            self.persona_topic_ttl = self.persona_topic_life
            return self._persona_reply(fact)

        # A knowledge question ("what is X?", "tell me about X") triggers a
        # whitelist-gated Wikipedia lookup; the reply is spliced from the
        # article's own sentences the same way identity facts are.
        wiki_reply = self._wiki_reply(message)
        if wiki_reply:
            return wiki_reply

        # A bare follow-up ("what?", "why?", "and?") links back to whatever
        # fact Wale was just talking about — association, not a phrase list.
        if self.persona_topic and self.persona_topic_ttl > 0 and persona.is_bare(message):
            self.persona_topic_ttl -= 1
            self._remember(message)
            return self._persona_reply(self.persona_topic)

        # A message with real content moves the subject on, so the old fact
        # stops being reachable by bare follow-ups.
        if self._tokens(message):
            self.persona_topic = None
            self.persona_topic_ttl = 0
        elif self.persona_topic_ttl > 0:
            self.persona_topic_ttl -= 1

        body = self._sentence(message)
        self._remember(message)
        self._remember(body, weight=0.5)
        message = (message or "").strip()
        if not message:
            return random.choice([
                "You didn't type anything. Bold strategy.",
                "Silence is also an answer, I guess.",
                body,
            ])
        roll = random.random()
        if message.endswith("?") or roll < 0.3:
            return f"{random.choice(_INTERJECTIONS)} {body}"
        return body


_default_bot = None


def get_bot():
    """Shared bot instance so the Markov model is only built once."""
    global _default_bot
    if _default_bot is None:
        _default_bot = WaleBot()
    return _default_bot


if __name__ == "__main__":
    bot = get_bot()
    if len(sys.argv) > 1:
        print(bot.reply(" ".join(sys.argv[1:])))
    else:
        print(f"{bot.name}: (type something, ctrl-c to quit)")
        while True:
            try:
                msg = input("you> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            print(f"{bot.name}> {bot.reply(msg)}")
            status = bot.last_learning.get("status")
            if status in ("learned", "learned_repeat"):
                note = "learned it" if status == "learned" else "learned it anyway"
                print(f"   (wale {note})")
