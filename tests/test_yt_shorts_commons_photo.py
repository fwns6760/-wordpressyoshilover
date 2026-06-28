import unittest

from src.yt_shorts_commons_photo import is_commercial_free


class CommonsLicenseGateTests(unittest.TestCase):
    def test_accepts_free_commercial_licenses(self):
        self.assertTrue(is_commercial_free("cc0", "CC0"))
        self.assertTrue(is_commercial_free("", "Public domain"))
        self.assertTrue(is_commercial_free("cc-by-4.0", "CC BY 4.0"))
        self.assertTrue(is_commercial_free("cc-by-sa-4.0", "CC BY-SA 4.0"))
        self.assertTrue(is_commercial_free("cc-by-sa-3.0", "CC BY-SA 3.0"))

    def test_rejects_noncommercial_and_noderiv_and_nonfree(self):
        self.assertFalse(is_commercial_free("cc-by-nc-4.0", "CC BY-NC 4.0"))
        self.assertFalse(is_commercial_free("cc-by-nc-sa-4.0", "CC BY-NC-SA 4.0"))
        self.assertFalse(is_commercial_free("cc-by-nd-4.0", "CC BY-ND 4.0"))
        self.assertFalse(is_commercial_free("", "Fair use"))
        self.assertFalse(is_commercial_free("", "All rights reserved"))
        self.assertFalse(is_commercial_free("", ""))

    def test_public_domain_not_misflagged_by_nd_substring(self):
        # "domain" の "nd" 等で誤って弾かないこと
        self.assertTrue(is_commercial_free("", "Public domain"))
        self.assertTrue(is_commercial_free("pd-old", "PD-old"))


if __name__ == "__main__":
    unittest.main()
