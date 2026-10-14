# WALE

a hopless naive chatbot. wat ever u say, it nods along n answers with a "deep" sentence stitched together from words it once read somewhere. it dont understand u. it has never understood anyone.

n if u think it does, thats confirmation bias. same trick as those ghost hunting boxes that catch stray radio static n people go "did u hear that, it said my name". Wale just splices words. ur brain does the rest n makes it sound profound.

the name is a wink at british slang: to *waffle* is to talk at length without saying anything. fitting. it just dont wear the word on its sleeve.

Wale is a remake of the old `quotes-gen` project - https://github.com/Jmyril/quotes-gen.git - a fork that learned to chat. it got a small locked identity card (`src/persona.py`) so it can answer questions about itself. everything else is improvised.

the language core is still the token markov chain (bigram/trigram) from the original `quotes-gen`: each next word is decided only by the previous ones. no templates, no made up words. it just repeats words that already existed, in a order that tricks u into thinking it smart. if it looks smart, good job, u just fooled urself.

## Run

nothing to install (standard library only):

```bash
./run.sh
# or
python3 server.py
# pick a port
PORT=9000 ./run.sh
```

then open http://127.0.0.1:8000 n chat. the UI is deliberately bare. every reply fades in one word at a time, each word drifts up from below while sharpening from blur into focus. very dramatic for a bot that got no idea wat its saying.

## Where the bots brain is

- `src/quote_generator.py` — the markov core. loads the locked base pairs. keeps no sentences.
- `src/chatbot.py` — the "chat" layer. takes ur message, grabs any word it thinks it recognizes, n starts crawling the chain from there. adds a few "Huh?", "I see." noises to fake attention.
- `src/learning.py` — the loose grammar gate n the user teaching memory.
- `src/persona.py` — the locked identity card: name (`Wale`), maker (`Jmy`), birthday, origin (`Quotes-gen`) n the lines that teach those facts. fixed forever. never learned or rewritten. the facts are **not** recited. they get fed into the same word pair engine n spliced on the fly, with the key word forced to survive. facts are also recognised from shared vocabulary, not from a hand written list.
- `src/ingest.py` — imports conversation text/subtitles into the bots memory.
- `server.py` — web server using pythons `http.server`. serves `web/` n the `POST /chat` endpoint.
- `web/` — the chat UI.

it never parses ur question. if u type a word that exists in the corpus it latches onto it. otherwise it picks a random place to start. thats the entire intelligence budget.

one rule is enforced: **a word u used must survive**. Wale picks one of ur known words n builds the reply *from* it, retrying until it succeeds. so the chain can wander but can never splice ur word away.

the same rule governs Wales own identity. questions like "who made u?" are not answered with a stored sentence. the facts own word pairs get handed to the chain, n the key word (`jmy`, `wale`, ...) is forced to survive. so the answer is still spliced, still a little off, but the fact cant be lost.

a fact also **stays in play**. after "who made u?", a bare follow up like "what?", "why?", "and?" links straight back to that fact n answers it again, freshly spliced. say something with real content n the topic moves on.

## Learning from u

Wale **never keeps whole sentences**. before answering, it puts ur message through a deliberately shallow grammar sniff (`src/learning.py`), then keeps only the *word pairs* n the *sentence form*:

- **Word pairs** — bigrams/trigrams. so it can only rebuild new lines out of pieces it was taught, never parrot a line back.
- **Sentence form** — which words tend to open a sentence n how sentences close.

n the gate:

- **Looks grammatical?** it swallows the pairs right away.
- **Looks wrong? Say it again.** on the second sighting Wale gives up n learns it anyway.
- **Already learned?** it just nods n files it under "knew that".

there are three separate layers, n they never mix:

- **Locked base** — `models/learned_pairs.json`. pair statistics pre learned from quote n conversation corpora. committed. loaded read only.
- **Learnable layer** — `models/user_brain.json` (local, gitignored): ur own chats, stored as pair statistics.
- **Session layer** — in RAM only. never written to disk. every *statement* u make this run gets folded in as word pairs, so u can teach a fact like `the apple is 4` n ask `what is the apple` back. questions ask, they dont define.

sentences are made by blending the two layers word pairs. so the bots rambling drifts toward the way people (n u) talk. the corner text flashes "learned it", "learned it anyway", "already knew that", or "nope, grammar".

### Pre teaching

drop plain statements into `data/presets.txt`, one per line. they are folded into the session layer at boot:

