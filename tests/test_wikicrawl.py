import tempfile
import unittest

import wikicrawl as w


class TopicTest(unittest.TestCase):
    def test_what_is(self):
        self.assertEqual(w.topic_from("what is a markov chain?"), "markov chain")

    def test_tell_me_about(self):
        self.assertEqual(w.topic_from("tell me about cold fusion"), "cold fusion")

    def test_filler_stripped(self):
        self.assertEqual(w.topic_from("uhm what is X"), "X")

    def test_not_a_question(self):
        self.assertIsNone(w.topic_from("hello there friend"))

    def test_long_topic_rejected(self):
        self.assertIsNone(w.topic_from("what is " + " ".join(["word"] * 20)))


class WhitelistTest(unittest.TestCase):
    def test_allowed(self):
        self.assertTrue(w.host_allowed("en.wikipedia.org"))
        self.assertTrue(w.host_allowed("wikipedia.org"))

    def test_blocked(self):
        self.assertFalse(w.host_allowed("evil.example.com"))
        self.assertFalse(w.host_allowed("notwikipedia.org"))
        self.assertFalse(w.host_allowed(""))


class ParseTest(unittest.TestCase):
    def test_sentences(self):
        text = "One two three. Four five six! Seven eight nine?"
        self.assertEqual(len(w.sentences(text)), 3)

    def test_key_terms_prefers_topic(self):
        terms = w.key_terms(
            "Einstein developed relativity. Relativity changed physics.",
            topic="relativity",
            limit=3,
        )
        self.assertIn("relativity", terms)


class CacheTest(unittest.TestCase):
    def test_disk_cache_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            old = w.CACHE_DIR
            w.CACHE_DIR = d
            try:
                info = {"title": "T", "extract": "x", "url": "u"}
                w.cache_put("some query", "en", info)
                self.assertEqual(w.cache_get("some query", "en"), info)
                self.assertIsNone(w.cache_get("never stored", "en"))
            finally:
                w.CACHE_DIR = old


if __name__ == "__main__":
    unittest.main()
