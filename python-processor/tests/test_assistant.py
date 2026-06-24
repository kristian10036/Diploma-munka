import unittest

from app.assistant import (AssistantSettings, build_grounded_prompt, is_mac_inventory_question,
                           model_is_installed, normalize_ollama_answer, select_context_kinds)


class AssistantTest(unittest.TestCase):
    def test_selects_relevant_context_without_keyword_sql(self):
        self.assertEqual(select_context_kinds("Milyen Wi-Fi és Bluetooth eszközök voltak?"), ("wifi", "bluetooth"))
        self.assertEqual(select_context_kinds("Adj teljes összefoglalót"), ("sessions", "wifi", "bluetooth", "peaks", "anomalies"))
        self.assertEqual(select_context_kinds("Foglald össze az adatokat"), ("sessions", "wifi", "bluetooth", "peaks", "anomalies"))

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
        self.assertLessEqual(len(build_grounded_prompt("Mi történt?", {"wifi": [{"id": str(i), "ssid": "x" * 1000} for i in range(20)]}, [])), 7000)

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

if __name__ == "__main__":
    unittest.main()
