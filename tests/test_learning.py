import os
import tempfile
import unittest
from collections import Counter

import learning


class TokenizeTest(unittest.TestCase):
    def test_tokenize(self):
        self.assertEqual(learning.tokenize("Hello, World!"), ["hello", ",", "world", "!"])

    def test_tokenize_session_keeps_digits(self):
        self.assertEqual(learning.tokenize_session("Apple is 4"), ["apple", "is", "4"])


class GrammarTest(unittest.TestCase):
    def test_good_sentence(self):
        self.assertTrue(
            learning.loose_grammar_check(learning.tokenize("the cat sits on the mat"))
        )

    def test_too_short(self):
        self.assertFalse(learning.loose_grammar_check(learning.tokenize("hi")))

    def test_no_verb(self):
        self.assertFalse(
            learning.loose_grammar_check(learning.tokenize("the big blue moon"))
        )


def _markov():
    return {"f1": {}, "f2": {}, "starts": Counter()}


class BrainTest(unittest.TestCase):
    def test_grammatical_learned_then_known(self):
        with tempfile.TemporaryDirectory() as d:
            brain = learning.UserBrain(path=os.path.join(d, "brain.json"))
            markov = _markov()
            self.assertEqual(
                brain.observe("the sky is blue", markov)["status"], "learned"
            )
            self.assertEqual(
                brain.observe("the sky is blue", markov)["status"], "known"
            )
            self.assertTrue(os.path.exists(brain.path))

    def test_bad_grammar_rejected_then_learned_on_repeat(self):
        with tempfile.TemporaryDirectory() as d:
            brain = learning.UserBrain(path=os.path.join(d, "brain.json"))
            markov = _markov()
            self.assertEqual(brain.observe("blue sky moon river", markov)["status"], "rejected")
            self.assertEqual(
                brain.observe("blue sky moon river", markov)["status"], "learned_repeat"
            )


if __name__ == "__main__":
    unittest.main()
