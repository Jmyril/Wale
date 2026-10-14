import unittest

import calculator


class CalculatorTest(unittest.TestCase):
    def test_basic_sum(self):
        self.assertEqual(
            calculator.solve("what is 4 + 4?"),
            {"expr": "4 + 4", "value": "8"},
        )

    def test_no_operator_returns_none(self):
        self.assertIsNone(calculator.solve("just 4"))
        self.assertIsNone(calculator.solve("hello there"))

    def test_multiplication(self):
        self.assertEqual(calculator.solve("6*7")["value"], "42")

    def test_unicode_operators(self):
        self.assertEqual(calculator.solve("8 ÷ 2")["value"], "4")
        self.assertEqual(calculator.solve("3 × 3")["value"], "9")

    def test_power(self):
        self.assertEqual(calculator.solve("2^10")["value"], "1024")

    def test_division_by_zero_is_none(self):
        self.assertIsNone(calculator.solve("5/0"))

    def test_float_format(self):
        self.assertEqual(calculator.solve("7/2")["value"], "3.5")

    def test_longest_run_wins(self):
        self.assertEqual(calculator.solve("2+2 plus 1+1+1")["value"], "3")

    def test_none_message(self):
        self.assertIsNone(calculator.solve(None))


if __name__ == "__main__":
    unittest.main()
