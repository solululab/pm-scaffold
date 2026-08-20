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
import datetime
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
            if not isinstance(meta, dict):
                errors.append("%s: frontmatter 須為 key: value 欄位（不可為清單）" % f)
                continue
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
            if not isinstance(project, dict):
                errors.append("project.yaml: 頂層須為 key: value 設定（不可為清單）")
                project = {}
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


# ---------- 驗證 ----------

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WORK_STATUS = {"todo", "doing", "blocked", "review", "done", "dropped"}
WORK_SIDE = {"vendor", "client", "both"}
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
    if not isinstance(project, dict):
        errors.append("project.yaml: 頂層須為 key: value 設定（不可為清單）")
        project = {}
    if not str(project.get("name", "") or "").strip():
        errors.append("project.yaml: 缺少必填欄位 name")
    _date(project, "started", "project.yaml", errors)
    milestones = project.get("milestones") or []
    if not isinstance(milestones, list):
        errors.append("project.yaml: milestones 須為清單（- id: ... 的縮排清單）")
        milestones = []
    mids = set()
    for m in milestones:
        if not isinstance(m, dict):
            errors.append("project.yaml: milestone 須為含 id/title/due 的項目（得到 %r）" % (m,))
            continue
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
    if not mids:
        errors.append("project.yaml: 至少需要一個 milestone")
    dash = project.get("dashboard")
    if isinstance(dash, dict):
        h = str(dash.get("health", "") or "").strip()
        if h and h not in HEALTH_LABEL:
            errors.append("project.yaml: dashboard.health 值非法：%r（允許：green|amber|red）" % h)

    # work/
    seen_wi = set()
    wi_refs = []
    for item in data["work"]:
        meta, path = item["meta"], item["path"]
        for k, v in meta.items():
            if not isinstance(v, str):
                errors.append("%s: 欄位 %s 須為單一值（得到 %r）" % (path, k, v))
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
        _date(meta, "due", path, errors, required=False)
        side = str(meta.get("side", "") or "").strip()
        if side and side not in WORK_SIDE:
            errors.append("%s: side 值非法：%r（允許：%s）" % (path, side, "|".join(sorted(WORK_SIDE))))
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
            elif bon == wid:
                errors.append("%s: blocked_on 不可引用自身" % path)
            elif bon.startswith("WI-"):
                wi_refs.append((path, bon))
            if bon == "client" and not str(meta.get("blocked_note", "") or "").strip():
                errors.append("%s: blocked_on=client 時 blocked_note 為必填（會上儀表板）" % path)

    # blocked_on 引用的工項必須存在（需全部 id 收集完才能查）
    for path, ref in wi_refs:
        if ref not in seen_wi:
            errors.append("%s: blocked_on 引用的 %s 不存在" % (path, ref))

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


# ---------- 渲染（白名單輸出） ----------

STATUS_LABEL = {"todo": "待辦", "doing": "進行中", "blocked": "卡關",
                "review": "驗收中", "done": "完成"}
SIDE_DEFAULT_LABELS = {"vendor": "開發方", "client": "客戶", "both": "雙方"}
HEALTH_LABEL = {"green": "進度正常", "amber": "有風險", "red": "進度延誤"}
HEALTH_ICON = {"green": "🟢", "amber": "🟡", "red": "🔴"}


def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _visible(works):
    """儀表板收錄範圍：client_visible=true 且非 dropped。"""
    return [w for w in works
            if str(w["meta"].get("client_visible", "")).strip() == "true"
            and w["meta"].get("status") != "dropped"]


def _due_span(meta, today, prefix=""):
    """工項截止日標籤；已過期且未完成者加 overdue 樣式。無 due 回傳空字串。"""
    due = str(meta.get("due", "") or "").strip()
    if not due:
        return ""
    cls = "due overdue" if due < today and meta.get("status") != "done" else "due"
    return '<span class="%s">%s%s</span>' % (cls, prefix, _esc(due))


def _bar(done, total):
    pct = int(round(done * 100.0 / total)) if total else 0
    return ('<div class="bar"><div class="fill" style="width:%d%%"></div></div>'
            '<span class="pct">%d / %d</span>' % (pct, done, total))


def _dot_class(meta, today):
    st = meta.get("status", "")
    due = str(meta.get("due", "") or "").strip()
    if st != "done" and due and due < today:
        return "dot-overdue"
    if st == "done":
        return "dot-done"
    if st == "blocked":
        return "dot-blocked"
    return "dot-todo"


