import unittest
from pathlib import Path


class ReadmeArchitectureTest(unittest.TestCase):
    def test_readme_recommends_hook_first_and_lens_optional(self):
        text = Path('README.md').read_text(encoding='utf-8')
        self.assertIn('推荐默认路径: UserPromptSubmit hook', text)
        self.assertIn('lens 是可选的 Anthropic API 代理', text)
        self.assertIn('不要同时启用 lens wake_memory 插件和 UserPromptSubmit hook', text)
        self.assertNotIn('集成 A (lens 代理)', text)
        self.assertNotIn('lens/proxy.py` | 内置 Anthropic API 代理(集成 A', text)


if __name__ == '__main__':
    unittest.main()
