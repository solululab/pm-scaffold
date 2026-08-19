# pm-scaffold 設計規格

日期：2026-08-19｜狀態：待審核

## 一、目標

一個可 clone 的專案管理 scaffold repo，供「AI agent + 人」共同維護客戶交付型專案的狀態。首個使用案例為 WordPress 電商交付案（hollisterco.tw），但設計為通用。

解決四件事：

1. **記錄要做的事與進度**——工項有狀態、負責人、里程碑，可追溯到簽約文件。
2. **卡關顯性化**——被誰卡住（客戶／內部／廠商／其他工項）是必填欄位，可被查詢與催辦。
3. **客戶進度儀表板**——repo 內靜態 HTML，經 GitHub Pages 發布，網址固定；內容經白名單過濾。
4. **業務可靠答**——客戶問題只從 repo 資料回答並附出處，答過的問題沉澱為資產。

### 非目標

- 不是開發用 repo：不放程式碼（工程 repo 另在他處，本 repo 僅登記其路徑）。
- 不是通用 PM 理論框架：不做 OKR、市場分析等文件產生器。
- 不做即時協作服務：真相是 git repo，同步靠 commit/push。

## 二、關鍵決策（已與使用者定案）

| 決策 | 選擇 |
|---|---|
| 資料形式 | 一事一檔 Markdown + YAML frontmatter（方案 A） |
| 存放 | private git repo，團隊共用；scaffold 本身可被 clone 重用 |
| 寫入方式 | 工程師口頭彙報 → AI 依 playbook 更新；選配掃工程 repo commits（草擬後人工確認） |
| 儀表板 | `docs/index.html` → GitHub Pages（自 `/docs` 發布），公開但不公告網址 |
| 儀表板安全 | 白名單輸出硬編碼於產生器；內部欄位在程式層面進不了 HTML |
| 工具相容 | 不綁 Claude Code：`AGENTS.md` 為正本、skills 用 agentskills.io 開放格式放根目錄 `skills/`、核心邏輯在零依賴 Python 腳本 |
| 語言 | 全部繁體中文 |

## 三、Repo 佈局

```
pm-scaffold/
├── README.md               # 人看的：這是什麼、clone 後怎麼啟用、三種角色速查
├── AGENTS.md               # AI 行為總則（正本，工具中立）＋「情境 → playbook」對照表
├── CLAUDE.md               # 一行 stub：@AGENTS.md（Claude Code import 語法）
├── project.yaml            # 專案基本資料（見 §四）
├── work/                   # 工項，一事一檔：WI-001-slug.md
├── decisions/              # 決策紀錄：D-001-slug.md
├── qa/                     # 客戶問答：QA-001-slug.md
├── meetings/               # 彙報／會議紀錄：YYYY-MM-DD-type.md
├── source/                 # 原始文件（規格書、報價單、合約）——唯讀，只進不改
├── docs/                   # GitHub Pages 根目錄
│   ├── index.html          # 儀表板（產生器輸出，禁止手改）
│   └── specs/              # 本設計文件等
├── tools/
│   └── build_dashboard.py  # 零依賴產生器 + schema 驗證器
├── skills/                 # playbook 正本（agentskills.io SKILL.md 格式）
│   ├── pm-init/SKILL.md
│   ├── pm-standup/SKILL.md
│   ├── pm-sync-repo/SKILL.md
│   ├── pm-dashboard/SKILL.md
│   ├── pm-ask/SKILL.md
│   └── pm-review/SKILL.md
└── .claude/skills/         # symlink → ../../skills/<name>（Claude Code 接線）
```

跨工具原則：

- **規則寫在標準處**：`AGENTS.md` 是唯一正本；`CLAUDE.md` 僅 import，不重複內容。
- **skill 即 playbook**：每個 `SKILL.md` 是人可讀的 SOP。不支援 skill 機制的工具，使用者說「照 `skills/pm-standup/SKILL.md` 跑」即可。
- **核心邏輯零 AI 依賴**：儀表板與驗證全在 `build_dashboard.py`，換 agent 不影響輸出。
- README 記載各工具接線方式（Claude Code 用內附 symlink；其他工具 copy 或 symlink）。

## 四、資料模型

### project.yaml

```yaml
name: ""                 # 專案名
client: ""               # 客戶顯示名（會出現在儀表板）
started: 2026-01-01
milestones:
  - id: M1
    title: ""
    due: 2026-01-01
people:                  # 內部名冊（不會出現在儀表板）
  - name: ""
    role: pm | engineer | sales
engineering_repos:       # pm-sync-repo 掃描對象
  - path: ""             # 本機路徑或 remote URL
    last_synced: ""      # commit hash，同步點
dashboard:
  title: ""              # 儀表板抬頭
  url: ""                # GitHub Pages 網址（設定完成後填入）
```

### 工項 `work/WI-###-slug.md`

```markdown
---
id: WI-023
title: PLP 篩選器接原生商品屬性
status: blocked        # todo | doing | blocked | review | done | dropped
owner: 小張
blocked_on: client     # client | internal | vendor | WI-###（status=blocked 時必填）
blocked_note: 客戶尚未提供色票對照表
priority: mvp          # mvp | recommended | nice
milestone: M2
spec_ref: 規格書 §3.2   # 回指 source/ 內文件；無來源者填 "口頭需求" 並連結 decision/qa
client_visible: true
estimate: 3d
updated: 2026-08-19
---

## 說明
（做什麼、驗收條件）

## 進度日誌
- 2026-08-19 小張：篩選 UI 完成，等色票對照表 → 轉 blocked
```

狀態機：`todo → doing → review → done`；任何狀態可轉 `blocked`（必填 `blocked_on`；`blocked_note` 於 `blocked_on: client` 時必填，因其會上儀表板）；轉 `dropped` 必須在日誌註明對應的 `D-###`。

