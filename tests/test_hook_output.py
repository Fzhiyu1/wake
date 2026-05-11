import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class HookOutputTest(unittest.TestCase):
    def test_hook_prints_memory_prefix_for_non_empty_recall(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            temp_repo = Path(td)
            shutil.copy2(repo / "hook.sh", temp_repo / "hook.sh")
            (temp_repo / "daemon.py").write_text("# test placeholder\n", encoding="utf-8")

            fake_python = temp_repo / ".venv" / "bin" / "python3"
            fake_python.parent.mkdir(parents=True)
            fake_python.write_text(
                "#!/bin/sh\n"
                "echo '[[形状记忆系统]] 浮起来。'\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            proc = subprocess.run(
                [str(temp_repo / "hook.sh")],
                input=json.dumps({"prompt": "形状记忆系统"}),
                text=True,
                capture_output=True,
                cwd=temp_repo,
                timeout=5,
            )

            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "[记忆] [[形状记忆系统]] 浮起来。")


if __name__ == "__main__":
    unittest.main()
