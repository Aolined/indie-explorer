import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "parse_readme.py"
SPEC = importlib.util.spec_from_file_location("parse_readme", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ParseReadmeTests(unittest.TestCase):
    def test_parses_author_and_product_metadata(self):
        text = """#### 张三(上海) - [Github](https://github.com/zhangsan), [博客](https://example.com/blog)
* :white_check_mark: [工具箱](https://example.com)：本地处理文件 - [更多介绍](https://example.com/about)
"""

        projects = MODULE.parse_readme(text)

        self.assertEqual(len(projects), 1)
        self.assertEqual(
            projects[0],
            {
                "author": "张三",
                "city": "上海",
                "github": "https://github.com/zhangsan",
                "blog": "https://example.com/blog",
                "website": None,
                "name": "工具箱",
                "url": "https://example.com",
                "description": "本地处理文件",
                "status": "online",
                "more_info": "https://example.com/about",
            },
        )

    def test_multiple_products_share_the_same_author(self):
        text = """#### Solo - [Github](https://github.com/solo)
* :clock8: [Alpha](https://alpha.example)：开发中
* :x: [Beta](https://beta.example)：已关闭
"""

        projects = MODULE.parse_readme(text)

        self.assertEqual([project["author"] for project in projects], ["Solo", "Solo"])
        self.assertEqual([project["status"] for project in projects], ["developing", "closed"])

    def test_ignores_headings_and_malformed_product_lines(self):
        text = """### 2026 年添加
#### 没有产品
这不是产品行
* [缺少状态](https://example.com)：应该跳过
"""

        self.assertEqual(MODULE.parse_readme(text), [])

    def test_accepts_legacy_url_and_description_formats(self):
        text = """#### Legacy
* :white_check_mark: [No Protocol](example.com)：可以访问
* :white_check_mark: [Short Description](https://example.org) - 用短横线分隔
"""

        projects = MODULE.parse_readme(text)

        self.assertEqual(projects[0]["url"], "https://example.com")
        self.assertEqual(projects[0]["description"], "可以访问")
        self.assertEqual(projects[1]["description"], "用短横线分隔")

    def test_handles_fullwidth_city_parentheses_and_link_only_headers(self):
        text = """#### Windyan(深圳）- [Github](https://github.com/windyan233)
* :white_check_mark: [项目](https://example.com)：测试
#### [Github](https://github.com/example)
* :white_check_mark: [另一个项目](https://example.org)：测试
"""

        projects = MODULE.parse_readme(text)

        self.assertEqual(projects[0]["author"], "Windyan")
        self.assertEqual(projects[0]["city"], "深圳")
        self.assertEqual(projects[1]["author"], "example")
        self.assertIsNone(projects[1]["city"])

    def test_rejects_domain_names_as_cities(self):
        text = """#### Example(github.com/example/project)
* :white_check_mark: [项目](https://example.com)：测试
"""

        project = MODULE.parse_readme(text)[0]

        self.assertEqual(project["author"], "Example")
        self.assertIsNone(project["city"])


if __name__ == "__main__":
    unittest.main()
