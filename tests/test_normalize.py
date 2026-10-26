"""Size parsing in normalize.py. Run: python -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import normalize as N  # noqa: E402


class GramsTest(unittest.TestCase):
    def test_decimals_without_a_leading_zero(self):  # Dutchie options and names like these were read as 5g / 25g
        self.assertEqual(N.parse_grams(".5g"), 0.5)
        self.assertEqual(N.parse_grams(".25g", "One Flower One Hitter 0.25g- Baby Yoda"), 0.25)
        self.assertEqual(N.parse_grams("Jerzy Landscapes | TK Headband (H) Pre Roll | .5g"), 0.5)
        self.assertEqual(N.parse_grams("Boho Euphorics | Grape |.5g 5PK DOUBLE Infused PreRolls (H)"), 0.5)

    def test_decimal_comma(self):
        self.assertEqual(N.parse_grams("0,5g"), 0.5)
        self.assertEqual(N.parse_grams("Live Resin Cart 0,5 g"), 0.5)

    def test_comma_as_separator(self):  # real Dutchie names
        self.assertEqual(N.parse_grams("Cadillac Rainbow,3.5g"), 3.5)
        self.assertEqual(N.parse_grams("Glitter Bomb,2.5g, 5pk"), 2.5)

    def test_ordinary_weights_unchanged(self):
        self.assertEqual(N.parse_grams("3.5g"), 3.5)
        self.assertEqual(N.parse_grams("Blue Dream 1g"), 1.0)
        self.assertEqual(N.parse_grams("14 grams"), 14.0)
        self.assertEqual(N.parse_grams("1/8 oz"), 3.5)
        self.assertEqual(N.parse_grams("1oz"), 28.0)
        self.assertEqual(N.parse_grams(".5oz"), 14.0)
        self.assertIsNone(N.parse_grams("100mg gummies"))
        self.assertIsNone(N.parse_grams(None, ""))

    def test_first_text_wins(self):
        self.assertEqual(N.parse_grams(".5g", "Pre Roll 1g"), 0.5)
        self.assertEqual(N.parse_grams(None, "Pre Roll 1g"), 1.0)

    def test_labels(self):
        self.assertEqual(N.size_label(N.parse_grams(".5g"), None), "0.5g")
        self.assertEqual(N.size_label(N.parse_grams(".25g"), None), "0.25g")


class MgTest(unittest.TestCase):
    def test_mg(self):
        self.assertEqual(N.parse_mg("1906 - Bliss Tablets 20pk 100mg"), 100.0)
        self.assertEqual(N.parse_mg("2.5mg mint"), 2.5)
        self.assertEqual(N.parse_mg(".5mg"), 0.5)
        self.assertEqual(N.parse_mg("2,5mg"), 2.5)
        self.assertEqual(N.parse_mg("Tincture 1,000mg"), 1000.0)  # thousands separator, not a decimal
        self.assertIsNone(N.parse_mg("1g"))


if __name__ == "__main__":
    unittest.main()