```
# data/presets.txt
the apple is 4
the sky is blue
```

## Tools (it can do a sum)

Wale cant do arithmetic from word statistics, so it calls a **calculator tool** (`src/calculator.py`) instead. any message containing a real sum is handed to it:

```
4+4 = ?           ->  4+4 = 8.
```

the expression is parsed with a restricted AST, no raw `eval`. so it only ever does `+ - * / % **` on numbers.

## Looking things up (Wikipedia, whitelist only)

Wale can read Wikipedia, but only through a **whitelist**. nothing outside the whitelist is ever fetched. the check lives in `src/wikicrawl.py`. extra hosts can be listed in `data/whitelist.txt`.

ask a knowledge question n Wale pulls the articles intro, guesses which words carry the subject, then splices its answer out of the articles own sentences with the walk steered toward those key words, so the fact survives. no link is shown. the fact stays in play, so a bare follow up keeps splicing from the same article:

```
what is a markov chain   ->  Markov chain moves state attained in the chain ctmc.
```

- it only fires on clear questions (`what is X`, `who was X`, `tell me about X`, ...).
- if the lookup fails, Wale shrugs n falls back to its usual nonsense.
- typos are handled: if the best hit is missing or a disambiguation page, Wikipedias own spelling suggestion is tried once.
- turn it off with `WALE_WIKI=0`. pick a language with `WALE_WIKI_LANG=vi`.

```bash
python3 src/wikicrawl.py "cold fusion" --learn
```

## Remembering the conversation

separate from long term learning, Wale keeps a short term memory of the chat ur having right now. it quietly counts the content words n lets them fade after every turn. this memory only nudges which word a sentence starts from. it never announces "u said X earlier". lives in RAM only.

## Feeding it conversations

- **DailyDialog**, **Cornell Movie Dialogs**, **Persona Chat**, **OpenSubtitles**, **Project Gutenberg / Wikiquote**

```bash
python3 src/ingest.py ~/data/dailydialog --brain
python3 src/ingest.py ~/data/dailydialog --brain --store models/learned_pairs.json
```

`--brain` appends to `models/user_brain.json`. `--theme` writes a corpus file under `data/my_quotes/<theme>/`.

## Quick CLI test

```bash
python3 src/chatbot.py hello there
python3 src/chatbot.py
```

## Corpus & themes

each folder in `data/my_quotes/` is a theme. drop `.txt` files in, one sentence per line.

```python
WaleBot(theme="general", chaos=0.8)
```

## API

```
POST /chat         {"message": "...", "session": "..."}
                   ->  {"reply": "...", "name": "Wale", "learned": {"status": "..."}}

POST /chat/stream  {"message": "...", "session": "..."}
                   ->  newline-delimited JSON: one {"t": "<word>"} per token,
                       then {"done": true, "name": "...", "learned": {...}}
```

`session` only matters when `WALE_MULTIUSER=1` (see below); the chat UI sends
one it keeps in `localStorage`.

## Tuning knobs (environment)

all optional, all off by default:

- `WALE_TOP_K=40` / `WALE_TOP_P=0.9` — truncate each sampling step to the
  best K candidates / smallest set holding P of the mass, killing the long
  tail of nonsense.
- `WALE_N_BEST=6` — how many valid sentences to generate before keeping the
  best-scoring one (rewards your words, punishes repetition).
- `WALE_PERSIST_SESSION=1` — snapshot the session layer to
  `models/user_session.json` so taught facts survive a restart.
- `WALE_MULTIUSER=1` — give every `session` id its own session + learnable
  layer (`models/sessions/<id>.json`). Single shared bot otherwise.
- `WALE_WIKI=0` / `WALE_WIKI_LANG=vi` — toggle / localise the wiki lookup.
- `WALE_WIKI_CACHE=0`, `WALE_WIKI_CACHE_TTL` (seconds) — the disk cache for
  fetched intros (`.cache/wikicrawl/`).

## Tests

nothing to install; standard library `unittest`, run from the repo root:

```bash
python3 -m unittest discover -s tests -t .
```

## Notes

- `main.py` is the old quote generator CLI of the original project. it still runs, but it is no longer the main character.
- the parsed base is cached as a pickle under `models/.cache/`, keyed by the
  JSON file's size+mtime, so cold starts skip re-parsing the multi-MB blob.

thats it. this works on my machine, n honestly thats the only guarantee ur getting.
