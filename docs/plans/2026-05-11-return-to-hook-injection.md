# Return to Hook Injection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace lens-based wake injection with Claude Code `UserPromptSubmit` hook injection, while keeping Anthropic networking on the normal proxy path.

**Architecture:** Wake becomes an input-side hook only: Claude Code calls `hook.sh` once per user prompt, `hook.sh` calls `daemon.py`, and hook stdout injects `[记忆] ...` into the current turn. Lens is removed from the active Anthropic request path so it no longer intercepts `/messages`, re-invokes wake after tool calls, or rewrites `system` blocks.

**Tech Stack:** Claude Code settings JSON, zsh environment configuration, Bash hook script, Python wake daemon, unittest.

---

### Task 1: Add hook output format regression test

**Files:**
- Create: `tests/test_hook_output.py`
- Read/Modify only if needed: `hook.sh`

**Step 1: Write the failing test**

Create `tests/test_hook_output.py`:

```python
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class HookOutputTest(unittest.TestCase):
    def test_hook_prints_memory_prefix_for_non_empty_recall(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            fake_python = Path(td) / "python3"
            fake_python.write_text(
                "#!/bin/sh\n"
                "echo '[[形状记忆系统]] 浮起来。'\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            venv_bin = repo / ".venv" / "bin"
            original = venv_bin / "python3"
            backup = venv_bin / "python3.real-for-hook-test"

            if backup.exists():
                backup.unlink()
            original.rename(backup)
            try:
                original.symlink_to(fake_python)
                proc = subprocess.run(
                    [str(repo / "hook.sh")],
                    input=json.dumps({"prompt": "形状记忆系统"}),
                    text=True,
                    capture_output=True,
                    cwd=repo,
                    timeout=5,
                )
            finally:
                original.unlink()
                backup.rename(original)

            self.assertEqual(proc.returncode, 0)
            self.assertEqual(proc.stdout.strip(), "[记忆] [[形状记忆系统]] 浮起来。")
```

**Step 2: Run test to verify it passes or identify existing hook breakage**

Run:

```bash
/path/to/wake/.venv/bin/python3 -m unittest tests.test_hook_output
```

Expected: PASS if `hook.sh` still emits `[记忆] ...` correctly. If it fails, inspect only `hook.sh` and fix the hook output path before continuing.

**Step 3: Commit if code changed**

If only a test was added and it passes:

```bash
git add tests/test_hook_output.py
git commit -m "test: cover wake hook output"
```

If `hook.sh` required changes:

```bash
git add hook.sh tests/test_hook_output.py
git commit -m "fix: restore wake hook output"
```

---

### Task 2: Add wake hook to Claude Code UserPromptSubmit hooks

**Files:**
- Modify: `~/.claude/settings.json`
- Read: `/path/to/wake/hook.sh`

**Step 1: Inspect current hook section**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('~/.claude/settings.json')
d = json.loads(p.read_text())
print(json.dumps(d.get('hooks', {}).get('UserPromptSubmit', []), ensure_ascii=False, indent=2))
PY
```

Expected: existing peon hooks are present, wake hook is absent.

**Step 2: Add wake hook entry idempotently**

Run this exact script:

```bash
python3 - <<'PY'
import json
from pathlib import Path

p = Path('~/.claude/settings.json')
d = json.loads(p.read_text())
hooks = d.setdefault('hooks', {})
entries = hooks.setdefault('UserPromptSubmit', [])
command = '/path/to/wake/hook.sh'

already = any(
    hook.get('command') == command
    for entry in entries
    for hook in entry.get('hooks', [])
)

if not already:
    entries.append({
        'matcher': '',
        'hooks': [{
            'type': 'command',
            'command': command,
            'timeout': 20,
        }],
    })

