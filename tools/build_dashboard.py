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
