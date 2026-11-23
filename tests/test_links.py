import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class LinksTest(unittest.TestCase):
    def test_set_replaces_and_resets(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server, "LINKS_FILE", os.path.join(tmp, "links.json")):
                server.api_link_set({"id": "debit-tbank-black", "url": "https://example.com/ref"})
                self.assertEqual(server.api_links()["items"]["debit-tbank-black"], "https://example.com/ref")

                merged = server._apply_links(
                    [{"id": "debit-tbank-black", "url": "https://bank.example"}],
                    server._load_links(),
                )
                self.assertEqual(merged[0]["url"], "https://example.com/ref")

                server.api_link_set({"id": "debit-tbank-black", "url": ""})
                self.assertEqual(server.api_links()["items"], {})

    def test_only_https_and_known_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server, "LINKS_FILE", os.path.join(tmp, "links.json")):
                with self.assertRaises(ValueError):
                    server.api_link_set({"id": "debit-tbank-black", "url": "http://example.com"})
                with self.assertRaises(ValueError):
                    server.api_link_set({"url": "https://example.com"})

    def test_cards_use_override(self):
        cards = {"items": [{"id": "credit-tbank-platinum", "url": "https://bank.example"}]}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(server, "CARDS_FILE", os.path.join(tmp, "cards.json")), \
                    patch.object(server, "LINKS_FILE", os.path.join(tmp, "links.json")):
                with open(os.path.join(tmp, "cards.json"), "w", encoding="utf-8") as file:
                    import json

                    json.dump(cards, file)
                server.api_link_set({"id": "credit-tbank-platinum", "url": "https://partner.example/ref"})
                items = server.api_cards()["items"]
                self.assertEqual(items[0]["url"], "https://partner.example/ref")


if __name__ == "__main__":
    unittest.main()
