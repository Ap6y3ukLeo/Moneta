import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class RealtyPhotosTest(unittest.TestCase):
    def test_yandex_offer_images(self):
        html = (
            '<script>window.INITIAL_STATE = '
            '{"offerCard":{"card":{"mainImages":["//img.example/a/main","//img.example/b/main"]}}}'
            ' </script>'
        )
        with patch.object(server, "http_text", return_value=html):
            result = server.api_realty_photos({"id": "yandex:123"})
        self.assertEqual(result["images"], [
            "https://img.example/a/main",
            "https://img.example/b/main",
        ])

    def test_non_yandex_has_no_gallery(self):
        result = server.api_realty_photos({"id": "avito:123"})
        self.assertEqual(result["images"], [])


if __name__ == "__main__":
    unittest.main()
