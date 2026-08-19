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

    def test_bad_indent_raises(self):
        with self.assertRaises(ValueError):
            bd.parse_yaml_subset("a: 1\n    b: 2")

    def test_flush_list_under_key(self):
        got = bd.parse_yaml_subset("milestones:\n- id: M1\n  title: X\nname: after")
        self.assertEqual(got["milestones"], [{"id": "M1", "title": "X"}])
        self.assertEqual(got["name"], "after")

    def test_scalar_list_item_with_colon(self):
        got = bd.parse_yaml_subset("refs:\n  - http://example.com/x\n  - b.md")
        self.assertEqual(got["refs"], ["http://example.com/x", "b.md"])

    def test_inline_list_with_quoted_comma_raises(self):
        with self.assertRaises(ValueError):
            bd.parse_yaml_subset("titles: ['Hello, World', foo]")

    def test_trailing_comment_stripped(self):
        got = bd.parse_yaml_subset("status: todo   # todo | doing\nrefs: [a.md]  # 註")
        self.assertEqual(got["status"], "todo")
        self.assertEqual(got["refs"], ["a.md"])

    def test_unparseable_tail_raises(self):
        with self.assertRaises(ValueError):
            bd.parse_yaml_subset("a: 1\n- stray")

    def test_unquoted_hash_value_raises(self):
        with self.assertRaises(ValueError):
            bd.parse_yaml_subset("color: #fff")

    def test_quoted_hash_value_preserved(self):
        self.assertEqual(bd.parse_yaml_subset("color: '#fff'"), {"color": "#fff"})


class TestFrontmatter(unittest.TestCase):
    def test_parse_ok(self):
        meta, body = bd.parse_frontmatter("---\nid: WI-001\ntitle: 首頁\n---\n\n## 說明\n內容")
        self.assertEqual(meta, {"id": "WI-001", "title": "首頁"})
        self.assertIn("## 說明", body)

    def test_missing_frontmatter(self):
        with self.assertRaises(ValueError):
            bd.parse_frontmatter("沒有 frontmatter")

    def test_unclosed_frontmatter(self):
        with self.assertRaises(ValueError):
            bd.parse_frontmatter("---\nid: WI-001\n")

    def test_empty_body(self):
        meta, body = bd.parse_frontmatter("---\nid: WI-001\n---")
        self.assertEqual(meta["id"], "WI-001")
        self.assertEqual(body, "")

    def test_dashes_in_body_kept(self):
        meta, body = bd.parse_frontmatter("---\nid: WI-001\n---\n前\n---\n後")
        self.assertEqual(body, "前\n---\n後")


class TestLoaders(unittest.TestCase):
    def test_load_dir_skips_underscore_and_non_md(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp) / "work"
            d.mkdir()
            (d / "WI-001-a.md").write_text("---\nid: WI-001\n---\nx", encoding="utf-8")
            (d / "_example-WI-000.md").write_text("---\nid: WI-000\n---\nx", encoding="utf-8")
            (d / "note.txt").write_text("x", encoding="utf-8")
            items, errors = bd.load_dir(d)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["meta"]["id"], "WI-001")
            self.assertEqual(errors, [])

    def test_load_dir_collects_parse_errors(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp) / "work"
            d.mkdir()
            (d / "WI-001-bad.md").write_text("沒有 frontmatter", encoding="utf-8")
            items, errors = bd.load_dir(d)
            self.assertEqual(items, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("WI-001-bad.md", errors[0])

    def test_load_dir_bom_file_ok(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / "WI-001-bom.md").write_bytes("﻿---\nid: WI-001\n---\nx".encode("utf-8"))
            items, errors = bd.load_dir(d)
            self.assertEqual(errors, [])
            self.assertEqual(items[0]["meta"]["id"], "WI-001")

    def test_load_dir_non_utf8_error_names_file(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / "WI-002-latin.md").write_bytes(b"---\nid: WI-002\xff\n---\n")
            items, errors = bd.load_dir(d)
            self.assertEqual(items, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("WI-002-latin.md", errors[0])

    def test_load_dir_unreadable_file_collected(self):
        import os, tempfile, pathlib
        if os.geteuid() == 0:
            self.skipTest("root 可讀任何檔案")
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            f = d / "WI-003-locked.md"
            f.write_text("---\nid: WI-003\n---\nx", encoding="utf-8")
            os.chmod(f, 0)
            try:
                items, errors = bd.load_dir(d)
            finally:
                os.chmod(f, 0o644)
            self.assertEqual(items, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("WI-003-locked.md", errors[0])


class TestLoadAll(unittest.TestCase):
    def test_missing_root(self):
        project, data, errors = bd.load_all("/nonexistent/pm-root")
        self.assertEqual(project, {})
        self.assertEqual(sorted(data), ["decisions", "meetings", "qa", "work"])
        self.assertTrue(any("project.yaml" in e for e in errors))

    def test_partial_dirs(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "project.yaml").write_text("name: x\n", encoding="utf-8")
            (root / "work").mkdir()
            (root / "work" / "WI-001-a.md").write_text("---\nid: WI-001\n---\nx", encoding="utf-8")
            project, data, errors = bd.load_all(root)
            self.assertEqual(errors, [])
            self.assertEqual(project["name"], "x")
            self.assertEqual(len(data["work"]), 1)
            self.assertEqual(data["qa"], [])


class TestValidate(unittest.TestCase):
    def _errors(self, name):
        project, data, errors = bd.load_all(os.path.join(FIXTURES, name))
        return errors + bd.validate(project, data)

    def test_sample_is_clean(self):
        self.assertEqual(self._errors("sample"), [])

    def test_broken_reports_each_violation(self):
        errs = "\n".join(self._errors("broken"))
        self.assertIn("name", errs)                 # project.name 空白
        self.assertIn("started", errs)              # 日期格式錯
        self.assertIn("status 值非法", errs)         # flying
        self.assertIn("blocked_on", errs)           # blocked 缺 blocked_on
        self.assertIn("blocked_note", errs)         # client 卡關缺 note
        self.assertIn("id 重複", errs)               # WI-001 x2
        self.assertIn("milestone", errs)            # M9 不存在
        self.assertIn("priority", errs)             # urgent
        self.assertIn("client_visible", errs)       # maybe
        self.assertIn("updated", errs)              # 2026/08/10

    def test_invalid_calendar_date_caught(self):
        errors = []
        bd._date({"d": "2026-13-99"}, "d", "x.md", errors)
        self.assertEqual(len(errors), 1)
        self.assertIn("不是有效日期", errors[0])


if __name__ == "__main__":
    unittest.main()