p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n')
PY
```

**Step 3: Verify JSON and hook presence**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('~/.claude/settings.json')
d = json.loads(p.read_text())
commands = [
    hook.get('command')
    for entry in d.get('hooks', {}).get('UserPromptSubmit', [])
    for hook in entry.get('hooks', [])
]
assert '/path/to/wake/hook.sh' in commands
print('wake hook configured')
PY
```

Expected: prints `wake hook configured`.

**Step 4: Do not commit global settings**

Do not commit `~/.claude/settings.json`; it is outside this repo and user-global state.

---

### Task 3: Remove lens from active Anthropic path

**Files:**
- Modify: `~/.zshrc`

**Step 1: Inspect existing lens/proxy environment lines**

Run:

```bash
grep -n "ANTHROPIC_BASE_URL\|LENS_PLUGINS\|LENS_UPSTREAM_PROXY\|HTTP_PROXY\|HTTPS_PROXY\|wake / lens" ~/.zshrc
```

Expected: `LENS_UPSTREAM_PROXY` may be present; `ANTHROPIC_BASE_URL=http://localhost:8765` may or may not be present.

**Step 2: Update `.zshrc` manually with these rules**

Keep normal network proxy lines available to Claude Code:

```bash
export HTTP_PROXY=http://your-proxy:port
export HTTPS_PROXY=http://your-proxy:port
```

Disable lens as an active API base URL by removing or commenting any line like:

```bash
export ANTHROPIC_BASE_URL=http://localhost:8765
```

Leave `LENS_UPSTREAM_PROXY` only if you still want to run lens manually for experiments; it must not matter when `ANTHROPIC_BASE_URL` is unset.

**Step 3: Verify shell config no longer routes Claude through lens**

Run:

```bash
grep -n "ANTHROPIC_BASE_URL=http://localhost:8765" ~/.zshrc || true
```

Expected: no uncommented active export line for `ANTHROPIC_BASE_URL=http://localhost:8765`.

**Step 4: Stop current lens process**

Run:

```bash
pgrep -lf 'lens/proxy.py' || true
```

If a lens process exists, stop only that PID:

```bash
kill <PID>
```

Then verify:

```bash
pgrep -lf 'lens/proxy.py' || true
```

Expected: no running `lens/proxy.py` process.

**Step 5: No repo commit for shell config**

Do not commit `~/.zshrc`; it is user-global state.

---

### Task 4: Verify hook and daemon still work independently

**Files:**
- Read: `hook.sh`
- Read: `data/recall.jsonl`

**Step 1: Run hook with a test prompt**

Run:

```bash
printf '%s' '{"prompt":"形状记忆系统"}' | /path/to/wake/hook.sh
```

Expected if DeepSeek balance is available: either no output or a line beginning with `[记忆] `. Expected if balance is still insufficient: no output, because `hook.sh` currently suppresses daemon stderr.

**Step 2: Run daemon directly to expose DeepSeek/cache status**

Run:

```bash
/path/to/wake/.venv/bin/python3 /path/to/wake/daemon.py '形状记忆系统'
```

Expected if DeepSeek balance is unavailable: `402 Insufficient Balance`. Expected if available: stderr includes `cache_hit=` and `cache_miss=`, stdout contains recall text or `——`.

**Step 3: Verify new recall logs include cache fields after a successful daemon call**

