import os

os.environ["SECRET_KEY"] = "unit-test-secret"

import unittest

from app.core.crypto import decrypt_json, decrypt_secret, encrypt_json, encrypt_secret


class TestCrypto(unittest.TestCase):
    def test_roundtrip(self):
        c = encrypt_secret("super-secret")
        self.assertTrue(c)
        self.assertNotEqual(c, "super-secret")
        self.assertEqual(decrypt_secret(c), "super-secret")

    def test_empty_safe(self):
        self.assertEqual(encrypt_secret(""), "")
        self.assertEqual(encrypt_secret(None), "")
        self.assertEqual(decrypt_secret(""), "")
        self.assertEqual(decrypt_secret(None), "")

    def test_json(self):
        c = encrypt_json({"a": 1, "b": "x"})
        self.assertEqual(decrypt_json(c), {"a": 1, "b": "x"})
        self.assertEqual(decrypt_json(""), {})
        self.assertEqual(decrypt_json(None), {})


if __name__ == "__main__":
    unittest.main()
