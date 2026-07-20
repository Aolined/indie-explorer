import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "update_catalog.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("update_catalog", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class UpdateCatalogTests(unittest.TestCase):
    def test_canonical_url_removes_common_tracking_variants(self):
        first = MODULE.canonical_url("http://www.Example.com/tool/?utm_source=test&b=2")
        second = MODULE.canonical_url("https://example.com/tool?b=2")

        self.assertEqual(first, second)

    def test_parses_vibe_timeline_and_skips_fenced_example(self):
        text = """```
* :white_check_mark: [示例](https://example.invalid)：不要收录
```
**[EloLin](https://github.com/DevEloLin)**

* :white_check_mark: [EloGames](https://games.elolin.com)：网页游戏平台
"""

        projects = MODULE.parse_vibe_readme(text)

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["name"], "EloGames")
        self.assertEqual(projects[0]["author"], "EloLin")
        self.assertEqual(projects[0]["github"], "https://github.com/DevEloLin")

    def test_parses_curated_project_table(self):
        text = """| 类别 | 开发者 | 项目名称 | 链接 | 简介 |
| --- | --- | --- | --- | --- |
| **游戏工具** | 玩家团队 | **Calculator** | [访问](https://tool.example/) | **社区工具：** 计算配方。 |
"""

        projects = MODULE.parse_curated_table(text)

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["name"], "Calculator")
        self.assertEqual(projects[0]["category"], "游戏工具")
        self.assertEqual(projects[0]["description"], "社区工具： 计算配方。")

    def test_merge_catalog_keeps_the_first_source_for_duplicates(self):
        first_source = {
            "id": "first/repo",
            "name": "First",
            "url": "https://github.com/first/repo",
            "license": "CC0",
        }
        second_source = {
            "id": "second/repo",
            "name": "Second",
            "url": "https://github.com/second/repo",
            "license": "MIT",
        }
        first = [{"name": "A", "url": "https://example.com/", "status": "online"}]
        second = [
            {"name": "Duplicate", "url": "http://www.example.com", "status": "online"},
            {"name": "B", "url": "https://other.example", "status": "online"},
        ]

        projects, sources = MODULE.merge_catalog(
            [(first_source, first), (second_source, second)]
        )

        self.assertEqual([project["name"] for project in projects], ["A", "B"])
        self.assertEqual(projects[0]["source"], "first/repo")
        self.assertEqual(sources[1]["duplicate_count"], 1)
        self.assertEqual(sources[1]["contributed_count"], 1)

    def test_merge_catalog_preserves_primary_source_entries_sharing_a_url(self):
        source = {
            "id": "primary/repo",
            "name": "Primary",
            "url": "https://github.com/primary/repo",
            "license": "Unknown",
        }
        records = [
            {"name": "Product A", "url": "https://example.com", "status": "online"},
            {"name": "Product B", "url": "https://example.com/", "status": "online"},
        ]

        projects, sources = MODULE.merge_catalog([(source, records)])

        self.assertEqual([project["name"] for project in projects], ["Product A", "Product B"])
        self.assertEqual(sources[0]["duplicate_count"], 0)


if __name__ == "__main__":
    unittest.main()
