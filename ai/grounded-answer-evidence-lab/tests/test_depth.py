import unittest
from unittest.mock import patch

import audit as module


class DocumentIndexTests(unittest.TestCase):
    def test_many_claims_hash_each_source_only_once(self):
        text = "합성 문서는 확인 가능한 인용과 명시적 한계를 포함합니다. " * 100
        quote = "합성 문서는 확인 가능한 인용과 명시적 한계를 포함합니다."
        citation = {
            "source_id": "doc",
            "quote": quote,
            "source_sha256": module.digest(text),
        }
        payload = {
            "documents": [{"id": "doc", "text": text}],
            "claims": [
                {"statement": f"합성 주장 {i}", "citations": [citation]}
                for i in range(1000)
            ],
        }
        original = module.digest
        inputs = []

        def recorded(value):
            inputs.append(value)
            return original(value)

        with patch.object(module, "digest", side_effect=recorded):
            result = module.audit(payload)
        self.assertTrue(result["traceable"])
        self.assertEqual(sum(value == text for value in inputs), 1)

    def test_duplicate_quote_after_whitespace_normalization_stays_rejected(self):
        text = "합성 문서는 확인 가능한 인용과 명시적 한계를 포함합니다."
        citation = {
            "source_id": "doc",
            "quote": text,
            "source_sha256": module.digest(text),
        }
        variant = dict(citation, quote=text.replace(" ", "\n  "))
        result = module.audit(
            {
                "documents": [{"id": "doc", "text": text}],
                "claims": [
                    {"statement": "합성 주장", "citations": [citation, variant]}
                ],
            }
        )
        self.assertIn("중복 인용", result["results"][0]["problems"])
