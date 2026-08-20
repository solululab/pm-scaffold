# pm-scaffold — AI 協作的專案管理 scaffold

可 clone 重用的客戶交付案管理 repo：Markdown 為真相來源、AI 依 playbook
維護資料、零依賴腳本產出客戶進度儀表板（GitHub Pages）。

## 這裡放什麼、不放什麼

放：工項與進度、卡關、決策、客戶問答、會議紀錄、簽約文件。
不放：程式碼（工程 repo 另在他處，僅於 `project.yaml` 登記路徑）。

## 快速開始

**方式一（推薦）**：GitHub 上按 **Use this template** 建新 repo（記得選 **Private**——
專案 repo 會放客戶資料），clone 下來後：

    python3 tools/test_build_dashboard.py  # 自我檢查（應全部通過）

**方式二**（不經 GitHub template）：

    git clone https://github.com/solululab/pm-scaffold my-project-pm && cd my-project-pm
    rm -rf .git && git init -b main        # 斷開 scaffold 歷史
    python3 tools/test_build_dashboard.py  # 自我檢查（應全部通過）

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

使用者只需要講人話（「我來報進度」「客戶問…」）——路由到正確 playbook
是 AI 的責任（規則在 `AGENTS.md` 的「路由紀律」），選不出來它會用人話反問，
不會要你講檔名。各工具的自動載入入口都已鋪好：

- **Claude Code**：`.claude/skills/` symlink + `CLAUDE.md` → `AGENTS.md`
- **Codex**：原生讀 `AGENTS.md`
- **Gemini CLI**：`GEMINI.md` → `AGENTS.md`
- **Cursor**：`.cursor/rules/pm-scaffold.mdc`（alwaysApply）→ `AGENTS.md`
- **GitHub Copilot**：`.github/copilot-instructions.md` → `AGENTS.md`
- **其他工具**（最後手段）：對 agent 說「先讀 AGENTS.md 再開始」

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
