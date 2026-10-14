import os

# Get the directory of the current script
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def load_words_from_file(filename):
    """Loads words from a text file, one word per line."""
    file_path = os.path.join(DATA_DIR, filename)
    with open(file_path, 'r') as f:
        return {word.strip().lower() for word in f if word.strip()}

common_words_raw = load_words_from_file('commonwords.txt')

all_words_raw = load_words_from_file('words.txt')

all_words = all_words_raw.union(common_words_raw)


_FUNC_CANDIDATES = {
    'a', 'an', 'the', 'to', 'in', 'on', 'of', 'and', 'but', 'or', 'if', 'then', 'than', 'as',
    'about', 'with', 'by', 'at', 'from', 'into', 'over', 'under', 'through', 'before', 'after',
    'while', 'when', 'where', 'how', 'why', 'what', 'which', 'who', 'whom', 'whose',
    'wherever', 'whenever', 'however', 'because', 'since', 'until', 'unless', 'though',
    'although', 'even', 'only', 'also', 'just', 'too', 'very', 'quite', 'rather', 'still',
    'yet', 'already', 'soon', 'always', 'never', 'often', 'sometimes', 'usually', 'rarely',
    'seldom', 'ever', 'almost', 'nearly', 'enough', 'much', 'many', 'more', 'most', 'less',
    'least', 'few', 'little', 'another', 'other', 'both', 'all', 'several', 'some', 'any', 'no',
    'every', 'each', 'either', 'neither', 'one', 'two', 'three',
    'not',
    'so', 'such',
    'up', 'down', 'out', 'off', 'back', 'forward', 'away',
    'again', 'ago'
}
FUNC = {w for w in _FUNC_CANDIDATES if w in all_words}

_PRON_CANDIDATES = {
    'i', 'me', 'you', 'he', 'him', 'she', 'her', 'it', 'we', 'us', 'they', 'them',
    'mine', 'yours', 'his', 'hers', 'ours', 'theirs',
    'myself', 'yourself', 'himself', 'herself', 'itself', 'ourselves', 'themselves',
    'everyone', 'everybody', 'someone', 'somebody', 'anyone', 'anybody',
    'noone', 'nobody', 'something', 'anything', 'nothing', 'everything',
    'who', 'whom', 'whose', 'which', 'what',
    'this', 'that', 'these', 'those'
}
PRON = {w for w in _PRON_CANDIDATES if w in all_words}


_MODAL_CANDIDATES = {'can', 'could', 'may', 'might', 'must', 'shall', 'should', 'will', 'would',
                     'cannot', 'can\'t', 'won\'t', 'couldn\'t', 'shouldn\'t', 'wouldn\'t', 'cannot'}
MODAL = {w for w in _MODAL_CANDIDATES if w in all_words}


_DET_CANDIDATES = {
    'a', 'an', 'the',
    'my', 'your', 'his', 'her', 'its', 'our', 'their',
    'this', 'that', 'these', 'those',
    'some', 'any', 'no', 'every', 'each', 'either', 'neither', 'both', 'all',
    'few', 'many', 'most', 'several', 'enough', 'more', 'less', 'little', 'much',
    'another', 'other', 'one'
}
DET = {w for w in _DET_CANDIDATES if w in all_words}


# ---------------------------------------------------------------------------
# Core lexicon: base-form verbs, plain adjectives and adverbs that suffix
# rules cannot catch.  These are the words that used to fall through to NOUN
# and made every connector decision wrong.
# ---------------------------------------------------------------------------
_BASE_VERBS = {
    'achieve', 'act', 'admit', 'allow', 'answer', 'ask', 'avoid', 'become',
    'beg', 'begin', 'believe', 'bend', 'betray', 'build', 'burn', 'call',
    'carry', 'catch', 'change', 'choose', 'cling', 'close', 'collect',
    'come', 'create', 'cry', 'dance', 'dare', 'deal', 'decide', 'defend',
    'deny', 'destroy', 'discover', 'doubt', 'draw', 'dream', 'drive', 'drop',
    'earn', 'eat', 'embrace', 'endure', 'enjoy', 'enter', 'escape', 'exist',
    'expect', 'explain', 'explore', 'face', 'fail', 'fall', 'feed', 'feel',
    'find', 'finish', 'fit', 'fix', 'flee', 'flow', 'follow', 'forget',
    'forgive', 'form', 'free', 'gain', 'gather', 'get', 'give', 'grow',
    'guard', 'happen', 'hate', 'have', 'hear', 'help', 'hide', 'hold', 'hope',
    'hunt', 'imagine', 'invent', 'join', 'judge', 'keep', 'kneel', 'know',
    'laugh', 'lay', 'lead', 'learn', 'leave', 'lend', 'let', 'lie', 'lift',
    'listen', 'like', 'live', 'look', 'lose', 'love', 'make', 'manage', 'matter',
    'mean', 'meet', 'move', 'need', 'notice', 'offer', 'open', 'overcome',
    'own', 'pass', 'pay', 'play', 'practise', 'prepare', 'promise', 'protect',
    'prove', 'pull', 'push', 'put', 'question', 'reach', 'read', 'realize',
    'receive', 'refuse', 'remain', 'remember', 'remove', 'return', 'rise',
    'run', 'say', 'see', 'seek', 'seem', 'sell', 'send', 'serve', 'set',
    'settle', 'shape', 'share', 'shine', 'show', 'sink', 'sit', 'speak',
    'spend', 'spread', 'stand', 'start', 'stay', 'steal', 'step', 'stop',
    'strike', 'struggle', 'study', 'surrender', 'survive', 'swim', 'take',
    'teach', 'tear', 'tell', 'think', 'throw', 'touch', 'travel', 'treat',
    'trust', 'try', 'turn', 'understand', 'use', 'visit', 'wait', 'walk',
    'want', 'waste', 'watch', 'wear', 'whisper', 'win', 'wish', 'wonder',
    'work', 'worry', 'write',
}
_BASE_VERBS |= {
    'came', 'gave', 'made', 'knew', 'found', 'took', 'broke', 'spoke',
    'wrote', 'went', 'left', 'felt', 'kept', 'built', 'ran', 'heard', 'told',
    'held', 'sat', 'stood', 'became', 'began', 'brought', 'bought', 'caught',
    'drew', 'drove', 'fought', 'flew', 'forgot', 'grew', 'hid', 'hit', 'led',
    'lost', 'met', 'paid', 'rose', 'sold', 'sent', 'showed', 'shut', 'sang',
    'slept', 'struck', 'taught', 'thought', 'threw', 'woke', 'won', 'wore',
    'read', 'saw', 'did', 'had', 'was', 'were', 'been', 'got',
    'am', 'is', 'are', 'be', 'being', 'has',
}

