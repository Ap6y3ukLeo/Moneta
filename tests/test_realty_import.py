import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

ROW = {
    "id": "yandex:1",
    "url": "https://realty.yandex.ru/offer/1/",
    "title": "2-комн. квартира, 54 м²",
    "price": 12_000_000,
    "city": "Москва",
    "img": "https://avatars.mds.yandex.net/a/app_middle",
    "rooms": "2",
    "area": 54.0,
}


class RealtyImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = os.path.join(self.tmp.name, "cache")
        self.bundled = os.path.join(self.tmp.name, "bundled")
        os.makedirs(self.cache)
        os.makedirs(self.bundled)
        for item in (
            patch.object(server, "CACHE_DIR", self.cache),
            patch.object(server, "BUNDLED_CACHE_DIR", self.bundled),
            patch.object(server, "MEM", {}),
            patch.object(server, "REALTY_IMAGES", None),
        ):
            item.start()
            self.addCleanup(item.stop)

    def cached(self):
        with open(os.path.join(self.cache, "realty_yandex.json"), encoding="utf-8") as file:
            return json.load(file)["value"]

    def test_import_and_merge(self):
        result = server.api_realty_import({"source": "yandex", "items": [ROW], "reset": True})
        self.assertEqual(result["items"], 1)
        self.assertEqual(self.cached()[0]["id"], "yandex:1")

        second = dict(ROW, id="yandex:2", url="https://realty.yandex.ru/offer/2/")
        server.api_realty_import({"source": "yandex", "items": [second]})
        self.assertEqual({item["id"] for item in self.cached()}, {"yandex:1", "yandex:2"})

        server.api_realty_import({"source": "yandex", "items": [ROW], "reset": True})
        self.assertEqual([item["id"] for item in self.cached()], ["yandex:1"])

    def test_galleries_saved(self):
        server.api_realty_import({
            "source": "yandex",
            "items": [ROW],
            "galleries": {"yandex:1": ["https://img.example/a.jpg", "http://bad.example/b.jpg"]},
        })
        with open(os.path.join(self.bundled, "realty_images.json"), encoding="utf-8") as file:
            saved = json.load(file)
        self.assertEqual(saved["yandex:1"], ["https://img.example/a.jpg"])

    def test_images_only_update(self):
        server.api_realty_import({"source": "yandex", "items": [ROW], "reset": True})
        result = server.api_realty_import({
            "source": "yandex",
            "images": {"yandex:1": "https://avatars.mds.yandex.net/b/app_large"},
        })
        self.assertEqual(result["updated"], 1)
        self.assertEqual(self.cached()[0]["img"], "https://avatars.mds.yandex.net/b/app_large")

    def test_avito_raw_rows(self):
        row = {
            "id": "123456",
            "title": "2-к. квартира, 54,2 м², 12/22 эт.",
            "url": "https://www.avito.ru/moskva/kvartiry/2-k_kvartira_54_m_123456",
            "price": "12000000",
            "img": "https://img.avito.st/image/1/1.abc",
            "addr": "Москва, ул. Тверская",
            "text": "2-к. квартира, 54,2 м²\n12 000 000 ₽",
        }
        result = server.api_realty_import({"source": "avito", "rows": [row], "reset": True})
        self.assertEqual(result["items"], 1)
        with open(os.path.join(self.cache, "realty_avito.json"), encoding="utf-8") as file:
            cached = json.load(file)["value"]
        self.assertEqual(cached[0]["id"], "avito:123456")
        self.assertEqual(cached[0]["img"], "https://img.avito.st/image/1/1.abc")

    def test_rejects_bad_rows(self):
        with self.assertRaises(ValueError):
            server.api_realty_import({"source": "nope", "items": [ROW]})
        with self.assertRaises(ValueError):
            server.api_realty_import({"source": "yandex", "items": []})
        with self.assertRaises(ValueError):
            server.api_realty_import({"source": "yandex", "items": [dict(ROW, price=0)]})
        with self.assertRaises(ValueError):
            server.api_realty_import({"source": "yandex", "items": [dict(ROW, url="javascript:1")]})


if __name__ == "__main__":
    unittest.main()
