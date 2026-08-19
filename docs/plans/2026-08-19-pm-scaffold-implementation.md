# pm-scaffold 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建出可 clone 重用的專案管理 scaffold repo：Markdown 資料層、零依賴儀表板產生器、六個工具中立 playbook。

**Architecture:** 一事一檔 Markdown + YAML frontmatter 為真相來源；`tools/build_dashboard.py`（Python 3 標準庫）負責 schema 驗證與白名單輸出 `docs/index.html`；`AGENTS.md` 為 AI 行為正本，`skills/*/SKILL.md` 為人機共讀 SOP。規格見 `docs/specs/2026-08-19-pm-scaffold-design.md`（下稱 spec）。

**Tech Stack:** Python 3 標準庫（unittest、argparse、html、re、pathlib）、Markdown、agentskills.io SKILL.md 格式。無任何第三方依賴。

**工作目錄：** 全部命令在 `/Users/largitdata/project/pm-scaffold/` 下執行。

---

## 檔案地圖

| 檔案 | 職責 |
|---|---|
| `tools/build_dashboard.py` | 迷你 YAML 子集解析、frontmatter 解析、載入器、驗證器、HTML 渲染、CLI（單檔，spec §六） |
| `tools/test_build_dashboard.py` | 上述全部的 unittest |
| `tools/fixtures/sample/` | 完整合法範例專案（測試 + 驗收用） |
| `tools/fixtures/broken/` | 故意違規的專案（驗證器測試用） |
| `project.yaml`、`work/` 等 | scaffold 資料模板與 `_example` 範例檔 |
| `AGENTS.md`、`CLAUDE.md` | AI 行為正本 + Claude Code stub |
| `skills/<name>/SKILL.md` × 6 | playbooks |
| `.claude/skills/<name>` | symlink → `../../skills/<name>` |
| `README.md` | 人的入口：啟用步驟、三角色速查、工具接線 |

---

### Task 1: 目錄骨架與 .gitignore

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: 建目錄與 .gitignore**

```bash
cd /Users/largitdata/project/pm-scaffold
mkdir -p work decisions qa meetings source docs tools/fixtures skills .claude/skills
cat > .gitignore <<'EOF'
.DS_Store
__pycache__/
*.pyc
EOF
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore && git commit -m "chore: repo 骨架"
```

（空目錄不進 git 沒關係，後續 task 會放檔案。）

---

### Task 2: YAML 子集解析器

**Files:**
- Create: `tools/build_dashboard.py`
- Create: `tools/test_build_dashboard.py`

- [ ] **Step 1: 寫失敗測試**

`tools/test_build_dashboard.py`：

```python
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
```

- [ ] **Step 2: 執行確認失敗**

Run: `python3 tools/test_build_dashboard.py -v`
Expected: FAIL —— `ModuleNotFoundError: No module named 'build_dashboard'`

- [ ] **Step 3: 實作解析器**

`tools/build_dashboard.py`：

```python
#!/usr/bin/env python3
"""pm-scaffold 儀表板產生器與 schema 驗證器。

零第三方依賴。用法：
  python3 tools/build_dashboard.py --check          # 只驗證資料
  python3 tools/build_dashboard.py                  # 驗證 + 產出 docs/index.html
  python3 tools/build_dashboard.py --root <path>    # 指定專案根目錄（預設：本檔上兩層）

支援的 YAML 子集（spec §六）：純量、引號字串、行內清單 [a, b]、
縮排巢狀 mapping、list-of-dicts（dict 欄位限純量）。不支援任意 YAML。
"""
import argparse
import html
import re
import sys
from pathlib import Path

# ---------- YAML 子集解析 ----------

def parse_scalar(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        return s[1:-1]
    return s


def _lines(text):
    out = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        out.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    return out


def parse_yaml_subset(text):
    lines = _lines(text)
    if not lines:
        return {}
    obj, _ = _parse_block(lines, 0, lines[0][0])
    return obj


def _parse_block(lines, i, indent):
    if lines[i][1].startswith("- "):
        return _parse_list(lines, i, indent)
    return _parse_map(lines, i, indent)


def _parse_map(lines, i, indent):
    result = {}
    while i < len(lines):
        ind, line = lines[i]
        if ind < indent or line.startswith("- "):
            break
        if ind > indent:
            raise ValueError("非預期縮排：%r" % line)
        key, _, rest = line.partition(":")
        key, rest = key.strip(), rest.strip()
        if rest == "":
            if i + 1 < len(lines) and lines[i + 1][0] > ind:
                result[key], i = _parse_block(lines, i + 1, lines[i + 1][0])
            else:
                result[key] = ""
                i += 1
        elif rest.startswith("[") and rest.endswith("]"):
            inner = rest[1:-1]
            result[key] = [parse_scalar(x) for x in inner.split(",") if x.strip()]
            i += 1
        else:
            result[key] = parse_scalar(rest)
            i += 1
    return result, i


def _parse_list(lines, i, indent):
    result = []
    while i < len(lines):
        ind, line = lines[i]
        if ind != indent or not line.startswith("- "):
            break
        content = line[2:].strip()
        if ":" in content:
            key, _, rest = content.partition(":")
            item = {key.strip(): parse_scalar(rest)}
            i += 1
            while i < len(lines) and lines[i][0] == indent + 2 and not lines[i][1].startswith("- "):
                k, _, r = lines[i][1].partition(":")
                item[k.strip()] = parse_scalar(r)
                i += 1
            result.append(item)
        else:
            result.append(parse_scalar(content))
            i += 1
    return result, i
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 tools/test_build_dashboard.py -v`
Expected: `TestYamlSubset` 5 項 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/ && git commit -m "feat: YAML 子集解析器（TDD）"
```

---

### Task 3: Frontmatter 解析與載入器

**Files:**
- Modify: `tools/build_dashboard.py`（追加）
- Modify: `tools/test_build_dashboard.py`（追加）

- [ ] **Step 1: 寫失敗測試（追加到 test 檔）**

```python
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
```

- [ ] **Step 2: 執行確認失敗**

Run: `python3 tools/test_build_dashboard.py -v`
Expected: FAIL —— `AttributeError: ... 'parse_frontmatter'`

- [ ] **Step 3: 實作（追加到 build_dashboard.py）**

```python
# ---------- Frontmatter 與載入 ----------

def parse_frontmatter(text, path=""):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("%s: 缺少 frontmatter（首行須為 ---）" % path)
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        raise ValueError("%s: frontmatter 未以 --- 結束" % path)
    meta = parse_yaml_subset("\n".join(lines[1:end]))
    return meta, "\n".join(lines[end + 1:])


