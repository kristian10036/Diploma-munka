import math
import unittest
import io
import json
import urllib.error
from unittest.mock import patch

from app.rag import (EMBEDDING_DIMENSIONS, RagSettings, chunk_text, embedding_dimensions,
                     local_hash_embeddings, ollama_embeddings, vector_literal)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class RagTest(unittest.TestCase):
    def test_chunking_is_bounded_and_overlapping(self):
        chunks = chunk_text(" ".join(f"word-{index}" for index in range(500)), 300, 50)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(0 < len(chunk) <= 300 for chunk in chunks))

    def test_local_embeddings_are_normalized_and_retrieval_oriented(self):
        wifi, wifi_query, bluetooth = local_hash_embeddings(
            ["wifi access point ssid channel", "wifi ssid channel", "bluetooth ble service"]
        )
        dot = lambda left, right: sum(a * b for a, b in zip(left, right))
        self.assertAlmostEqual(math.sqrt(dot(wifi, wifi)), 1.0)
        self.assertGreater(dot(wifi, wifi_query), dot(wifi, bluetooth))
        self.assertEqual(len(wifi), EMBEDDING_DIMENSIONS)

    def test_vector_literal_validates_dimensions(self):
        value = vector_literal([0.0] * EMBEDDING_DIMENSIONS)
        self.assertTrue(value.startswith("[") and value.endswith("]"))
        with self.assertRaisesRegex(ValueError, "invalid embedding"):
            vector_literal([0.0, 1.0])

    def test_bge_m3_batch_embedding_and_dimension(self):
        settings = RagSettings(True, "ollama", "bge-m3", "http://ollama:11434", 3, 1200, 200, 5)
        dimensions = embedding_dimensions("ollama", "bge-m3")
        payload = json.dumps({"embeddings": [[0.0] * dimensions, [1.0] * dimensions]}).encode()
        with patch("app.rag.urllib.request.urlopen", return_value=FakeResponse(payload)) as urlopen:
            vectors = ollama_embeddings(settings, ["egy", "kettő"])
        self.assertEqual([len(vector) for vector in vectors], [1024, 1024])
        request_body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(request_body["input"], ["egy", "kettő"])
        self.assertEqual(request_body["model"], "bge-m3")

    def test_embedding_rejects_invalid_response_and_dimension(self):
        settings = RagSettings(True, "ollama", "bge-m3", "http://ollama:11434", 3, 1200, 200, 5)
        with patch("app.rag.urllib.request.urlopen", return_value=FakeResponse(b'{"bad":[]}')):
            with self.assertRaisesRegex(RuntimeError, "invalid_response"):
                ollama_embeddings(settings, ["szöveg"])
        with patch("app.rag.urllib.request.urlopen", return_value=FakeResponse(b'{"embeddings":[[1.0,2.0]]}')):
            with self.assertRaisesRegex(RuntimeError, "invalid_dimensions"):
                ollama_embeddings(settings, ["szöveg"])

    def test_embedding_handles_offline_and_missing_model(self):
        settings = RagSettings(True, "ollama", "bge-m3", "http://ollama:11434", 3, 1200, 200, 5)
        with patch("app.rag.urllib.request.urlopen", side_effect=urllib.error.URLError("offline")), patch("app.rag.time.sleep"):
            with self.assertRaisesRegex(RuntimeError, "provider_unavailable"):
                ollama_embeddings(settings, ["szöveg"])
        missing = urllib.error.HTTPError("http://ollama/api/embed", 404, "not found", {}, io.BytesIO(b'{"error":"model not found"}'))
        with patch("app.rag.urllib.request.urlopen", side_effect=missing):
            with self.assertRaisesRegex(RuntimeError, "model_not_installed"):
                ollama_embeddings(settings, ["szöveg"])


if __name__ == "__main__":
    unittest.main()
