---
name: pm-init
description: clone 本 scaffold 後首次啟用專案時使用——建立 project.yaml、匯入規格書／報價單成工項、引導 GitHub Pages 設定。觸發語：「初始化專案」「匯入規格書」。
---

# pm-init — 專案初始化

## 前置
- 確認在 repo 根目錄、`git status` 乾淨。
- 讀 `AGENTS.md`（若尚未讀）。

## 步驟

1. **問答式填 project.yaml**：逐項詢問專案名、客戶名、開始日、里程碑
   （id/標題/目標日）、成員（姓名/角色 pm|engineer|sales）、工程 repo 路徑
   （可為空清單）、儀表板抬頭。一次問一題。全部確認後改寫 `project.yaml`。
2. **匯入既有文件（如有）**：請使用者把規格書／報價單放進 `source/`。
   逐份讀取，將可執行項目逐項向使用者確認：標題、priority（mvp|recommended|nice）、
   milestone、spec_ref（引用文件章節）、client_visible、estimate。
   確認一批後以 `work/WI-###-slug.md` 建檔（id 從 WI-001 遞增），status 一律 todo。
   **不確定的項目寧可略過並列出，不要擅自建檔。**
3. **無文件時**：請使用者口述工項清單，同上逐項確認建檔。
4. **驗證**：`python3 tools/build_dashboard.py --check` 須通過。
5. **首次產出儀表板**：`python3 tools/build_dashboard.py`，commit。
6. **GitHub Pages 引導**（人工步驟，念給使用者）：
   - push 到 GitHub private repo（Pages 需 Pro/Team 方案）
   - repo Settings → Pages → Source: Deploy from a branch → main、`/docs`
   - 自訂網域：DNS 加 CNAME 指向 `<帳號>.github.io`，再於 Pages 設定填網域
   - 取得網址後填回 `project.yaml` 的 `dashboard.url`
   - 提醒：頁面「公開但不公告網址」，白名單已過濾內部資訊
7. **收尾**：問「要刪除各目錄的 `_example` 範例檔嗎？」（建議留著當 schema 文件）。
   commit：`chore: pm-init 完成`。
