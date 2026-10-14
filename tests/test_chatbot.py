import os
import tempfile
import unittest

import chatbot


class BotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["WALE_WIKI"] = "0"  # never touch the network in tests
        cls._tmp = tempfile.TemporaryDirectory()
        cls.bot = chatbot.WaleBot(brain_path=os.path.join(cls._tmp.name, "brain.json"))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_question_detection(self):
        self.assertTrue(self.bot._is_question("what is a cat?"))
        self.assertTrue(self.bot._is_question("what"))
        self.assertFalse(self.bot._is_question("the cat sat"))

    def test_calculator_reply(self):
        self.assertEqual(self.bot.reply("4+4"), "4+4 = 8.")

    def test_reply_nonempty(self):
        out = self.bot.reply("hello there friend")
        self.assertIsInstance(out, str)
        self.assertTrue(out.strip())

    def test_stream_yields_words(self):
        words = list(self.bot.reply_stream("4+4"))
        self.assertEqual(words, ["4+4", "=", "8."])

    def test_stream_nonempty(self):
        words = list(self.bot.reply_stream("tell me something about words"))
        self.assertTrue(words)
        self.assertTrue(" ".join(words).strip())

    def test_session_persist_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            sess = os.path.join(d, "session.json")
            brain = os.path.join(d, "brain.json")
            b = chatbot.WaleBot(brain_path=brain)
            b.persist_session = True
            b.session_path = sess
            b.reply("the apple is 4")
            self.assertTrue(os.path.exists(sess))

            b2 = chatbot.WaleBot(brain_path=brain)
            b2.persist_session = True
            b2.session_path = sess
            b2._load_session()
            self.assertTrue(b2._session_has("apple"))


if __name__ == "__main__":
    unittest.main()
