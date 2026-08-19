#!/usr/bin/env python3
"""build_dashboard.py 測試。執行：python3 tools/test_build_dashboard.py -v"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_dashboard as bd

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class TestYamlSubset(unittest.TestCase):
    def test_scalars_and_quotes(self):
        self.assertEqual(bd.parse_yaml_subset("a: 1\nb: 你好\nc: 'x y'"),
                         {"a": "1", "b": "你好", "c": "x y"})

    def test_inline_list(self):
        self.assertEqual(bd.parse_yaml_subset("refs: [a.md, b.md]\nempty: []"),
                         {"refs": ["a.md", "b.md"], "empty": []})

    def test_empty_value_and_comment(self):
        self.assertEqual(bd.parse_yaml_subset("# 註解\nurl: \nname: x"),
                         {"url": "", "name": "x"})

    def test_nested_map_and_list_of_dicts(self):
        text = (
            "name: 專案\n"
            "milestones:\n"
            "  - id: M1\n"
            "    title: 首頁\n"
            "    due: 2026-09-01\n"
            "  - id: M2\n"
            "    title: 結帳\n"
            "    due: 2026-10-01\n"
            "dashboard:\n"
            "  title: 進度\n"
        )
        got = bd.parse_yaml_subset(text)
        self.assertEqual(got["name"], "專案")
        self.assertEqual(got["milestones"][1], {"id": "M2", "title": "結帳", "due": "2026-10-01"})
        self.assertEqual(got["dashboard"], {"title": "進度"})

    def test_empty_text(self):
        self.assertEqual(bd.parse_yaml_subset(""), {})


if __name__ == "__main__":
    unittest.main()