def load_dir(dirpath):
    """回傳 (items, errors)。item = {path, meta, body}。跳過 _ 開頭與非 .md。"""
    items, errors = [], []
    dirpath = Path(dirpath)
    if not dirpath.is_dir():
        return items, errors
    for f in sorted(dirpath.glob("*.md")):
        if f.name.startswith("_"):
            continue
        try:
            meta, body = parse_frontmatter(f.read_text(encoding="utf-8"), str(f))
            items.append({"path": str(f), "meta": meta, "body": body})
        except ValueError as e:
            errors.append(str(e))
    return items, errors


def load_all(root):
    """回傳 (project, data, errors)。data = {work, decisions, qa, meetings}。"""
    root = Path(root)
    errors = []
    project = {}
    pf = root / "project.yaml"
    if pf.is_file():
        try:
            project = parse_yaml_subset(pf.read_text(encoding="utf-8"))
        except ValueError as e:
            errors.append("project.yaml: %s" % e)
    else:
        errors.append("project.yaml: 檔案不存在")
    data = {}
    for name in ("work", "decisions", "qa", "meetings"):
        items, errs = load_dir(root / name)
        data[name] = items
        errors.extend(errs)
    return project, data, errors
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 tools/test_build_dashboard.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/ && git commit -m "feat: frontmatter 解析與資料載入器（TDD）"
```

---

### Task 4: 測試 fixtures（sample 合法專案 + broken 違規專案）

**Files:**
- Create: `tools/fixtures/sample/project.yaml`、`tools/fixtures/sample/{work,decisions,qa,meetings}/*.md`
- Create: `tools/fixtures/broken/project.yaml`、`tools/fixtures/broken/work/*.md`

- [ ] **Step 1: 建 sample fixture**

```bash
mkdir -p tools/fixtures/sample/{work,decisions,qa,meetings} tools/fixtures/broken/work
```

`tools/fixtures/sample/project.yaml`：

```yaml
name: 範例電商網站
client: 範例客戶股份有限公司
started: 2026-08-01
milestones:
  - id: M1
    title: 前台頁面
    due: 2026-09-15
  - id: M2
    title: 金流與結帳
    due: 2026-10-15
people:
  - name: 內部人員甲
    role: engineer
  - name: 內部人員乙
    role: pm
engineering_repos:
  - path: /path/to/theme-repo
    last_synced: ""
dashboard:
  title: 範例電商網站 建置進度
  url: ""
```

`tools/fixtures/sample/work/WI-001-homepage.md`：

```markdown
---
id: WI-001
title: 首頁版面
status: done
owner: 內部人員甲
priority: mvp
milestone: M1
spec_ref: 規格書 §2
client_visible: true
estimate: 42d
updated: 2026-08-10
---

## 說明
首頁 hero 與分類磚。

## 進度日誌
- 2026-08-10 內部人員甲：完成
```

`tools/fixtures/sample/work/WI-002-plp.md`：

```markdown
---
id: WI-002
title: 商品列表與篩選
status: doing
owner: 內部人員甲
priority: mvp
milestone: M1
spec_ref: 規格書 §3
client_visible: true
estimate: 5d
updated: 2026-08-18
---

## 說明
PLP 清單與篩選抽屜。

## 進度日誌
- 2026-08-18 內部人員甲：篩選抽屜完成一半
```

`tools/fixtures/sample/work/WI-003-swatch.md`：

```markdown
---
id: WI-003
title: 色票對照表匯入
status: blocked
owner: 內部人員甲
blocked_on: client
blocked_note: 待客戶提供色票對照表 Excel
priority: mvp
milestone: M2
spec_ref: 規格書 §4.1
client_visible: true
estimate: 2d
updated: 2026-08-15
---

## 說明
匯入客戶提供的色票對照。

## 進度日誌
- 2026-08-15 內部人員甲：已向客戶催件 → blocked
```

`tools/fixtures/sample/work/WI-004-internal-ci.md`：

```markdown
---
id: WI-004
title: 內部 CI 修復
status: blocked
owner: 內部人員甲
blocked_on: internal
blocked_note: 等內部主機擴容這是內部秘密
priority: nice
milestone: M2
spec_ref: 口頭需求
client_visible: false
estimate: 1d
updated: 2026-08-14
---

## 說明
內部事項，不上儀表板。
```

`tools/fixtures/sample/work/WI-005-hidden-done.md`：

```markdown
---
id: WI-005
title: 隱藏完成項目
status: done
owner: 內部人員乙
priority: recommended
milestone: M2
spec_ref: 口頭需求
client_visible: false
estimate: 1d
updated: 2026-08-12
---

## 說明
client_visible: false 的 done 項目，白名單測試用。
```

`tools/fixtures/sample/decisions/D-001-platform.md`：

```markdown
---
id: D-001
date: 2026-08-05
decided_by: 範例客戶窗口
status: decided
refs: [source/spec.xlsx]
---

## 背景
平台選擇。

## 決定
採 WordPress。

## 重新討論的條件
流量超過預估十倍時。
```

`tools/fixtures/sample/qa/QA-001-refund.md`：

```markdown
---
id: QA-001
date: 2026-08-08
asked_by: 範例客戶窗口
channel: email
status: answered
refs: [decisions/D-001-platform.md]
---

## 客戶問什麼
退貨流程是否包含在合約內？

## 我們答什麼
包含，見規格書 §9。

## 依據
source/spec.xlsx §9
```

`tools/fixtures/sample/meetings/2026-08-18-standup.md`：

```markdown
---
date: 2026-08-18
type: standup
attendees: [內部人員甲, 內部人員乙]
---

## 摘要
彙報 PLP 進度。

## 工項異動
- WI-002 → doing（日誌更新）
```

- [ ] **Step 2: 建 broken fixture**

`tools/fixtures/broken/project.yaml`：

```yaml
name: ""
client: 壞掉專案
started: 2026-13-99
milestones:
  - id: M1
    title: 有效里程碑
    due: 2026-09-15
```

`tools/fixtures/broken/work/WI-001-bad-status.md`：

```markdown
---
id: WI-001
title: 非法狀態
status: flying
owner: 某人
priority: mvp
milestone: M1
spec_ref: x
client_visible: true
estimate: 1d
updated: 2026-08-10
---
x
```

`tools/fixtures/broken/work/WI-002-blocked-no-on.md`：

```markdown
---
id: WI-002
title: blocked 缺 blocked_on
status: blocked
owner: 某人
priority: mvp
milestone: M1
spec_ref: x
client_visible: true
estimate: 1d
updated: 2026-08-10
---
x
```

`tools/fixtures/broken/work/WI-003-dup-and-refs.md`：

```markdown
---
id: WI-001
title: id 重複、milestone 不存在、client 卡關缺 note
status: blocked
owner: 某人
blocked_on: client
priority: urgent
milestone: M9
spec_ref: x
client_visible: maybe
estimate: 1d
updated: 2026/08/10
---
x
```

- [ ] **Step 3: 驗證 fixtures 可被載入**

Run: `python3 -c "import sys; sys.path.insert(0,'tools'); import build_dashboard as bd; p,d,e = bd.load_all('tools/fixtures/sample'); print(len(d['work']), e)"`
Expected: `5 []`

- [ ] **Step 4: Commit**

```bash
git add tools/fixtures && git commit -m "test: sample 與 broken fixtures"
```

---

### Task 5: 驗證器

**Files:**
- Modify: `tools/build_dashboard.py`（追加）
- Modify: `tools/test_build_dashboard.py`（追加）

- [ ] **Step 1: 寫失敗測試（追加）**

```python
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
```

- [ ] **Step 2: 執行確認失敗**

Run: `python3 tools/test_build_dashboard.py -v`
Expected: FAIL —— `AttributeError: ... 'validate'`

- [ ] **Step 3: 實作驗證器（追加）**

```python
# ---------- 驗證 ----------

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WORK_STATUS = {"todo", "doing", "blocked", "review", "done", "dropped"}
PRIORITY = {"mvp", "recommended", "nice"}
BLOCKED_ON_RE = re.compile(r"^(client|internal|vendor|WI-\d+)$")
DECISION_STATUS = {"decided", "superseded"}
QA_STATUS = {"answered", "pending"}
QA_CHANNEL = {"email", "meeting", "line", "other"}
MEETING_TYPE = {"standup", "client", "internal"}


def _req(meta, field, path, errors):
    val = str(meta.get(field, "") or "").strip()
    if not val:
        errors.append("%s: 缺少必填欄位 %s" % (path, field))
    return val


def _date(meta, field, path, errors, required=True):
    val = str(meta.get(field, "") or "").strip()
    if not val:
        if required:
            errors.append("%s: 缺少必填欄位 %s" % (path, field))
        return
    if not DATE_RE.match(val):
        errors.append("%s: %s 日期格式須為 YYYY-MM-DD（得到 %r）" % (path, field, val))
        return
    try:
        datetime.date.fromisoformat(val)
    except ValueError:
        errors.append("%s: %s 不是有效日期（得到 %r）" % (path, field, val))


def validate(project, data):
    errors = []

    # project.yaml
    if not str(project.get("name", "") or "").strip():
        errors.append("project.yaml: 缺少必填欄位 name")
    _date(project, "started", "project.yaml", errors)
    milestones = project.get("milestones") or []
    mids = set()
    for m in milestones:
        mid = str(m.get("id", "") or "").strip()
        if not mid:
            errors.append("project.yaml: milestone 缺少 id")
            continue
        if mid in mids:
            errors.append("project.yaml: milestone id 重複：%s" % mid)
        mids.add(mid)
        if not str(m.get("title", "") or "").strip():
            errors.append("project.yaml: milestone %s 缺少 title" % mid)
        _date(m, "due", "project.yaml milestone %s" % mid, errors)

    # work/
    seen_wi = set()
    for item in data["work"]:
        meta, path = item["meta"], item["path"]
        wid = _req(meta, "id", path, errors)
        if wid:
            if not re.match(r"^WI-\d+$", wid):
                errors.append("%s: id 格式須為 WI-###（得到 %r）" % (path, wid))
            if wid in seen_wi:
                errors.append("%s: id 重複：%s" % (path, wid))
            seen_wi.add(wid)
        _req(meta, "title", path, errors)
        _req(meta, "owner", path, errors)
        _req(meta, "spec_ref", path, errors)
        _date(meta, "updated", path, errors)
        status = _req(meta, "status", path, errors)
        if status and status not in WORK_STATUS:
            errors.append("%s: status 值非法：%r（允許：%s）" % (path, status, "|".join(sorted(WORK_STATUS))))
        pri = _req(meta, "priority", path, errors)
        if pri and pri not in PRIORITY:
            errors.append("%s: priority 值非法：%r" % (path, pri))
        ms = _req(meta, "milestone", path, errors)
        if ms and mids and ms not in mids:
            errors.append("%s: milestone %r 不存在於 project.yaml" % (path, ms))
        cv = str(meta.get("client_visible", "") or "").strip()
        if cv not in {"true", "false"}:
            errors.append("%s: client_visible 須為 true|false（得到 %r）" % (path, cv))
        if status == "blocked":
            bon = str(meta.get("blocked_on", "") or "").strip()
            if not bon:
                errors.append("%s: status=blocked 時 blocked_on 為必填" % path)
            elif not BLOCKED_ON_RE.match(bon):
                errors.append("%s: blocked_on 值非法：%r" % (path, bon))
            if bon == "client" and not str(meta.get("blocked_note", "") or "").strip():
                errors.append("%s: blocked_on=client 時 blocked_note 為必填（會上儀表板）" % path)

    # decisions/
    for item in data["decisions"]:
        meta, path = item["meta"], item["path"]
        did = _req(meta, "id", path, errors)
        if did and not re.match(r"^D-\d+$", did):
            errors.append("%s: id 格式須為 D-###" % path)
        _date(meta, "date", path, errors)
        _req(meta, "decided_by", path, errors)
        st = _req(meta, "status", path, errors)
        if st and st not in DECISION_STATUS:
            errors.append("%s: status 值非法：%r" % (path, st))

    # qa/
    for item in data["qa"]:
        meta, path = item["meta"], item["path"]
        qid = _req(meta, "id", path, errors)
        if qid and not re.match(r"^QA-\d+$", qid):
            errors.append("%s: id 格式須為 QA-###" % path)
        _date(meta, "date", path, errors)
        _req(meta, "asked_by", path, errors)
        ch = _req(meta, "channel", path, errors)
        if ch and ch not in QA_CHANNEL:
            errors.append("%s: channel 值非法：%r" % (path, ch))
        st = _req(meta, "status", path, errors)
        if st and st not in QA_STATUS:
            errors.append("%s: status 值非法：%r" % (path, st))

    # meetings/
    for item in data["meetings"]:
        meta, path = item["meta"], item["path"]
        _date(meta, "date", path, errors)
        ty = _req(meta, "type", path, errors)
        if ty and ty not in MEETING_TYPE:
            errors.append("%s: type 值非法：%r" % (path, ty))

    return errors
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 tools/test_build_dashboard.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/ && git commit -m "feat: schema 驗證器（TDD）"
```

---

### Task 6: HTML 渲染器（白名單輸出）

**Files:**
- Modify: `tools/build_dashboard.py`（追加）
- Modify: `tools/test_build_dashboard.py`（追加）

- [ ] **Step 1: 寫失敗測試（追加）**

```python
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
        self.assertIn("首頁版面", self.html)                       # visible done
        self.assertIn("待客戶提供色票對照表 Excel", self.html)      # client blocked_note
        self.assertIn("範例電商網站 建置進度", self.html)           # dashboard.title
        self.assertIn("2026-08-18", self.html)                     # 最後更新 = max(updated of visible)

    def test_whitelist_blocks_internal_fields(self):
        self.assertNotIn("內部人員甲", self.html)                   # owner
        self.assertNotIn("內部人員乙", self.html)
        self.assertNotIn("42d", self.html)                          # estimate
        self.assertNotIn("內部 CI 修復", self.html)                 # client_visible: false
        self.assertNotIn("隱藏完成項目", self.html)                 # client_visible: false
        self.assertNotIn("這是內部秘密", self.html)                 # internal blocked_note
        self.assertNotIn("規格書 §", self.html)                     # spec_ref

    def test_progress_counts_visible_mvp_only(self):
        # visible MVP：WI-001 done、WI-002 doing、WI-003 blocked → 1/3
        self.assertIn("1 / 3", self.html)

    def test_html_escaped(self):
        project = {"name": "x", "client": "c", "started": "2026-01-01",
                   "milestones": [{"id": "M1", "title": "m", "due": "2026-02-01"}],
                   "dashboard": {"title": "<script>alert(1)</script>"}}
        out = bd.render_html(project, [])
        self.assertNotIn("<script>alert(1)</script>", out)
        self.assertIn("&lt;script&gt;", out)
```

- [ ] **Step 2: 執行確認失敗**

Run: `python3 tools/test_build_dashboard.py -v`
Expected: FAIL —— `AttributeError: ... 'render_html'`

- [ ] **Step 3: 實作渲染器（追加）**

白名單原則：本函式**只讀取** title / status / milestone / blocked_note（僅 `blocked_on==client`）/ updated / priority（只用於計數，不輸出文字）。owner、estimate、spec_ref、內部 note 連變數都不取。

```python
# ---------- 渲染（白名單輸出） ----------

STATUS_LABEL = {"todo": "待辦", "doing": "進行中", "blocked": "卡關",
                "review": "驗收中", "done": "完成"}


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _visible(works):
    """儀表板收錄範圍：client_visible=true 且非 dropped。"""
    return [w for w in works
            if str(w["meta"].get("client_visible", "")).strip() == "true"
            and w["meta"].get("status") != "dropped"]


def _bar(done, total):
    pct = int(round(done * 100.0 / total)) if total else 0
    return ('<div class="bar"><div class="fill" style="width:%d%%"></div></div>'
            '<span class="pct">%d / %d</span>' % (pct, done, total))


def render_html(project, works):
    vis = _visible(works)
    dash = project.get("dashboard") or {}
    title = str(dash.get("title") or "").strip() or "%s 專案進度" % project.get("name", "")
    updated = max((w["meta"].get("updated", "") for w in vis), default="—")

    mvp = [w for w in vis if w["meta"].get("priority") == "mvp"]
    mvp_done = [w for w in mvp if w["meta"].get("status") == "done"]

    parts = []
    parts.append("<header><h1>%s</h1>" % _esc(title))
    parts.append('<p class="meta">最後更新：%s</p>' % _esc(updated))
    parts.append('<section class="overall"><h2>整體進度（MVP）</h2>%s</section></header>'
                 % _bar(len(mvp_done), len(mvp)))

    # 里程碑
    parts.append("<section><h2>里程碑</h2>")
    for m in project.get("milestones") or []:
        mid = m.get("id", "")
        mitems = [w for w in vis if w["meta"].get("milestone") == mid]
        mdone = [w for w in mitems if w["meta"].get("status") == "done"]
        parts.append('<div class="ms"><h3>%s %s <span class="due">目標 %s</span></h3>%s</div>'
                     % (_esc(mid), _esc(m.get("title", "")), _esc(m.get("due", "")),
                        _bar(len(mdone), len(mitems))))
    parts.append("</section>")

    # 待客戶事項
    waiting = [w for w in vis if w["meta"].get("status") == "blocked"
               and w["meta"].get("blocked_on") == "client"]
    parts.append('<section class="waiting"><h2>⏳ 待客戶事項</h2>')
    if waiting:
        parts.append("<ul>")
        for w in waiting:
            parts.append("<li><strong>%s</strong>：%s</li>"
                         % (_esc(w["meta"].get("title", "")), _esc(w["meta"].get("blocked_note", ""))))
        parts.append("</ul>")
    else:
        parts.append('<p class="empty">目前沒有待客戶提供的事項。</p>')
    parts.append("</section>")

    # 進行中 / 最近完成
    doing = [w for w in vis if w["meta"].get("status") in ("doing", "review")]
    recent = sorted((w for w in vis if w["meta"].get("status") == "done"),
                    key=lambda w: w["meta"].get("updated", ""), reverse=True)[:10]
    parts.append('<section class="cols"><div><h2>進行中</h2><ul>')
    parts.extend("<li>%s <span class=\"tag\">%s</span></li>"
                 % (_esc(w["meta"].get("title", "")), STATUS_LABEL.get(w["meta"].get("status"), ""))
                 for w in doing)
    parts.append("</ul></div><div><h2>最近完成</h2><ul>")
    parts.extend("<li>%s <span class=\"date\">%s</span></li>"
                 % (_esc(w["meta"].get("title", "")), _esc(w["meta"].get("updated", "")))
                 for w in recent)
    parts.append("</ul></div></section>")

    # 全部工項（按里程碑分組）
    parts.append("<section><h2>全部工項</h2>")
    for m in project.get("milestones") or []:
        mid = m.get("id", "")
        mitems = [w for w in vis if w["meta"].get("milestone") == mid]
        if not mitems:
            continue
        parts.append("<details open><summary>%s %s（%d 項）</summary><table>"
                     "<tr><th>項目</th><th>狀態</th></tr>" % (_esc(mid), _esc(m.get("title", "")), len(mitems)))
        for w in mitems:
            st = w["meta"].get("status", "")
            parts.append('<tr><td>%s</td><td><span class="st st-%s">%s</span></td></tr>'
                         % (_esc(w["meta"].get("title", "")), _esc(st), STATUS_LABEL.get(st, _esc(st))))
        parts.append("</table></details>")
    parts.append("</section>")

    body = "\n".join(parts)
    return _PAGE_TEMPLATE % {"lang_title": _esc(title), "body": body}


_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>%(lang_title)s</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#e5e5e5;--accent:#0a6e4f;--warn:#b45309;--card:#f7f7f5}
@media (prefers-color-scheme: dark){:root{--bg:#141414;--fg:#ececec;--muted:#9a9a9a;--line:#2c2c2c;--accent:#3ecf9a;--warn:#f59e0b;--card:#1e1e1e}}
*{box-sizing:border-box}body{margin:0 auto;max-width:760px;padding:24px 16px 64px;background:var(--bg);color:var(--fg);font:16px/1.7 -apple-system,"PingFang TC","Noto Sans TC",sans-serif}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.1rem;margin:32px 0 12px;border-bottom:1px solid var(--line);padding-bottom:6px}h3{font-size:1rem;margin:16px 0 4px}
.meta,.due,.date{color:var(--muted);font-size:.85rem;font-weight:normal}
.bar{background:var(--line);border-radius:6px;height:10px;overflow:hidden;display:inline-block;width:70%%;vertical-align:middle}
.fill{background:var(--accent);height:100%%}.pct{margin-left:10px;font-size:.9rem;color:var(--muted)}
.waiting{background:var(--card);border-left:4px solid var(--warn);padding:4px 16px 12px;border-radius:6px;margin-top:24px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:24px}@media (max-width:600px){.cols{grid-template-columns:1fr}}
ul{padding-left:20px}li{margin:6px 0}
table{width:100%%;border-collapse:collapse;font-size:.95rem}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
summary{cursor:pointer;font-weight:600;margin:12px 0}
.st{font-size:.8rem;padding:2px 8px;border-radius:10px;background:var(--line)}
.st-done{background:var(--accent);color:#fff}.st-blocked{background:var(--warn);color:#fff}
.empty{color:var(--muted)}
</style>
</head>
<body>
%(body)s
<footer><p class="meta">本頁由專案資料自動產生。</p></footer>
</body>
</html>
"""
```

- [ ] **Step 4: 執行測試確認通過**

Run: `python3 tools/test_build_dashboard.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/ && git commit -m "feat: 儀表板 HTML 渲染器（白名單輸出，TDD）"
```

---

### Task 7: CLI（--check / 建置）

**Files:**
- Modify: `tools/build_dashboard.py`（追加）
- Modify: `tools/test_build_dashboard.py`（追加）

- [ ] **Step 1: 寫失敗測試（追加）**

```python
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
```

- [ ] **Step 2: 執行確認失敗**

Run: `python3 tools/test_build_dashboard.py -v`
Expected: FAIL —— `AttributeError: ... 'main'`

- [ ] **Step 3: 實作 CLI（追加）**

```python
# ---------- CLI ----------

def main(argv=None):
    ap = argparse.ArgumentParser(description="pm-scaffold 儀表板產生器")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                    help="專案根目錄（預設：repo 根）")
    ap.add_argument("--out", default=None, help="輸出路徑（預設：<root>/docs/index.html）")
    ap.add_argument("--check", action="store_true", help="只驗證資料，不產出")
    args = ap.parse_args(argv)

    project, data, errors = load_all(args.root)
    errors.extend(validate(project, data))
    if errors:
        for e in errors:
            print("✗ %s" % e, file=sys.stderr)
        print("共 %d 個錯誤。" % len(errors), file=sys.stderr)
        return 1
    if args.check:
        print("✓ 資料驗證通過（work %d、decisions %d、qa %d、meetings %d）"
              % (len(data["work"]), len(data["decisions"]), len(data["qa"]), len(data["meetings"])))
        return 0
    out = Path(args.out) if args.out else Path(args.root) / "docs" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(project, data["work"]), encoding="utf-8")
    print("✓ 已產出 %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 執行測試確認全部通過**

Run: `python3 tools/test_build_dashboard.py -v`
Expected: 全部 PASS（約 20 項）

- [ ] **Step 5: 人工煙霧測試**

Run: `python3 tools/build_dashboard.py --root tools/fixtures/sample --out /tmp/pm-preview.html && open /tmp/pm-preview.html`
Expected: 瀏覽器開啟，五區塊齊全、繁中、RWD 可用。

- [ ] **Step 6: Commit**

```bash
git add tools/ && git commit -m "feat: CLI --check 與建置模式（TDD）"
```

---

### Task 8: Scaffold 資料模板與 _example 範例檔

**Files:**
- Create: `project.yaml`
- Create: `work/_example-WI-000.md`、`decisions/_example-D-000.md`、`qa/_example-QA-000.md`、`meetings/_example-2026-01-01-standup.md`
- Create: `source/README.md`

- [ ] **Step 1: 寫 project.yaml 模板**

須通過 `--check`（pm-init 啟用時改寫）：

```yaml
# 專案基本資料。clone 後執行 pm-init playbook 會引導改寫本檔。
name: 未初始化專案（請跑 pm-init）
client: 客戶名稱
started: 2026-01-01
milestones:
  - id: M1
    title: 範例里程碑
    due: 2026-12-31
people:
  - name: 請填姓名
    role: pm
engineering_repos: []
dashboard:
  title: 專案建置進度
  url: ""
```

- [ ] **Step 2: 寫四個 _example 範例檔**

`work/_example-WI-000.md`（`_` 開頭，工具跳過，僅作 schema 活文件）：

```markdown
---
id: WI-000
title: 範例工項（複製本檔去掉底線開頭建新工項）
status: todo           # todo | doing | blocked | review | done | dropped
owner: 姓名
blocked_on: ""         # status=blocked 時必填：client | internal | vendor | WI-###
blocked_note: ""       # blocked_on=client 時必填，會顯示在客戶儀表板
priority: mvp          # mvp | recommended | nice
milestone: M1
spec_ref: 規格書 §x     # 回指 source/ 文件；無來源填「口頭需求」並連結 decision/qa
client_visible: true   # 是否出現在客戶儀表板
estimate: 1d
updated: 2026-01-01
---

## 說明
做什麼、驗收條件。

## 進度日誌
- 2026-01-01 姓名：建立
```

`decisions/_example-D-000.md`：

```markdown
---
id: D-000
date: 2026-01-01
decided_by: 拍板者
status: decided        # decided | superseded
refs: []               # 相關 qa / meetings / source 檔案路徑
---

## 背景

## 選項

## 決定

## 重新討論的條件
```

`qa/_example-QA-000.md`：

```markdown
---
id: QA-000
date: 2026-01-01
asked_by: 客戶窗口
channel: email         # email | meeting | line | other
status: answered       # answered | pending
refs: []
---

## 客戶問什麼

## 我們答什麼

## 依據
（引 source/ 或 decisions/ 具體段落）
```

`meetings/_example-2026-01-01-standup.md`：

```markdown
---
date: 2026-01-01
type: standup          # standup | client | internal
attendees: []
---

## 摘要

## 工項異動
- WI-### → 狀態（一行一項）
```

`source/README.md`：

```markdown
# source/ — 原始文件（唯讀）

放簽約基準文件：規格書、報價單、合約附件。

**規則：只進不改。** AI 與人都只能引用，不得修改。範圍要變就開一筆
`decisions/`，在裡面引用本目錄的文件段落。
```

- [ ] **Step 3: 驗證 repo 根可通過 check**

Run: `python3 tools/build_dashboard.py --check`
Expected: `✓ 資料驗證通過（work 0、decisions 0、qa 0、meetings 0）`（`_` 檔被跳過）

- [ ] **Step 4: Commit**

```bash
git add project.yaml work decisions qa meetings source && git commit -m "feat: 資料模板與範例檔"
```

---

### Task 9: AGENTS.md 與 CLAUDE.md stub

**Files:**
- Create: `AGENTS.md`
- Create: `CLAUDE.md`

- [ ] **Step 1: 寫 AGENTS.md**

```markdown
# AGENTS.md — AI 協作總則

本 repo 是「專案管理資料庫」，不是程式碼庫。AI 在此的工作是：依 playbook
維護 Markdown 資料、產生客戶儀表板、依據資料回答問題。全程使用繁體中文。

## 情境 → Playbook 對照表

| 使用者說的話（舉例） | 執行的 playbook |
|---|---|
| 「初始化專案」「匯入規格書」 | `skills/pm-init/SKILL.md` |
| 「我來報進度」「更新一下狀態」 | `skills/pm-standup/SKILL.md` |
| 「去看工程 repo」「同步 commits」 | `skills/pm-sync-repo/SKILL.md` |
| 「更新儀表板」「產進度頁」 | `skills/pm-dashboard/SKILL.md` |
| 「客戶問…要怎麼回」「合約有沒有含…」 | `skills/pm-ask/SKILL.md` |
| 「健檢」「這週有什麼要催的」 | `skills/pm-review/SKILL.md` |

不支援 skill 機制的工具：直接讀上表對應的 SKILL.md 並照其 SOP 執行。

## 鐵律

1. **source/ 唯讀**——只能引用，不得修改。範圍變更走 `decisions/`。
2. **docs/index.html 禁止手改**——只能由 `tools/build_dashboard.py` 產生。
3. **只記錄聽到／讀到的**——不腦補進度、不代填欄位；不確定就問。
4. **狀態轉 blocked 必填 `blocked_on`**；卡客戶必填 `blocked_note`（會公開給客戶看）。
5. **回答客戶相關問題只准引用 repo 內容**，逐點附出處路徑；查無依據要明說。
6. **每次寫入後 commit**，訊息格式：
   `standup: YYYY-MM-DD`｜`wi: WI-### → <狀態>`｜`qa: QA-###`｜
   `decision: D-###`｜`dashboard: rebuild`｜`sync: <repo> @<hash>`
7. 寫入資料後執行 `python3 tools/build_dashboard.py --check`，有錯就修到過。

## 資料模型速查

- `project.yaml`：專案名、客戶、里程碑、成員、工程 repo、儀表板設定
- `work/WI-###-slug.md`：工項。status: todo|doing|blocked|review|done|dropped
- `decisions/D-###-slug.md`：決策（背景→選項→決定→重新討論條件）
- `qa/QA-###-slug.md`：客戶問答（問→答→依據）
- `meetings/YYYY-MM-DD-type.md`：彙報／會議紀錄
- 檔名 `_` 開頭＝範例，工具跳過。id 取號＝目錄內現有最大值 +1。
- 完整欄位定義見各目錄 `_example` 檔與 `docs/specs/`。

## 客戶儀表板白名單（背景知識）

`docs/index.html` 只會包含：title、status、milestone、
blocked_note（僅 blocked_on=client）、專案名與更新日。owner、estimate、
內部備註在產生器層就被排除——但你寫 blocked_note（client）時仍須意識到
**它會被客戶看到**，措辭要對外得體。
```

- [ ] **Step 2: 寫 CLAUDE.md stub**

```markdown
@AGENTS.md
```

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md CLAUDE.md && git commit -m "feat: AGENTS.md 行為總則 + CLAUDE.md stub"
```

---

### Task 10: Playbooks 之一（pm-init、pm-standup、pm-sync-repo）

**Files:**
- Create: `skills/pm-init/SKILL.md`、`skills/pm-standup/SKILL.md`、`skills/pm-sync-repo/SKILL.md`

- [ ] **Step 1: 寫 skills/pm-init/SKILL.md**

```markdown
---
name: pm-init
description: clone 本 scaffold 後首次啟用專案時使用——建立 project.yaml、匯入規格書／報價單成工項、引導 GitHub Pages 設定。觸發語：「初始化專案」「匯入規格書」。
---

# pm-init — 專案初始化

## 前置
- 確認在 repo 根目錄、`git status` 乾淨。
- 讀 `AGENTS.md`（若尚未讀）。

## 步驟

1. **問答式填 project.yaml**：逐項詢問專案名、客戶名、開始日、里程碑
   （id/標題/目標日）、成員（姓名/角色 pm|engineer|sales）、工程 repo 路徑
   （可為空清單）、儀表板抬頭。一次問一題。全部確認後改寫 `project.yaml`。
2. **匯入既有文件（如有）**：請使用者把規格書／報價單放進 `source/`。
   逐份讀取，將可執行項目逐項向使用者確認：標題、priority（mvp|recommended|nice）、
   milestone、spec_ref（引用文件章節）、client_visible、estimate。
   確認一批後以 `work/WI-###-slug.md` 建檔（id 從 WI-001 遞增），status 一律 todo。
   **不確定的項目寧可略過並列出，不要擅自建檔。**
3. **無文件時**：請使用者口述工項清單，同上逐項確認建檔。
4. **驗證**：`python3 tools/build_dashboard.py --check` 須通過。
5. **首次產出儀表板**：`python3 tools/build_dashboard.py`，commit。
6. **GitHub Pages 引導**（人工步驟，念給使用者）：
   - push 到 GitHub private repo（Pages 需 Pro/Team 方案）
   - repo Settings → Pages → Source: Deploy from a branch → main、`/docs`
   - 自訂網域：DNS 加 CNAME 指向 `<帳號>.github.io`，再於 Pages 設定填網域
   - 取得網址後填回 `project.yaml` 的 `dashboard.url`
   - 提醒：頁面「公開但不公告網址」，白名單已過濾內部資訊
7. **收尾**：問「要刪除各目錄的 `_example` 範例檔嗎？」（建議留著當 schema 文件）。
   commit：`chore: pm-init 完成`。
```

- [ ] **Step 2: 寫 skills/pm-standup/SKILL.md**

```markdown
---
name: pm-standup
description: 工程師或 PM 口頭彙報進度時使用——比對工項、確認後更新狀態與日誌、產會議紀錄。觸發語：「我來報進度」「更新狀態」「standup」。
---

# pm-standup — 進度彙報

## 步驟

1. 讀 `project.yaml` 與 `work/` 全部工項（frontmatter 即可），掌握現況。
2. 聽使用者彙報。對每一句進度，比對到具體 WI-###；對不上的內容先問：
   - 「這是新工作嗎？要開新工項嗎？」（要 → 依 `work/_example-WI-000.md`
     schema 逐欄確認後建檔）
   - 「這是既有工項 WI-### 的進度嗎？」
3. **聽到卡關必追問**：卡在誰（client|internal|vendor|WI-###）？卡什麼？
   卡客戶的，把 blocked_note 措辭成可以給客戶看的句子並向使用者確認。
4. 彙整成異動清單，**逐項覆述給使用者確認**後才寫入：
   - 更新 frontmatter（status、blocked_on、blocked_note、updated=今日）
   - 在「進度日誌」最上方追加一行：`- YYYY-MM-DD 姓名：<摘要>`
5. 產 `meetings/YYYY-MM-DD-standup.md`（schema 見 `_example`），
   「工項異動」段落列出本次全部異動。
6. `python3 tools/build_dashboard.py --check` 須通過。
7. commit：`standup: YYYY-MM-DD`。
8. 提醒使用者：「要順便更新儀表板嗎？（pm-dashboard）」

## 紀律
- 只更新聽到的，不腦補。使用者沒提的工項一律不動。
- done 要口頭確認過驗收條件才標，否則用 review。
```

- [ ] **Step 3: 寫 skills/pm-sync-repo/SKILL.md**

```markdown
---
name: pm-sync-repo
description: 掃描 project.yaml 登記的工程 repo commits，草擬工項進度更新，經人工確認後寫入。觸發語：「去看工程 repo」「同步 commits」。
---

# pm-sync-repo — 工程 repo 同步

## 步驟

1. 讀 `project.yaml` 的 `engineering_repos`。空清單 → 告知使用者請先在
   pm-init 或手動登記，結束。
2. 對每個 repo：
   - 本機路徑：`git -C <path> log --oneline --no-merges <last_synced>..HEAD`
     （`last_synced` 為空 → 取最近 30 筆並告知使用者）
   - 讀不到 repo → 回報並跳過，不猜。
3. 將 commits 對應到工項：訊息含 `WI-###` 直接對應；否則以關鍵字比對工項
   title 與說明，標註信心（高/低）。
4. **產出草稿清單**（不寫入）：每項列 commit → 對應工項 → 建議動作
   （追加日誌／建議轉 review）。對不上的 commits 單獨列出待人工歸類。
5. 使用者逐項確認後才寫入工項（追加日誌一行：
   `- YYYY-MM-DD 同步：<commit 摘要>（<hash 前 7 碼>）`；狀態只有在使用者
   明確同意時才改）。
6. 更新 `project.yaml` 該 repo 的 `last_synced` 為目前 HEAD hash。
7. `python3 tools/build_dashboard.py --check`，commit：`sync: <repo名> @<hash 前 7 碼>`。

## 紀律
- 本 playbook 永遠是「草擬 → 人工確認 → 寫入」，不得跳過確認。
- commit 存在不代表功能完成；不得僅憑 commit 將工項標 done。
```

- [ ] **Step 4: Commit**

```bash
git add skills && git commit -m "feat: playbooks pm-init / pm-standup / pm-sync-repo"
```

---

### Task 11: Playbooks 之二（pm-dashboard、pm-ask、pm-review）

**Files:**
- Create: `skills/pm-dashboard/SKILL.md`、`skills/pm-ask/SKILL.md`、`skills/pm-review/SKILL.md`

- [ ] **Step 1: 寫 skills/pm-dashboard/SKILL.md**

```markdown
---
name: pm-dashboard
description: 重建客戶進度儀表板並發布。觸發語：「更新儀表板」「產進度頁」。
---

# pm-dashboard — 儀表板重建

## 步驟

1. `python3 tools/build_dashboard.py --check`——失敗即停，把錯誤逐條回報
   給使用者，修好資料再來。
2. `python3 tools/build_dashboard.py` 產出 `docs/index.html`。
3. `git diff --stat docs/index.html` 給使用者看變化摘要。
4. commit：`dashboard: rebuild`；若 repo 有 remote 則 push。
5. 回報 `project.yaml` 裡的 `dashboard.url`（未設定則提示 pm-init 第 6 步）。

## 紀律
- 禁止手改 `docs/index.html`。版面要改 → 改 `tools/build_dashboard.py`
  的模板並跑測試（`python3 tools/test_build_dashboard.py`）。
- 白名單欄位不得擴充，除非使用者明確要求並理解該欄位會公開。
```

- [ ] **Step 2: 寫 skills/pm-ask/SKILL.md**

```markdown
---
name: pm-ask
description: 業務或 PM 要回答客戶問題時使用——只從 repo 資料回答並附出處，答案可沉澱為 qa/ 檔。觸發語：「客戶問…要怎麼回」「合約有沒有含…」。
---

# pm-ask — 客戶問題應答

## 步驟

1. 針對問題檢索 repo：`source/`（規格、報價、合約）、`decisions/`、`qa/`
   （可能答過）、`work/`（現況）。grep + 逐檔閱讀相關段落。
2. 組答案：**每個論點附出處**（檔案路徑＋章節/段落）。格式：
   - 結論（可直接轉述給客戶的措辭）
   - 依據（逐條列出處）
   - 注意事項（如有：相關卡關、未定案的 decisions）
3. **查無依據就明說**：「repo 內沒有這題的依據，建議開會確認後記入
   decisions/」。禁止推測合約內容、禁止以一般常識冒充專案事實。
4. 問使用者：「要把這題存成 qa/ 檔嗎？」要 → 依 `qa/_example-QA-000.md`
   schema 建檔（問／答／依據照實記錄），commit：`qa: QA-###`。
   客戶還沒得到答覆的，status 用 pending。
```

- [ ] **Step 3: 寫 skills/pm-review/SKILL.md**

```markdown
---
name: pm-review
description: 每週健檢——找出過期工項、老化卡關、未答問題、儀表板落後，產出行動清單。觸發語：「健檢」「這週有什麼要催的」。
---

# pm-review — 週期健檢

## 步驟

1. `python3 tools/build_dashboard.py --check`——先確保資料乾淨。
2. 以今日日期掃描：
   - **doing/review 超過 7 天未更新**（updated 距今）→ 列出，該問 owner
   - **blocked 超過 5 天** → 列出，附 blocked_on（卡客戶 → 該催客戶窗口；
     卡內部 → 該催誰）
   - **qa/ 的 pending** → 列出，客戶還在等答案
   - **儀表板落後**：`git log -1 --format=%ci -- docs/index.html` 早於
     work/ 最後異動 → 建議跑 pm-dashboard
   - milestone due 已過但仍有未完成工項 → 列出
3. 產出行動清單（誰、該做什麼、依據哪個檔案），按急迫排序。
4. **只報告，不自動改資料。** 使用者針對個別項目下指令後才動
   （轉交 pm-standup / pm-dashboard 流程）。
```

- [ ] **Step 4: Commit**

```bash
git add skills && git commit -m "feat: playbooks pm-dashboard / pm-ask / pm-review"
```

---

### Task 12: Claude Code 接線（symlinks）

**Files:**
- Create: `.claude/skills/pm-*`（6 個相對 symlink）

- [ ] **Step 1: 建 symlinks**

```bash
cd /Users/largitdata/project/pm-scaffold
for s in pm-init pm-standup pm-sync-repo pm-dashboard pm-ask pm-review; do
  ln -sfn ../../skills/$s .claude/skills/$s
done
```

- [ ] **Step 2: 驗證 symlink 解析**

Run: `ls -l .claude/skills/ && cat .claude/skills/pm-standup/SKILL.md | head -3`
Expected: 6 個 symlink 全部指向 `../../skills/<name>`，cat 能讀到 frontmatter。

- [ ] **Step 3: Commit**

```bash
git add .claude && git commit -m "feat: .claude/skills symlinks（Claude Code 接線）"
```

---

### Task 13: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: 寫 README.md**

```markdown
# pm-scaffold — AI 協作的專案管理 scaffold

可 clone 重用的客戶交付案管理 repo：Markdown 為真相來源、AI 依 playbook
維護資料、零依賴腳本產出客戶進度儀表板（GitHub Pages）。

## 這裡放什麼、不放什麼

放：工項與進度、卡關、決策、客戶問答、會議紀錄、簽約文件。
不放：程式碼（工程 repo 另在他處，僅於 `project.yaml` 登記路徑）。

## 快速開始

```bash
git clone <本repo> my-project-pm && cd my-project-pm
rm -rf .git && git init -b main        # 斷開 scaffold 歷史
python3 tools/test_build_dashboard.py  # 自我檢查（應全部通過）
```

然後開你的 AI 工具（Claude Code / Codex / 其他），說「**初始化專案**」——
agent 會照 `skills/pm-init/SKILL.md` 引導你完成設定、匯入規格書、
設定 GitHub Pages。

### GitHub Pages（客戶儀表板）

private repo 需 GitHub Pro / Team。Settings → Pages → main + `/docs`。
自訂子網域：DNS CNAME 指向 `<帳號>.github.io`。頁面為
**公開但不公告網址**；內容經白名單過濾（詳見 AGENTS.md）。

## 三種角色怎麼用

| 角色 | 對 AI 說 | 發生什麼 |
|---|---|---|
| 工程師 | 「我來報進度」 | AI 比對工項、確認後更新狀態與日誌（pm-standup）；也可說「去看我的 repo commits」（pm-sync-repo） |
| 業務 | 「客戶問退貨流程含不含，怎麼回？」 | AI 只從 repo 資料回答並附出處，可存成 qa/ 檔（pm-ask） |
| PM | 「健檢」「更新儀表板」 | 行動清單（pm-review）；重建並發布 docs/index.html（pm-dashboard） |

## AI 工具接線

- **Claude Code**：內建（`.claude/skills/` symlink 已就緒；`CLAUDE.md` → `AGENTS.md`）。
- **Codex / 其他支援 AGENTS.md 的工具**：自動讀 `AGENTS.md`，內含
  「情境 → playbook」對照表。
- **完全不支援 skill 的工具**：對 agent 說「照 `skills/<名稱>/SKILL.md` 跑」。

## 資料模型

一事一檔、YAML frontmatter。schema 見各目錄 `_example-*` 檔（工具會跳過
`_` 開頭檔案）。完整規格：`docs/specs/2026-08-19-pm-scaffold-design.md`。

| 目錄 | 內容 | id |
|---|---|---|
| `work/` | 工項（狀態機 todo→doing→review→done；blocked 必填卡在誰） | WI-### |
| `decisions/` | 決策：背景→選項→決定→重新討論條件 | D-### |
| `qa/` | 客戶問答：問→答→依據 | QA-### |
| `meetings/` | 彙報／會議紀錄 | 日期 |
| `source/` | 簽約文件，**唯讀** | — |

## 儀表板

`python3 tools/build_dashboard.py`（`--check` 只驗證）。輸出
`docs/index.html`，單檔、繁中、RWD、亮暗色。白名單硬編碼：客戶只看得到
工項名稱、狀態、里程碑、待客戶事項；owner、工時、內部備註不會出現。
```

- [ ] **Step 2: Commit**

```bash
git add README.md && git commit -m "docs: README（啟用步驟、角色速查、接線說明）"
```

---

### Task 14: 驗收總檢

**Files:** 無新增，逐條核對 spec §七。

- [ ] **Step 1: 全測試 + repo 根 check**

```bash
python3 tools/test_build_dashboard.py -v && python3 tools/build_dashboard.py --check
```
Expected: 測試全 PASS；check 通過。

- [ ] **Step 2: self-contained 驗證（clone 到暫存目錄跑）**

```bash
git clone /Users/largitdata/project/pm-scaffold /tmp/pm-scaffold-clone-test
cd /tmp/pm-scaffold-clone-test
python3 tools/test_build_dashboard.py && python3 tools/build_dashboard.py --check
ls -l .claude/skills/ | grep -c '\->'   # 應為 6
cd - && rm -rf /tmp/pm-scaffold-clone-test
```
Expected: 測試通過、check 通過、symlink 6 個。

- [ ] **Step 3: 白名單目視複核**

```bash
python3 tools/build_dashboard.py --root tools/fixtures/sample --out /tmp/wl.html
grep -c "內部人員\|42d\|內部秘密\|規格書 §" /tmp/wl.html; rm /tmp/wl.html
```
Expected: `0`（grep 無匹配，exit code 1 屬正常）。

- [ ] **Step 4: 對照 spec §七逐條打勾**，缺漏即補。

- [ ] **Step 5: 最終 commit（如有調整）**

```bash
git add -A && git commit -m "chore: 驗收總檢完成" --allow-empty
```

---

## 執行期修訂紀錄

- Task 2/3 追加：解析器修復（同縮排清單、冒號清單元素、引號逗號、行尾註解、#值報錯、尾端未解析防護）與載入器強化（utf-8-sig、UnicodeDecodeError/OSError 分層收集）——品質審查發現，皆有回歸測試。
- Task 5：`_date` 補日曆有效性檢查（`datetime.date.fromisoformat`），檔頭需 `import datetime`；原 DATE_RE 只驗形狀會放過 `2026-13-99`。
- Task 5 追加：blocked_on 為 WI-### 時需驗證該工項存在（收集 `wi_refs`，work 迴圈後比對 `seen_wi`）——spec §六「WI 引用存在」原計畫漏實作。
- Task 5-7 追加（品質審查）：非法資料形狀（頂層清單、milestones 非 dict 清單）改報繁中錯誤而非 traceback；milestones 至少一個；work 欄位須純量；blocked_on 禁自我引用；渲染器空清單有文案、跳過非 dict milestone；CLI root 不存在早退。皆有回歸測試。

## Self-Review 紀錄

- **Spec 覆蓋**：§三佈局→T1/T8/T9/T10-13；§四資料模型→T4/T5/T8；§五 playbooks→T10/T11；§六產生器→T2/T3/T5/T6/T7；§七驗收→T14。
- **型別一致**：`load_all` 回傳 `(project, data, errors)`，T5/T6/T7 測試皆按此簽名；`main(argv)` 回傳 int。
- **無佔位符**：所有檔案內容完整給出。