_BASE_ADJS = {
    'able', 'afraid', 'alive', 'alone', 'ancient', 'angry', 'aware', 'bad',
    'bare', 'beautiful', 'big', 'bitter', 'black', 'blind', 'blue', 'bold',
    'brave', 'brief', 'bright', 'broad', 'brown', 'calm', 'certain', 'cheap',
    'clean', 'clear', 'clever', 'cold', 'cool', 'cruel', 'curious', 'dark',
    'deep', 'dense', 'dirty', 'dry', 'dull', 'eager', 'early', 'easy',
    'empty', 'fair', 'famous', 'fast', 'fat', 'fine', 'firm', 'fit', 'flat',
    'frail', 'free', 'fresh', 'friendly', 'funny', 'glad', 'golden', 'good',
    'grand', 'gray', 'great', 'green', 'gross', 'happy', 'hard', 'harsh',
    'heavy', 'high', 'hollow', 'honest', 'hot', 'huge', 'hungry', 'ill',
    'important', 'impossible', 'interesting', 'jealous', 'kind', 'large',
    'late', 'lazy', 'light', 'little', 'live', 'long', 'loud', 'low', 'lucky',
    'mad', 'main', 'major', 'merry', 'mild', 'minor', 'neat', 'new', 'nice',
    'noble', 'odd', 'old', 'open', 'ordinary', 'pale', 'patient', 'plain',
    'pleasant', 'poor', 'popular', 'positive', 'pretty', 'proud', 'pure',
    'quick', 'quiet', 'rare', 'raw', 'ready', 'real', 'rich', 'right',
    'ripe', 'rough', 'round', 'safe', 'same', 'savage', 'sharp', 'short',
    'shy', 'sick', 'silent', 'simple', 'sincere', 'slow', 'small', 'smart',
    'smooth', 'soft', 'solid', 'solitary', 'sore', 'sound', 'sour', 'special',
    'strange', 'strong', 'stupid', 'sure', 'sweet', 'swift', 'tall', 'tender',
    'thick', 'thin', 'tight', 'tired', 'tiny', 'tough', 'true', 'ugly',
    'unable', 'unfair', 'united', 'unknown', 'unwise', 'upset', 'vast',
    'violent', 'warm', 'weak', 'wet', 'white', 'wide', 'wild', 'wise',
    'wonderful', 'worthy', 'wrong', 'young',
}

_BASE_ADVS = {
    'again', 'almost', 'always', 'away', 'back', 'barely', 'briefly',
    'certainly', 'clearly', 'daily', 'early', 'even', 'ever', 'far', 'fast',
    'finally', 'forward', 'further', 'hard', 'here', 'home', 'however',
    'indeed', 'instead', 'late', 'later', 'long', 'maybe', 'near', 'never',
    'now', 'often', 'once', 'only', 'so', 'sometimes', 'soon', 'still',
    'then', 'there', 'today', 'together', 'tomorrow', 'tonight', 'usually',
    'very', 'well',
}


def assign_role_by_pattern(word):
    word_lower = str(word).lower().strip(".,;:!?()\"'")

    if word_lower in FUNC:
        return 'FUNC'
    if word_lower in PRON:
        return 'PRON'
    if word_lower in MODAL:
        return 'MODAL'
    if word_lower in DET:
        return 'DET'

    if word_lower.endswith("ing"):
        return 'VING'
    if word_lower in _BASE_VERBS:
        return 'VERB'
    if word_lower in _BASE_ADJS:
        return 'ADJ'
    if word_lower in _BASE_ADVS:
        return 'ADV'
    if word_lower.endswith("ly"):
        return 'ADV'
    if word_lower.endswith(("able", "ous", "ful", "less", "ive", "ic", "al")):
        return 'ADJ'
    if word_lower.endswith(("ed", "ize", "ify", "ate")):
        return 'VERB'

    return 'NOUN'


def resolve_role(word, prev_word=None, next_word=None):
    """Context-aware guess, used by the generator for slot sanity."""
    w = str(word).lower().strip(".,;:!?()\"'")
    p = str(prev_word).lower() if prev_word else None
    n = str(next_word).lower() if next_word else None

    if p in ('to',) and w not in _BASE_ADJS:
        return 'VERB'
    if p in MODAL:
        return 'VERB'
    if p in DET:
        return 'NOUN'
    return assign_role_by_pattern(w)