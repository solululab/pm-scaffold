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
