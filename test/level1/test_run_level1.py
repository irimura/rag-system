import math
import unittest

import run_level1


class RetrievalScoringTest(unittest.TestCase):
    def setUp(self):
        self.case = {
            "evidence": [
                {"doc_id": "law-a", "quote": "first evidence"},
                {"doc_id": "law-a", "quote": "second evidence"},
            ]
        }

    def test_doc_id_match_without_quote_is_not_a_hit(self):
        chunk = {"page_content": "unrelated", "metadata": {"source": "law-a.md"}}
        self.assertEqual(run_level1.matching_evidence(self.case, chunk), set())

    def test_ndcg_uses_all_golden_evidence_for_idcg(self):
        chunks = [{"page_content": "first evidence", "metadata": {}}]
        score = run_level1.score_ranking(self.case, chunks, 5)
        expected = 1.0 / (1.0 + 1.0 / math.log2(3))
        self.assertAlmostEqual(score["ndcg"], expected)
        self.assertEqual(score["evidence_recall"], 0.5)

    def test_duplicate_match_is_not_counted_twice(self):
        chunks = [
            {"page_content": "first evidence", "metadata": {}},
            {"page_content": "first evidence repeated", "metadata": {}},
        ]
        score = run_level1.score_ranking(self.case, chunks, 5)
        self.assertAlmostEqual(score["ndcg"], 1.0 / (1.0 + 1.0 / math.log2(3)))
        self.assertEqual(score["evidence_recall"], 0.5)


if __name__ == "__main__":
    unittest.main()