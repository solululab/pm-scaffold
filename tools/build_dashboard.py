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


def _strip_comment(s):
    """去除引號外的行尾註解（前面有空白、# 後接空白或行尾才算註解）。

    `status: todo  # 說明` → 註解，去除。
    `color: #fff`（# 後無空白）→ 視為值含 #，直接報錯，要求加引號，
    避免靜默清空資料。值要含「 #」請用引號包住。
    """
    quote = None
    for idx, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and idx > 0 and s[idx - 1] in " \t":
            if idx + 1 < len(s) and s[idx + 1] not in " \t":
                raise ValueError(
                    "值疑似含 #（如色碼/編號）：%r——請用引號包住值，"
                    "或在註解的 # 後加空白" % s)
            return s[:idx].rstrip()
    return s


def _lines(text):
    out = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        line = _strip_comment(raw.rstrip())
        out.append((len(line) - len(line.lstrip(" ")), line.strip()))
    return out


def parse_yaml_subset(text):
    lines = _lines(text)
    if not lines:
        return {}
    obj, end = _parse_block(lines, 0, lines[0][0])
    if end != len(lines):
        raise ValueError("無法解析（有效行 %d 之後）：%r" % (end, lines[end][1]))
    return obj


# 以下三個函式互相遞迴，共用慣例：(lines, i, indent) -> (值, 下一個未消化的行號)。
# 重複的 key 為後者覆蓋（同多數 YAML 實作）；重複 id 的偵測屬驗證器職責，非解析器。

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
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            # 巢狀區塊：比 key 深，或與 key 同縮排的清單（YAML 常見寫法）
            if nxt and (nxt[0] > ind or (nxt[0] == ind and nxt[1].startswith("- "))):
                result[key], i = _parse_block(lines, i + 1, nxt[0])
            else:
                result[key] = ""
                i += 1
        elif rest.startswith("[") and rest.endswith("]"):
            result[key] = _parse_inline_list(rest, line)
            i += 1
        else:
            result[key] = parse_scalar(rest)
            i += 1
    return result, i


def _parse_inline_list(rest, context):
    items = [parse_scalar(x) for x in rest[1:-1].split(",") if x.strip()]
    for it in items:
        if "'" in it or '"' in it:
            raise ValueError("行內清單元素含引號/逗號歧義，請改用縮排清單：%r" % context)
    return items


# 清單項是 dict 的判準：開頭是「key:」且冒號後接空白或行尾（URL 如 http://x 不會誤中）
_ITEM_KEY_RE = re.compile(r"^[^\s:#]+:(\s|$)")


def _parse_list(lines, i, indent):
    result = []
    while i < len(lines):
        ind, line = lines[i]
        if ind != indent or not line.startswith("- "):
            break
        content = line[2:].strip()
        if _ITEM_KEY_RE.match(content):
            key, _, rest = content.partition(":")
            item = {key.strip(): parse_scalar(rest)}
            i += 1
            # dict 項的後續欄位縮排 = 清單縮排 + 2（「- 」佔兩格）
            while i < len(lines) and lines[i][0] == indent + 2 and not lines[i][1].startswith("- "):
                k, _, r = lines[i][1].partition(":")
                item[k.strip()] = parse_scalar(r)
                i += 1
            result.append(item)
        else:
            result.append(parse_scalar(content))
            i += 1
    return result, i


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
            meta, body = parse_frontmatter(f.read_text(encoding="utf-8-sig"), str(f))
            items.append({"path": str(f), "meta": meta, "body": body})
        except UnicodeDecodeError as e:
            errors.append("%s: 非 UTF-8 編碼（%s）" % (f, e))
        except OSError as e:
            errors.append("%s: 無法讀取（%s）" % (f, e))
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
            project = parse_yaml_subset(pf.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError) as e:
            errors.append("project.yaml: %s" % e)
    else:
        errors.append("project.yaml: 檔案不存在")
    data = {}
    for name in ("work", "decisions", "qa", "meetings"):
        items, errs = load_dir(root / name)
        data[name] = items
        errors.extend(errs)
    return project, data, errors
