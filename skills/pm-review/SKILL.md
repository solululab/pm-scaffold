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