Only if Step 2 succeeded, run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('/path/to/wake/data/recall.jsonl')
row = json.loads(p.read_text(encoding='utf-8').splitlines()[-1])
for key in ['prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'context_sha256', 'context_bytes']:
    assert key in row, key
print({k: row[k] for k in ['prompt_cache_hit_tokens', 'prompt_cache_miss_tokens', 'context_bytes']})
PY
```

Expected: prints cache hit/miss values and context byte count.

---

### Task 5: Update README architecture notes

**Files:**
- Modify: `README.md`

**Step 1: Write a failing documentation check**

Create `tests/test_readme_architecture.py`:

```python
import unittest
from pathlib import Path


class ReadmeArchitectureTest(unittest.TestCase):
    def test_readme_recommends_hook_first_and_lens_optional(self):
        text = Path('README.md').read_text(encoding='utf-8')
        self.assertIn('推荐默认路径: UserPromptSubmit hook', text)
        self.assertIn('lens 是可选的 Anthropic API 代理', text)
        self.assertIn('不要同时启用 lens wake_memory 插件和 UserPromptSubmit hook', text)


if __name__ == '__main__':
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run:

```bash
/path/to/wake/.venv/bin/python3 -m unittest tests.test_readme_architecture
```

Expected: FAIL because README still describes lens as a main path and does not warn against double injection clearly enough.

**Step 3: Update README minimally**

Edit `README.md` so the usage section says:

```markdown
推荐默认路径: UserPromptSubmit hook

默认推荐把 wake 作为 Claude Code 的 UserPromptSubmit hook 使用。hook 只在用户提交 prompt 时触发一次,不会在工具调用续跑时重新召回,也不会改写 Anthropic `/messages` 请求体。

lens 是可选的 Anthropic API 代理

`lens/` 可以作为透明 Anthropic API 代理或实验性请求改写层使用。常规 wake 使用不需要 lens。如果启用 lens,默认应设置 `LENS_PLUGINS=` 让它不加载 `wake_memory`。

不要同时启用 lens wake_memory 插件和 UserPromptSubmit hook

两者同时启用会造成双重注入。`wake_memory` 插件还会在每个 `/messages` 请求触发,包括工具调用后的续跑请求,可能覆盖上一轮注入的记忆块并影响 prompt cache。
```

Keep old lens documentation as an advanced/experimental section if still useful, but it must no longer be the recommended default.

**Step 4: Run documentation test to verify it passes**

Run:

```bash
/path/to/wake/.venv/bin/python3 -m unittest tests.test_readme_architecture
```

Expected: PASS.

**Step 5: Run all tests**

Run:

```bash
/path/to/wake/.venv/bin/python3 -m unittest discover -s tests
```

Expected: all tests PASS.

**Step 6: Commit README/test changes**

```bash
git add README.md tests/test_readme_architecture.py
git commit -m "docs: recommend hook-based wake injection"
```

---

### Task 6: Final verification checklist

**Files:**
- Check: `~/.claude/settings.json`
- Check: `~/.zshrc`
- Check: `README.md`
- Check: `tests/`

**Step 1: Verify no active lens process**

Run:

```bash
pgrep -lf 'lens/proxy.py' || true
```

Expected: no active lens process unless intentionally running manual experiments.

**Step 2: Verify Claude Code will not use lens by default**

Run:

```bash
grep -n "ANTHROPIC_BASE_URL=http://localhost:8765" ~/.zshrc || true
```

Expected: no active uncommented export.

**Step 3: Verify wake hook configured**

Run:

```bash
python3 - <<'PY'
import json
from pathlib import Path
p = Path('~/.claude/settings.json')
d = json.loads(p.read_text())
commands = [
    hook.get('command')
    for entry in d.get('hooks', {}).get('UserPromptSubmit', [])
    for hook in entry.get('hooks', [])
]
print('/path/to/wake/hook.sh' in commands)
PY
```

Expected: `True`.

**Step 4: Verify tests**

Run:

```bash
/path/to/wake/.venv/bin/python3 -m unittest discover -s tests
```

Expected: all tests PASS.

**Step 5: Inspect git diff**

Run:

```bash
git status --short
git diff -- README.md daemon.py tests/test_daemon_recall_logging.py tests/test_hook_output.py tests/test_readme_architecture.py docs/plans/2026-05-11-return-to-hook-injection.md
```

Expected: repo changes are limited to wake source/docs/tests/plan. Global config changes are not in git.

**Step 6: Final commit for plan if not already committed**

```bash
git add docs/plans/2026-05-11-return-to-hook-injection.md
git commit -m "docs: plan hook-based wake injection"
```

Skip commit if the user does not want plan docs committed.
