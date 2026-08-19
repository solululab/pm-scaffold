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
