import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import daemon


class RecallLoggingTest(unittest.TestCase):
    def test_recall_logs_deepseek_cache_usage_and_context_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            (tmp / "system-prompt.md").write_text("system", encoding="utf-8")
            (tmp / "kb-snapshot.txt").write_text("kb", encoding="utf-8")

            usage = SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=2,
                prompt_cache_hit_tokens=7,
                prompt_cache_miss_tokens=3,
            )
            response = SimpleNamespace(
                choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="[[x]]"))],
                usage=usage,
            )
            client = SimpleNamespace(
                chat=SimpleNamespace(
                    completions=SimpleNamespace(create=lambda **kwargs: response)
                )
            )

            with patch.object(daemon, "WAKE_DIR", tmp), \
                 patch.object(daemon, "SYSTEM_PROMPT", tmp / "system-prompt.md"), \
                 patch.object(daemon, "KB_SNAPSHOT", tmp / "kb-snapshot.txt"), \
                 patch.object(daemon, "KB_INDEX", tmp / "kb-index.json"), \
                 patch.object(daemon, "create_client", return_value=client):
                daemon.recall("query")

            rows = (tmp / "data" / "recall.jsonl").read_text(encoding="utf-8").splitlines()
            row = json.loads(rows[-1])
            expected_context = "system\n\n---\n\n以下是完整知识库：\n\nkb"
            self.assertEqual(row["prompt_cache_hit_tokens"], 7)
            self.assertEqual(row["prompt_cache_miss_tokens"], 3)
            self.assertEqual(row["context_bytes"], len(expected_context.encode("utf-8")))
            self.assertRegex(row["context_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
