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

## 路由紀律（給 AI，不是給使用者）

- 觸發語**不限於表列**，使用者只會講人話。同義說法自行歸類，例：
  「進度到哪了」「幫我看一下專案狀況」→ pm-review；「小張說首頁做完了」
  → pm-standup；「客戶剛來信問……」「這個合約有包嗎」→ pm-ask；
  「工程師有推新的 code 嗎」→ pm-sync-repo。
- 凡涉及專案資料（work/、decisions/、qa/、meetings/、project.yaml、儀表板）
  的請求：**先選定一個 playbook、完整讀取後才動作**。
- 判斷不了就用人話問使用者二選一（例：「你是要報進度，還是要我幫你
  回客戶的問題？」）。**絕不要求使用者說出 skill 名稱或檔案路徑。**
- 不支援 skill 機制的工具：本節連同上表就是你的路由器——照著讀對應的
  SKILL.md 執行即可。

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
8. **工項轉 dropped 前必須先有對應的 `decisions/D-###`**，並在進度日誌註明。

## 資料模型速查

- `project.yaml`：專案名、客戶、里程碑、成員、工程 repo、儀表板設定
- `work/WI-###-slug.md`：工項。status: todo|doing|blocked|review|done|dropped
- `decisions/D-###-slug.md`：決策（背景→選項→決定→重新討論條件）
- `qa/QA-###-slug.md`：客戶問答（問→答→依據）
- `meetings/YYYY-MM-DD-type.md`：彙報／會議紀錄
- 檔名 `_` 開頭＝範例，工具跳過。id 取號＝目錄內現有最大值 +1。
- 完整欄位定義見各目錄 `_example` 檔與 `docs/specs/`。
- frontmatter 值若含「 #」或以 # 開頭（色碼、編號），必須用引號包住。

## 客戶儀表板白名單（背景知識）

`docs/index.html` 只會包含：title、status、milestone、due（工項截止日，
選填；逾期未完成會標示）、side 的負責方 label（選填 vendor|client|both，
顯示文字設定在 dashboard.side_labels，**owner 人名不會上儀表板**）、
blocked_note（僅 blocked_on=client）、健康度燈號（dashboard.health，
**只能由使用者拍板**，AI 不得自動設定或變更）、
專案名與更新日。owner、estimate、
內部備註在產生器層就被排除——但你寫 blocked_note（client）時仍須意識到
**它會被客戶看到**，措辭要對外得體。

注意：GitHub Pages 公開的是 **`docs/` 整個目錄**（含 specs/、plans/），
不只 index.html——內部或客戶敏感文件一律不放 `docs/`。