def _timeline(start, end, items, today):
    """里程碑時間軸：工項依 due 落點成點，顏色依狀態，加今天標線。

    起訖或工項 due 解析不出來就靜默省略（timeline 是加值視覺，不擋渲染）。
    同一落點的點垂直堆疊，避免互相蓋住。
    """
    try:
        s = datetime.date.fromisoformat(str(start or "").strip())
        e = datetime.date.fromisoformat(str(end or "").strip())
    except ValueError:
        return ""
    span = (e - s).days
    if span <= 0:
        return ""

    def pct(d):
        return max(0, min(100, int(round((d - s).days * 100.0 / span))))

    dots, lanes = [], {}
    for w in items:
        due = str(w["meta"].get("due", "") or "").strip()
        try:
            d = datetime.date.fromisoformat(due)
        except ValueError:
            continue
        p = pct(d)
        lane = lanes.get(p, 0)
        lanes[p] = lane + 1
        dots.append('<span class="dot %s" style="left:%d%%;top:%dpx" title="%s（截止 %s）"></span>'
                    % (_dot_class(w["meta"], today), p, 5 + lane * 12,
                       _esc(w["meta"].get("title", "")), _esc(due)))
    if not dots:
        return ""
    height = 10 + 12 * max(lanes.values())
    try:
        tp = pct(datetime.date.fromisoformat(today))
        today_html = '<span class="today" style="left:%d%%" title="今天 %s"></span>' % (tp, _esc(today))
    except ValueError:
        today_html = ""
    return ('<div class="tl" style="height:%dpx"><span class="tl-date l">%s</span>'
            '<span class="tl-date r">%s</span>%s%s</div>'
            % (height + 10, _esc(str(start)), _esc(str(end)), today_html, "".join(dots)))