### 決策 `decisions/D-###-slug.md`

frontmatter：`id / date / decided_by / status: decided|superseded / refs:[]`（指向 qa、meetings、source 檔案）。內文結構：背景 → 選項 → 決定 → 重新討論的條件。`superseded` 時 refs 指向取代它的新決策。

### 客戶問答 `qa/QA-###-slug.md`

frontmatter：`id / date / asked_by / channel: email|meeting|line|other / status: answered|pending / refs:[]`。內文結構：客戶問什麼 → 我們答什麼 → 依據（引 source/decisions 具體段落）。

### 會議 `meetings/YYYY-MM-DD-<type>.md`

type：standup｜client｜internal。frontmatter：`date / type / attendees:[]`。內文：摘要 + 本次觸發的工項異動清單（WI-### → 狀態）。

### 共通慣例

- 檔名 `_` 開頭者為範例／草稿，產生器與驗證器跳過。
- id 為目錄內遞增序號，由 playbook 負責取號（取現有最大值 +1）。
- 每次寫入後 commit，訊息格式：`standup: 2026-08-19`｜`wi: WI-023 → blocked`｜`qa: QA-007`｜`decision: D-003`｜`dashboard: rebuild`｜`sync: <repo> @<hash>`。

## 五、Playbooks（skills/）

各 SKILL.md 含 agentskills.io frontmatter（name / description 觸發條件）+ SOP 正文。

| Playbook | 觸發 | 行為要點 |
|---|---|---|
| **pm-init** | clone 後首次啟用 | 問答式填 `project.yaml`；若 `source/` 有規格書／報價單，逐項匯入成工項（確認 id、priority、spec_ref、milestone）；無文件則手動列工項；引導 GitHub Pages 設定（repo Settings → Pages → main `/docs`）；最後問是否刪除範例檔。 |
| **pm-standup** | 工程師報進度 | 聽自然語言 → 比對 `work/` → 逐項覆述確認 → 更新工項 frontmatter + 追加進度日誌 → 產 `meetings/` 紀錄。紀律：只更新聽到的，不腦補；新工作先問「開新工項？」；聽到卡關必問卡在誰；結束提醒跑 pm-dashboard。 |
| **pm-sync-repo** | 「去看工程 repo」 | 讀 `engineering_repos` → `git log <last_synced>..HEAD` → 以關鍵字／WI-id 對應工項 → **草擬**異動清單，人工確認後寫入 → 更新 `last_synced`。對不上的 commits 列出待人工歸類。 |
| **pm-dashboard** | 「更新儀表板」 | `python3 tools/build_dashboard.py --check`（失敗即停，回報錯誤）→ 產出 `docs/index.html` → commit + push → 回報網址。 |
| **pm-ask** | 業務問「客戶問…怎麼回」 | 只從 repo 內容（source/decisions/qa/work）回答，每個論點附出處檔案路徑；查無依據就明說「沒有依據，需開會確認」，不得推測合約內容；回答後問「存成 qa/ 檔？」。 |
| **pm-review** | 每週／「健檢」 | 跑 `--check`；列出：doing 超過 7 天未更新、blocked 超過 5 天（附該催的對象）、pending QA、`docs/index.html` 落後於資料 commit；產出行動清單（不自動改資料）。 |

## 六、儀表板產生器 `tools/build_dashboard.py`

- Python 3 標準庫、零第三方依賴。內建迷你 frontmatter 解析器，僅支援本 spec 的欄位子集（純量、字串、`[a, b]` 行內清單、縮排清單），spec 即格式上限，不接受任意 YAML。
- `--check`：驗證 project.yaml 與全部資料檔——必填欄位、列舉值合法、blocked 必有 blocked_on、`blocked_on: client` 必有 blocked_note、日期格式 `YYYY-MM-DD`、milestone/WI 引用存在、id 不重複。錯誤全部列出後以非零 exit code 結束。
- 預設模式：先跑 check，通過才產出 `docs/index.html`——單檔、CSS/JS 內嵌、繁中、RWD、亮暗色皆可讀。

版面（上而下）：

1. 抬頭：`dashboard.title`、最後更新日期、整體進度（MVP 工項 done 數／總數）
2. 里程碑：每個 milestone 一條進度條 + due 日期
3. **⏳ 待客戶事項**：`blocked_on: client` 項目 + blocked_note（置頂是刻意的——儀表板同時是催辦工具）
4. 進行中／最近完成（done 按 updated 取近 10 筆）兩欄
5. 全部工項表：title / milestone / status，按 milestone 分組摺疊

**白名單輸出（硬編碼）**：HTML 只包含 title、status、milestone（含 due）、blocked_note（僅 `blocked_on: client`）、專案名與更新日。owner、estimate、people、內部 blocked 原因、spec_ref 一律不輸出。僅收錄 `client_visible: true` 的工項。

## 七、驗收標準

1. clone 到全新目錄後，不依賴 repo 外任何檔案即可完整運作（skills、範例、文件皆在內）。
2. 各資料目錄含 `_example-*` 範例檔，`build_dashboard.py` 對範例資料成功產出 index.html，五個區塊齊全。
3. 對故意違規的 fixture（缺 blocked_on、非法 status 等），`--check` 逐條報錯且 exit code 非零。
4. 產出的 HTML 以字串檢查確認不含 owner／estimate／內部 note／`client_visible: false` 項目。
5. `.claude/skills/` symlink 在 Claude Code 中六個 skill 皆可被列出與觸發。
6. README 含三角色速查（工程師怎麼報、業務怎麼問、PM 怎麼維護）與 GitHub Pages＋自訂網域設定步驟。
