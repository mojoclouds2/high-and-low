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


class PackTest(unittest.TestCase):  # names from the real menus
    def test_unit_weight_is_multiplied(self):
        self.assertEqual(N.pack_grams("Green Leevz | Soap | .7g 2pk PreRolls (S)"), 1.4)
        self.assertEqual(N.pack_grams("Honey Banana - Live Rosin Vape 2pk (.5g Cart)"), 1.0)
        self.assertEqual(N.pack_grams("Dawg Lemons Smokos Pre-Roll .5g 5-Pack"), 2.5)
        self.assertEqual(N.pack_grams("Higgs | Sunday Driver | 10 x .3g Preroll (I)"), 3.0)
        self.assertEqual(N.pack_grams("Torchez - Blue Dream - 2pk x 0.75g each Infused Pre-roll"), 1.5)
        self.assertEqual(N.pack_grams("GO TIME | 0.58G | 6PK | GET UP"), 3.48)
        self.assertEqual(N.pack_grams("Shaka - Banana Cake #20 - (3pk x 1g) Pre-rolls"), 3.0)
        self.assertEqual(N.pack_grams("Jay's Party Pack Duo - Burpee & Morning Diesel - 28pk .5g Pre Rolls"), 14.0)

    def test_pack_total_is_kept(self):
        self.assertEqual(N.pack_grams("ALLDAY - Blacktop Diesel 5pk 2.5g"), 2.5)
        self.assertEqual(N.pack_grams("Lowell Farms | Chill Indica | Pre-Roll | 3.5g/6pk"), 3.5)
        self.assertEqual(N.pack_grams("Twozie - Chill Pre-Roll 2pk 2g"), 2.0)
        self.assertEqual(N.pack_grams("Cheddar Cheeze Mini Dogs 5-pack | 1.75g"), 1.75)
        self.assertEqual(N.pack_grams("2.25g - 5pk - Infused Prerolls - Couch Crasher - Dogwalkers - REC"), 2.25)

    def test_singles_and_no_weight(self):
        self.assertEqual(N.pack_grams("Blue Dream Pre-Roll 1g"), 1.0)
        self.assertEqual(N.pack_grams("One Pre-Roll 1pk/0.7g- Vanilla Sprinklez"), 0.7)
        self.assertEqual(N.pack_grams("Sour Diesel x Kush Mints Pre-Roll .5g"), 0.5)  # "x" between strains, not a count
        self.assertIsNone(N.pack_grams("2pk - Diamond Infused Preroll - Lemon Cherry Rozay"))
        self.assertIsNone(N.pack_grams(None))


class CheckPackTest(unittest.TestCase):  # store weight vs the name, real listings
    def test_name_overrules_a_clearly_wrong_store_weight(self):
        self.assertEqual(N.check_pack(1.0, "Twozie - Chill Pre-Roll 2pk 2g"), 2.0)
        self.assertEqual(N.check_pack(1.0, "Springtime - Sub Zero 5pk 2.5g"), 2.5)
        self.assertEqual(N.check_pack(2.5, "Illicit | Violet Fog | 2pk 1g Pre-Roll (I)"), 1.0)
        self.assertEqual(N.check_pack(2.0, "Chocolate OG | All Times 5pk Pre-Rolls | 0.5g Each"), 2.5)
        self.assertEqual(N.check_pack(5.0, "Kind Tree Pre-Roll 2pk/0.5g Infused- Cherry Slushee"), 1.0)

    def test_store_weight_kept_when_the_name_agrees(self):
        self.assertEqual(N.check_pack(14, "Sunday -  Kush Cake - 14pk 1g Pre Rolls - 14g"), 14)
        self.assertEqual(N.check_pack(3, "Shaka - Banana Cake #20 - (3pk x 1g) Pre-rolls"), 3)
        self.assertEqual(N.check_pack(2.5, "Dawg Lemons Smokos Pre-Roll .5g 5-Pack"), 2.5)
        self.assertEqual(N.check_pack(3.5, "Clade9 Pre-Roll 5pk/3.4g- Fig Bar"), 3.5)  # within 10%

    def test_singles_and_unstated_weights_untouched(self):
        self.assertEqual(N.check_pack(3.5, "Blue Dream 1g"), 3.5)  # not a pack
        self.assertEqual(N.check_pack(3.5, "10 Pack - Infused PreRolls - Pave - High Wired"), 3.5)
        self.assertIsNone(N.check_pack(None, "Twozie 2pk 2g"))


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