def render_html(project, works):
    vis = _visible(works)
    today = datetime.date.today().isoformat()
    side_labels = dict(SIDE_DEFAULT_LABELS)
    conf = (project.get("dashboard") or {}).get("side_labels")
    if isinstance(conf, dict):
        side_labels.update({k: str(v).strip() for k, v in conf.items()
                            if k in WORK_SIDE and str(v).strip()})
    show_side = any(str(w["meta"].get("side", "") or "").strip() for w in vis)
    dash = project.get("dashboard") or {}
    title = str(dash.get("title") or "").strip() or "%s 專案進度" % project.get("name", "")
    updated = max((w["meta"].get("updated", "") for w in vis), default="—")

    mvp = [w for w in vis if w["meta"].get("priority") == "mvp"]
    mvp_done = [w for w in mvp if w["meta"].get("status") == "done"]

    parts = []
    parts.append("<header><h1>%s</h1>" % _esc(title))
    parts.append('<p class="meta">最後更新：%s</p>' % _esc(updated))

    # 健康度燈號：由 PM 於 project.yaml dashboard.health 手動評估，不自動判定
    health = str(dash.get("health", "") or "").strip()
    if health in HEALTH_LABEL:
        note = str(dash.get("health_note", "") or "").strip()
        parts.append('<p><span class="health health-%s">%s %s</span>%s</p>'
                     % (health, HEALTH_ICON[health], HEALTH_LABEL[health],
                        ' <span class="meta">%s</span>' % _esc(note) if note else ""))

    # KPI 速覽
    pct_val = int(round(len(mvp_done) * 100.0 / len(mvp))) if mvp else 0
    doing_n = len([w for w in vis if w["meta"].get("status") in ("doing", "review")])
    waiting_n = len([w for w in vis if w["meta"].get("status") == "blocked"
                     and w["meta"].get("blocked_on") == "client"])
    next_ms = None
    for m in project.get("milestones") or []:
        if not isinstance(m, dict):
            continue
        d = str(m.get("due", "") or "").strip()
        try:
            datetime.date.fromisoformat(d)
        except ValueError:
            continue
        if d >= today and (next_ms is None or d < next_ms[1]):
            next_ms = (str(m.get("id", "")), d)
    tiles = ['<div class="kpi"><div class="lbl">整體進度（MVP）</div><div class="num">%d%%</div>%s</div>'
             % (pct_val, _bar(len(mvp_done), len(mvp)))]
    if next_ms:
        days = (datetime.date.fromisoformat(next_ms[1]) - datetime.date.fromisoformat(today)).days
        tiles.append('<div class="kpi"><div class="lbl">距 %s 目標</div><div class="num">%d 天</div>'
                     '<div class="meta">%s</div></div>' % (_esc(next_ms[0]), days, _esc(next_ms[1])))
    tiles.append('<div class="kpi"><div class="lbl">進行中</div><div class="num">%d 項</div></div>' % doing_n)
    tiles.append('<div class="kpi"><div class="lbl">待客戶</div><div class="num">%d 項</div></div>' % waiting_n)
    parts.append('<div class="kpis">%s</div></header>' % "".join(tiles))

    parts.append("<section><h2>里程碑</h2>")
    has_tl = False
    for m in project.get("milestones") or []:
        if not isinstance(m, dict):
            continue
        mid = m.get("id", "")
        mitems = [w for w in vis if w["meta"].get("milestone") == mid]
        mdone = [w for w in mitems if w["meta"].get("status") == "done"]
        tl = _timeline(project.get("started", ""), m.get("due", ""), mitems, today)
        has_tl = has_tl or bool(tl)
        parts.append('<div class="ms"><h3>%s %s <span class="due">目標 %s</span></h3>%s%s</div>'
                     % (_esc(mid), _esc(m.get("title", "")), _esc(m.get("due", "")),
                        _bar(len(mdone), len(mitems)), tl))
    if has_tl:
        parts.append('<p class="legend">'
                     '<span class="dot dot-done"></span>完成'
                     '<span class="dot dot-todo"></span>待辦／進行'
                     '<span class="dot dot-blocked"></span>卡關'
                     '<span class="dot dot-overdue"></span>逾期'
                     '<span class="today-sample"></span>今天</p>')
    parts.append("</section>")

    upcoming = []
    for w in vis:
        due = str(w["meta"].get("due", "") or "").strip()
        if not due or w["meta"].get("status") == "done":
            continue
        try:
            days = (datetime.date.fromisoformat(due) - datetime.date.fromisoformat(today)).days
        except ValueError:
            continue
        if days <= 14:
            upcoming.append((due, days, w))
    upcoming.sort(key=lambda x: x[0])
    parts.append('<div class="grid2"><section><h2>📅 近期截止</h2>')
    if upcoming:
        parts.append("<ul>")
        for due, days, w in upcoming:
            if days < 0:
                tag = '<span class="due overdue">逾期 %d 天</span>' % -days
            elif days == 0:
                tag = '<span class="due overdue">今天截止</span>'
            else:
                tag = '<span class="due">剩 %d 天（%s）</span>' % (days, _esc(due))
            parts.append("<li>%s %s</li>" % (_esc(w["meta"].get("title", "")), tag))
        parts.append("</ul>")
    else:
        parts.append('<p class="empty">未來兩週內沒有截止項目。</p>')
    parts.append("</section>")

    waiting = [w for w in vis if w["meta"].get("status") == "blocked"
               and w["meta"].get("blocked_on") == "client"]
    parts.append('<section class="waiting"><h2>⏳ 待客戶事項</h2>')
    if waiting:
        parts.append("<ul>")
        for w in waiting:
            due = _due_span(w["meta"], today, prefix="截止 ")
            parts.append("<li><strong>%s</strong>%s：%s</li>"
                         % (_esc(w["meta"].get("title", "")),
                            " " + due if due else "",
                            _esc(w["meta"].get("blocked_note", ""))))
        parts.append("</ul>")
    else:
        parts.append('<p class="empty">目前沒有待客戶提供的事項。</p>')
    parts.append("</section></div>")

    doing = [w for w in vis if w["meta"].get("status") in ("doing", "review")]
    recent = sorted((w for w in vis if w["meta"].get("status") == "done"),
                    key=lambda w: w["meta"].get("updated", ""), reverse=True)[:10]
    parts.append('<section class="cols"><div><h2>進行中</h2>')
    if doing:
        parts.append("<ul>")
        parts.extend("<li>%s <span class=\"tag\">%s</span></li>"
                     % (_esc(w["meta"].get("title", "")), STATUS_LABEL.get(w["meta"].get("status"), ""))
                     for w in doing)
        parts.append("</ul>")
    else:
        parts.append('<p class="empty">目前沒有進行中的項目。</p>')
    parts.append("</div><div><h2>最近完成</h2>")
    if recent:
        parts.append("<ul>")
        parts.extend("<li>%s <span class=\"date\">%s</span></li>"
                     % (_esc(w["meta"].get("title", "")), _esc(w["meta"].get("updated", "")))
                     for w in recent)
        parts.append("</ul>")
    else:
        parts.append('<p class="empty">尚無完成項目。</p>')
    parts.append("</div></section>")

    parts.append("<section><h2>全部工項</h2>")
    for m in project.get("milestones") or []:
        if not isinstance(m, dict):
            continue
        mid = m.get("id", "")
        mitems = [w for w in vis if w["meta"].get("milestone") == mid]
        if not mitems:
            continue
        head = ("<tr><th>項目</th>" + ("<th>負責方</th>" if show_side else "")
                + "<th>狀態</th><th>截止</th></tr>")
        parts.append("<details open><summary>%s %s（%d 項）</summary><table>%s"
                     % (_esc(mid), _esc(m.get("title", "")), len(mitems), head))
        for w in mitems:
            st = w["meta"].get("status", "")
            side_td = ""
            if show_side:
                side = str(w["meta"].get("side", "") or "").strip()
                side_td = "<td>%s</td>" % (_esc(side_labels[side]) if side in side_labels else "—")
            parts.append('<tr><td>%s</td>%s<td><span class="st st-%s">%s</span></td><td>%s</td></tr>'
                         % (_esc(w["meta"].get("title", "")), side_td, _esc(st), STATUS_LABEL.get(st, _esc(st)),
                            _due_span(w["meta"], today) or '<span class="due">—</span>'))
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
:root{--bg:#fff;--fg:#1a1a1a;--muted:#666;--line:#e5e5e5;--accent:#0a6e4f;--warn:#b45309;--danger:#c0392b;--card:#f7f7f5}
@media (prefers-color-scheme: dark){:root{--bg:#141414;--fg:#ececec;--muted:#9a9a9a;--line:#2c2c2c;--accent:#3ecf9a;--warn:#f59e0b;--danger:#f87171;--card:#1e1e1e}}
*{box-sizing:border-box}body{margin:0 auto;max-width:1120px;padding:24px 24px 64px;background:var(--bg);color:var(--fg);font:16px/1.7 -apple-system,"PingFang TC","Noto Sans TC",sans-serif}
h1{font-size:1.5rem;margin:0 0 4px}h2{font-size:1.1rem;margin:32px 0 12px;border-bottom:1px solid var(--line);padding-bottom:6px}h3{font-size:1rem;margin:16px 0 4px}
.meta,.due,.date{color:var(--muted);font-size:.85rem;font-weight:normal}
.overdue{color:var(--danger);font-weight:600}
.tl{position:relative;background:var(--card);border-radius:6px;margin:8px 0 2px;overflow:hidden}
.dot{position:absolute;width:10px;height:10px;border-radius:50%%;transform:translateX(-50%%)}
.dot-done{background:var(--accent)}.dot-todo{background:var(--muted)}
.dot-blocked{background:var(--warn)}.dot-overdue{background:var(--danger)}
.today{position:absolute;top:0;bottom:0;width:2px;background:var(--fg);opacity:.45;transform:translateX(-50%%)}
.tl-date{position:absolute;bottom:0;font-size:.7rem;color:var(--muted)}
.tl-date.l{left:4px}.tl-date.r{right:4px}
.legend{color:var(--muted);font-size:.8rem;margin:8px 0 0}
.legend .dot{position:static;display:inline-block;transform:none;vertical-align:middle;margin:0 4px 2px 12px}
.legend .dot:first-child{margin-left:0}
.legend .today-sample{display:inline-block;width:2px;height:12px;background:var(--fg);opacity:.45;vertical-align:middle;margin:0 4px 2px 12px}
.bar{background:var(--line);border-radius:6px;height:10px;overflow:hidden;display:inline-block;width:70%%;vertical-align:middle}
.fill{background:var(--accent);height:100%%}.pct{margin-left:10px;font-size:.9rem;color:var(--muted)}
.waiting{background:var(--card);border-left:4px solid var(--warn);padding:4px 16px 12px;border-radius:6px;margin-top:24px}
.cols,.grid2{display:grid;grid-template-columns:1fr 1fr;gap:0 32px;align-items:start}
@media (max-width:800px){.cols,.grid2{grid-template-columns:1fr}}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:16px 0 8px}
.kpi{background:var(--card);border-radius:8px;padding:12px 16px}
.kpi .num{font-size:1.7rem;font-weight:700;line-height:1.3}
.kpi .lbl{color:var(--muted);font-size:.85rem}
.kpi .bar{width:100%%;display:block;margin-top:6px}.kpi .pct{display:none}
.health{display:inline-block;padding:2px 14px;border-radius:14px;font-size:.9rem;font-weight:600;color:#fff}
.health-green{background:var(--accent)}.health-amber{background:var(--warn)}.health-red{background:var(--danger)}
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


# ---------- CLI ----------

def main(argv=None):
    ap = argparse.ArgumentParser(description="pm-scaffold 儀表板產生器")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                    help="專案根目錄（預設：repo 根）")
    ap.add_argument("--out", default=None, help="輸出路徑（預設：<root>/docs/index.html）")
    ap.add_argument("--check", action="store_true", help="只驗證資料，不產出")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print("✗ 根目錄不存在：%s" % root, file=sys.stderr)
        return 1

    project, data, errors = load_all(root)
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
