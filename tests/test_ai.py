import io
import json
import os
import sys
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class YandexGptTest(unittest.TestCase):
    def test_question_required(self):
        with self.assertRaises(ValueError):
            server.api_ai({})

    def test_config_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                server.api_ai({"question": "Что в портфеле?"})
        self.assertIn("YANDEX_GPT_API_KEY", str(ctx.exception))

    def test_answer(self):
        payload = {"result": {"alternatives": [{"message": {"text": "Короткий ответ"}}]}}
        env = {"YANDEX_GPT_API_KEY": "test-key", "YANDEX_GPT_FOLDER_ID": "test-folder"}
        with patch.dict(os.environ, env, clear=True), patch(
            "server.urllib.request.urlopen", return_value=FakeResponse(payload)
        ) as open_mock:
            result = server.api_ai({"question": "Что в портфеле?", "context": "{}"})
        self.assertEqual(result["answer"], "Короткий ответ")
        request = open_mock.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["modelUri"], "gpt://test-folder/yandexgpt-lite/latest")
        self.assertEqual(request.get_header("Authorization"), "Api-Key test-key")

    def test_auth_error_message(self):
        error = urllib.error.HTTPError("https://example.test", 401, "Unauthorized", {}, io.BytesIO(b"{}"))
        env = {"YANDEX_GPT_API_KEY": "test-key", "YANDEX_GPT_FOLDER_ID": "test-folder"}
        with patch.dict(os.environ, env, clear=True), patch(
            "server.urllib.request.urlopen", side_effect=error
        ):
            with self.assertRaises(RuntimeError) as ctx:
                server.api_ai({"question": "Что в портфеле?"})
        self.assertIn("отклонил ключ", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
