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
   - remote URL：淺層 clone 到暫存目錄（`git clone --filter=blob:none <url> <tmp>`）
     後同上處理，用完刪除；無法 clone 就回報並請使用者改提供本機路徑。
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
