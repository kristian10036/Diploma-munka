import json
import unittest

from app.assistant import (
    AssistantSettings,
    build_grounded_prompt,
    is_mac_inventory_question,
    model_is_installed,
    normalize_ollama_answer,
    select_context_kinds,
)


def _extract_payload(prompt: str) -> dict:
    start = prompt.index("Structured context: ") + len("Structured context: ")
    end = prompt.index("\n\nQuestion:")
    return json.loads(prompt[start:end])


class AssistantTest(unittest.TestCase):
    def test_selects_relevant_context_without_keyword_sql(self):
        self.assertEqual(
            select_context_kinds("Milyen Wi-Fi és Bluetooth eszközök voltak?"),
            ("wifi", "bluetooth"),
        )
        self.assertEqual(
            select_context_kinds("Adj teljes összefoglalót"),
            ("sessions", "wifi", "bluetooth", "peaks", "anomalies"),
        )
        self.assertEqual(
            select_context_kinds("Foglald össze az adatokat"),
            ("sessions", "wifi", "bluetooth", "peaks", "anomalies"),
        )

    def test_prompt_requires_grounding_and_source_ids(self):
        prompt = build_grounded_prompt(
            "Mi történt?",
            {"anomalies": [{"id": "a-1", "severity": 3}]},
            [{"record_type": "anomalies", "record_id": "a-1"}],
        )
        self.assertIn("Never invent", prompt)
        self.assertIn("record_type:record_id", prompt)
        self.assertIn("Hungarian (hu)", prompt)
        self.assertIn("a-1", prompt)
        self.assertLessEqual(
            len(
                build_grounded_prompt(
                    "Mi történt?",
                    {"wifi": [{"id": str(i), "ssid": "x" * 1000} for i in range(20)]},
                    [],
                )
            ),
            7000,
        )

    def test_disabled_status_is_generation_only(self):
        settings = AssistantSettings(False, "http://ollama:11434", "", 20, 10)
        status = settings.status()
        self.assertTrue(status["implemented"])
        self.assertFalse(status["enabled"])
        self.assertFalse(status["available"])
        self.assertEqual(status["status"], "disabled")
        self.assertNotIn("rag_available", status)
        self.assertNotIn("rag_status", status)

    def test_enabled_without_model_is_explicit(self):
        settings = AssistantSettings(True, "http://ollama:11434", "", 20, 10)
        status = settings.status()
        self.assertTrue(status["enabled"])
        self.assertFalse(status["available"])
        self.assertEqual(status["status"], "model_not_configured")

    def test_implicit_latest_model_name_matches_ollama_list(self):
        self.assertTrue(model_is_installed("bge-m3", {"bge-m3:latest"}))
        self.assertTrue(model_is_installed("qwen3:8b", {"qwen3:8b"}))
        self.assertFalse(model_is_installed("missing", {"bge-m3:latest"}))

    def test_complete_mac_inventory_question_is_detected_without_matching_counts(self):
        self.assertTrue(is_mac_inventory_question("Sorold fel az összes látható MAC-címet"))
        self.assertTrue(is_mac_inventory_question("Mutasd a teljes BSSID listát"))
        self.assertFalse(is_mac_inventory_question("Hány Bluetooth MAC-cím van?"))
        self.assertFalse(is_mac_inventory_question("Milyen Wi-Fi eszközök láthatók?"))

    def test_normalizes_json_wrapped_model_answer(self):
        self.assertEqual(normalize_ollama_answer('{"answer":"Emberi válasz."}'), "Emberi válasz.")
        self.assertEqual(normalize_ollama_answer("Egyszerű szöveg."), "Egyszerű szöveg.")

    def test_many_populated_kinds_do_not_collapse_to_one_record_each(self):
        context = {
            kind: [{"id": f"{kind}-{i}", "field": "value"} for i in range(5)]
            for kind in ("sessions", "wifi", "bluetooth", "peaks", "anomalies")
        }
        prompt = build_grounded_prompt("Adj összefoglalót", context, [])
        payload = _extract_payload(prompt)
        self.assertEqual(len(payload["context"]), 5)
        for kind, block in payload["context"].items():
            self.assertEqual(block["supplied_count"], 5)
            self.assertGreater(
                len(block["records"]), 1, f"{kind} collapsed to <=1 record despite ample budget"
            )

    def test_oversized_context_drops_whole_records_not_a_blind_char_cut(self):
        context = {
            kind: [{"id": f"{kind}-{i}", "field": "v" * 200} for i in range(50)]
            for kind in ("sessions", "wifi", "bluetooth", "peaks", "anomalies")
        }
        sources = [{"record_type": "wifi", "record_id": f"wifi-{i}"} for i in range(50)]
        prompt = build_grounded_prompt(
            "Adj összefoglalót", context, sources, max_prompt_chars=4000, max_source_records=20
        )
        self.assertNotIn("TRUNCATED", prompt)
        start = prompt.index("Structured context: ") + len("Structured context: ")
        end = prompt.index("\n\nQuestion:")
        payload_text = prompt[start:end]
        self.assertLessEqual(len(payload_text), 4000)
        payload = json.loads(payload_text)  # raises if the payload is malformed JSON
        for block in payload["context"].values():
            self.assertEqual(block["supplied_count"], 50)
            self.assertLessEqual(len(block["records"]), 50)
        self.assertLessEqual(len(payload["source_records"]), 20)

    def test_settings_from_env_parses_new_budget_knobs(self):
        import os

        previous = {
            key: os.environ.get(key)
            for key in (
                "ASSISTANT_MAX_PROMPT_CHARS",
                "ASSISTANT_MAX_SOURCE_RECORDS",
                "ASSISTANT_NUM_PREDICT",
            )
        }
        try:
            os.environ["ASSISTANT_MAX_PROMPT_CHARS"] = "99999999"
            os.environ["ASSISTANT_MAX_SOURCE_RECORDS"] = "0"
            os.environ["ASSISTANT_NUM_PREDICT"] = "9999999"
            settings = AssistantSettings.from_env()
            self.assertEqual(settings.max_prompt_chars, 60_000)
            self.assertEqual(settings.max_source_records, 1)
            self.assertEqual(settings.num_predict, 2048)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
