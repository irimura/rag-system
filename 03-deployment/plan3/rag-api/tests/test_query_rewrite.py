import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).parents[1] / "query_rewrite.py"
spec = importlib.util.spec_from_file_location("query_rewrite", MODULE_PATH)
query_rewrite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(query_rewrite)


class QueryRewritePromptTest(unittest.TestCase):
    def test_prompt_contains_previous_query_and_attempt(self):
        prompt = query_rewrite.build_rewrite_prompt("休暇制度は？", ["休暇制度"], 1)
        self.assertIn("- 休暇制度", prompt)
        self.assertIn("試行回数: 1", prompt)

    def test_retry_prompts_change_with_search_history(self):
        first = query_rewrite.build_rewrite_prompt("休暇制度は？", ["休暇制度"], 1)
        second = query_rewrite.build_rewrite_prompt("休暇制度は？", ["休暇制度", "年次有給休暇"], 2)
        self.assertNotEqual(first, second)
        self.assertIn("年次有給休暇", second)

    def test_attempt_must_be_positive(self):
        with self.assertRaises(ValueError):
            query_rewrite.build_rewrite_prompt("質問", ["検索"], 0)


if __name__ == "__main__":
    unittest.main()
