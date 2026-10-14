import unittest

import persona


class PersonaTest(unittest.TestCase):
    def test_name_constant(self):
        self.assertEqual(persona.NAME, "Wale")

    def test_who_made_you(self):
        fact = persona.match("who made you?")
        self.assertIsNotNone(fact)
        self.assertEqual(fact["key"], "creator")

    def test_name_question(self):
        fact = persona.match("what is your name?")
        self.assertIsNotNone(fact)
        self.assertEqual(fact["key"], "name")

    def test_is_bare(self):
        self.assertTrue(persona.is_bare("what?"))
        self.assertTrue(persona.is_bare("why"))
        self.assertFalse(persona.is_bare("the apple is red"))

    def test_all_lines_present(self):
        self.assertTrue(persona.all_lines())


if __name__ == "__main__":
    unittest.main()
