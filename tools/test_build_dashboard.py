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

    def test_load_dir_list_frontmatter_reported(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / "WI-001-list.md").write_text("---\n- a\n- b\n---\nx", encoding="utf-8")
            items, errors = bd.load_dir(d)
            self.assertEqual(items, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("key: value", errors[0])


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

    def test_blocked_on_unknown_wi_caught(self):
        project = {"name": "x", "started": "2026-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2026-02-01"}]}
        data = {"work": [{"path": "a.md", "body": "", "meta": {
                    "id": "WI-001", "title": "t", "owner": "o", "spec_ref": "s",
                    "updated": "2026-08-01", "status": "blocked", "blocked_on": "WI-999",
                    "priority": "mvp", "milestone": "M1", "client_visible": "false"}}],
                "decisions": [], "qa": [], "meetings": []}
        errs = bd.validate(project, data)
        self.assertTrue(any("WI-999" in e and "不存在" in e for e in errs))

    def test_project_top_level_list_reported(self):
        errs = bd.validate(["not", "a", "map"],
                           {"work": [], "decisions": [], "qa": [], "meetings": []})
        self.assertTrue(any("project.yaml" in e and "清單" in e for e in errs))

    def test_milestones_bad_shape_reported(self):
        for bad in ("M1", ["M1", "M2"], {"id": "M1"}):
            project = {"name": "x", "started": "2026-01-01", "milestones": bad}
            errs = bd.validate(project, {"work": [], "decisions": [], "qa": [], "meetings": []})
            self.assertTrue(any("milestone" in e for e in errs), repr(bad))

    def test_empty_milestones_reported(self):
        project = {"name": "x", "started": "2026-01-01", "milestones": []}
        errs = bd.validate(project, {"work": [], "decisions": [], "qa": [], "meetings": []})
        self.assertTrue(any("至少" in e for e in errs))

    def test_work_list_value_reported(self):
        project = {"name": "x", "started": "2026-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2026-02-01"}]}
        meta = {"id": "WI-001", "title": ["a", "b"], "owner": "o", "spec_ref": "s",
                "updated": "2026-08-01", "status": "todo", "priority": "mvp",
                "milestone": "M1", "client_visible": "true"}
        errs = bd.validate(project, {"work": [{"path": "a.md", "meta": meta, "body": ""}],
                                     "decisions": [], "qa": [], "meetings": []})
        self.assertTrue(any("須為單一值" in e for e in errs))

    def test_blocked_on_self_reported(self):
        project = {"name": "x", "started": "2026-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2026-02-01"}]}
        meta = {"id": "WI-001", "title": "t", "owner": "o", "spec_ref": "s",
                "updated": "2026-08-01", "status": "blocked", "blocked_on": "WI-001",
                "priority": "mvp", "milestone": "M1", "client_visible": "false"}
        errs = bd.validate(project, {"work": [{"path": "a.md", "meta": meta, "body": ""}],
                                     "decisions": [], "qa": [], "meetings": []})
        self.assertTrue(any("自身" in e for e in errs))

    def test_work_due_optional_but_validated(self):
        project = {"name": "x", "started": "2026-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2026-02-01"}]}
        base = {"id": "WI-001", "title": "t", "owner": "o", "spec_ref": "s",
                "updated": "2026-08-01", "status": "todo", "priority": "mvp",
                "milestone": "M1", "client_visible": "true"}

        def data(meta):
            return {"work": [{"path": "a.md", "meta": meta, "body": ""}],
                    "decisions": [], "qa": [], "meetings": []}

        self.assertEqual(bd.validate(project, data(dict(base))), [])  # 無 due 合法
        self.assertEqual(bd.validate(project, data(dict(base, due="2026-09-05"))), [])
        errs = bd.validate(project, data(dict(base, due="9/5")))
        self.assertTrue(any("due" in e and "日期格式" in e for e in errs))

    def test_work_side_optional_but_validated(self):
        project = {"name": "x", "started": "2026-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2026-02-01"}]}
        base = {"id": "WI-001", "title": "t", "owner": "o", "spec_ref": "s",
                "updated": "2026-08-01", "status": "todo", "priority": "mvp",
                "milestone": "M1", "client_visible": "true"}

        def data(meta):
            return {"work": [{"path": "a.md", "meta": meta, "body": ""}],
                    "decisions": [], "qa": [], "meetings": []}

        self.assertEqual(bd.validate(project, data(dict(base))), [])  # 無 side 合法
        for ok in ("vendor", "client", "both"):
            self.assertEqual(bd.validate(project, data(dict(base, side=ok))), [])
        errs = bd.validate(project, data(dict(base, side="樂禾")))
        self.assertTrue(any("side 值非法" in e for e in errs))


class TestRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project, data, errors = bd.load_all(os.path.join(FIXTURES, "sample"))
        assert not errors
        cls.html = bd.render_html(project, data["work"])

    def test_five_sections_present(self):
        for marker in ("整體進度", "里程碑", "待客戶事項", "進行中", "最近完成", "全部工項"):
            self.assertIn(marker, self.html)

    def test_visible_content(self):
        self.assertIn("首頁版面", self.html)
        self.assertIn("待客戶提供色票對照表 Excel", self.html)
        self.assertIn("範例電商網站 建置進度", self.html)
        self.assertIn("2026-08-18", self.html)

    def test_whitelist_blocks_internal_fields(self):
        self.assertNotIn("內部人員甲", self.html)
        self.assertNotIn("內部人員乙", self.html)
        self.assertNotIn("42d", self.html)
        self.assertNotIn("內部 CI 修復", self.html)
        self.assertNotIn("隱藏完成項目", self.html)
        self.assertNotIn("這是內部秘密", self.html)
        self.assertNotIn("規格書 §", self.html)

    def test_progress_counts_visible_mvp_only(self):
        self.assertIn("1 / 3", self.html)

    def test_html_escaped(self):
        project = {"name": "x", "client": "c", "started": "2026-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2026-02-01"}],
                   "dashboard": {"title": "<script>alert(1)</script>"}}
        out = bd.render_html(project, [])
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_render_empty_lists_have_placeholder(self):
        project = {"name": "x", "started": "2026-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2026-02-01"}],
                   "dashboard": {"title": "t"}}
        out = bd.render_html(project, [])
        self.assertIn("目前沒有進行中的項目", out)
        self.assertIn("尚無完成項目", out)

    @staticmethod
    def _wi(i, **kw):
        meta = {"id": "WI-00%d" % i, "title": "工項%d" % i, "owner": "o", "spec_ref": "s",
                "updated": "2026-08-01", "status": "todo", "priority": "mvp",
                "milestone": "M1", "client_visible": "true"}
        meta.update(kw)
        return {"path": "a.md", "meta": meta, "body": ""}

    def test_work_due_rendered_and_overdue_flagged(self):
        project = {"name": "x", "started": "2026-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2026-02-01"}],
                   "dashboard": {"title": "t"}}
        works = [self._wi(1, due="2999-12-31"),                 # 未到期
                 self._wi(2, due="2000-01-01"),                 # 逾期未完成 → overdue
                 self._wi(3, due="2000-01-02", status="done"),  # 逾期但已完成 → 不標
                 self._wi(4)]                                   # 無 due → —
        out = bd.render_html(project, works)
        self.assertIn("<th>截止</th>", out)
        self.assertIn("2999-12-31", out)
        self.assertIn('class="due overdue">2000-01-01', out)
        self.assertIn('class="due">2000-01-02', out)
        # 逾期標記出現在全部工項表與近期截止區各一次，且不含已完成項
        self.assertEqual(out.count('class="due overdue"'), 2)
        self.assertIn("—", out)

    def test_waiting_item_shows_due(self):
        project = {"name": "x", "started": "2026-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2026-02-01"}],
                   "dashboard": {"title": "t"}}
        works = [self._wi(1, status="blocked", blocked_on="client",
                          blocked_note="待提供資料", due="2026-09-05")]
        out = bd.render_html(project, works)
        self.assertIn("截止 2026-09-05", out)

    def test_side_column_uses_labels_not_owner(self):
        project = {"name": "x", "started": "2026-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2026-02-01"}],
                   "dashboard": {"title": "t", "side_labels": {"vendor": "樂禾", "client": "客戶"}}}
        works = [self._wi(1, side="vendor", owner="內部人員甲"),
                 self._wi(2, side="client"),
                 self._wi(3, side="both"),
                 self._wi(4)]  # 無 side → —
        out = bd.render_html(project, works)
        self.assertIn("<th>負責方</th>", out)
        self.assertIn("樂禾", out)          # 自訂 label
        self.assertIn("客戶", out)
        self.assertIn("雙方", out)          # 未自訂者用預設
        self.assertNotIn("內部人員甲", out)  # owner 人名不得輸出
        # 全部工項都沒 side → 不出現負責方欄
        out2 = bd.render_html(project, [self._wi(1)])
        self.assertNotIn("<th>負責方</th>", out2)

    def test_timeline_dots_and_today_marker(self):
        project = {"name": "x", "started": "2000-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2999-12-31"}],
                   "dashboard": {"title": "t"}}
        works = [self._wi(1, due="2000-06-01", status="done"),
                 self._wi(2, due="2000-06-01"),               # 逾期未完成
                 self._wi(3, due="2999-06-01")]
        out = bd.render_html(project, works)
        self.assertIn('class="dot dot-done"', out)
        self.assertIn('class="dot dot-overdue"', out)
        self.assertIn('class="dot dot-todo"', out)
        self.assertIn('class="today"', out)
        self.assertIn("legend", out)
        # 起訖解析不出來 → 靜默省略 timeline，不整頁失敗
        project2 = {"name": "x", "started": "??",
                    "milestones": [{"id": "M1", "title": "m", "due": "2999-12-31"}],
                    "dashboard": {"title": "t"}}
        out2 = bd.render_html(project2, works)
        self.assertNotIn('class="tl"', out2)

    def test_upcoming_section_lists_overdue_first_excludes_done(self):
        project = {"name": "x", "started": "2000-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2999-12-31"}],
                   "dashboard": {"title": "t"}}
        works = [self._wi(1, due="2000-01-05"),                 # 逾期
                 self._wi(2, due="2000-01-02", status="done"),  # done 不列
                 self._wi(3, due="2999-06-01")]                 # 14 天外不列
        out = bd.render_html(project, works)
        self.assertIn("近期截止", out)
        section = out.split("近期截止")[1].split("</section>")[0]
        self.assertIn("逾期", section)
        self.assertNotIn("工項2", section)       # done 不列
        self.assertNotIn("工項3", section)       # 14 天外不列
        # 無符合項目 → 佔位文字
        out2 = bd.render_html(project, [self._wi(3, due="2999-06-01")])
        self.assertIn("未來兩週內沒有截止項目", out2)


class TestCli(unittest.TestCase):
    def test_check_sample_ok(self):
        self.assertEqual(bd.main(["--root", os.path.join(FIXTURES, "sample"), "--check"]), 0)

    def test_check_broken_fails(self):
        self.assertEqual(bd.main(["--root", os.path.join(FIXTURES, "broken"), "--check"]), 1)

    def test_build_writes_html(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "index.html")
            rc = bd.main(["--root", os.path.join(FIXTURES, "sample"), "--out", out])
            self.assertEqual(rc, 0)
            with open(out, encoding="utf-8") as f:
                self.assertIn("待客戶事項", f.read())

    def test_build_refuses_on_errors(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "index.html")
            rc = bd.main(["--root", os.path.join(FIXTURES, "broken"), "--out", out])
            self.assertEqual(rc, 1)
            self.assertFalse(os.path.exists(out))

    def test_root_not_exist_message(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            rc = bd.main(["--root", "/nonexistent/pm-root", "--check"])
        self.assertEqual(rc, 1)
        self.assertIn("根目錄不存在", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
