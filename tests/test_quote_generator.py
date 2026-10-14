import unittest

import quote_generator as qg


class TextFixTest(unittest.TestCase):
    def test_articles(self):
        self.assertEqual(qg.fix_articles("a apple"), "an apple")
        self.assertEqual(qg.fix_articles("an dog"), "a dog")
        self.assertEqual(qg.fix_articles("a hour"), "an hour")
        self.assertEqual(qg.fix_articles("an unit"), "a unit")

    def test_fix_case(self):
        self.assertEqual(qg.fix_case("hello world"), "Hello world.")

    def test_sanity(self):
        self.assertTrue(qg.sanity_check("The cat is here."))
        self.assertFalse(qg.sanity_check("Cat."))

    def test_vowel_sound(self):
        self.assertTrue(qg._is_vowel_sound("apple"))
        self.assertFalse(qg._is_vowel_sound("dog"))


class SampleTest(unittest.TestCase):
    def test_top_k_restricts_to_best(self):
        keys = ["a", "b", "c", "d"]
        weights = [1, 100, 1, 1]
        picks = {qg._sample(keys, weights, 1.0, top_k=1) for _ in range(50)}
        self.assertEqual(picks, {"b"})

    def test_top_p_nucleus(self):
        picks = {qg._sample(["a", "b"], [100, 1], 1.0, top_p=0.9) for _ in range(50)}
        self.assertEqual(picks, {"a"})


if __name__ == "__main__":
    unittest.main()
