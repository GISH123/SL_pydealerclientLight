# J20 BAC UAT 現場部署檢查表

日期／操作人：＿＿＿＿　Detector／模型版本：＿＿＿＿　A008 實測 W:H：＿＿＿＿

詳細操作與排查見 [J20 BAC UAT 部署操作手冊](J20_BAC_Deployment_Operator_Guide.md)。開工前由部署負責人確認手冊中的現場 TODO。記錄局號與證據位置，分享畫面前先遮蔽內部連線資訊及憑證資料。

## 1. Poker Crop Tool

- [ ] 在內部開發 GPU 機開啟工具，確認 A008 即時影像持續更新並記下解碼影格 W:H。
- [ ] 依上次確認的最後一版畫法重校六格，分別確認第 5、6 格的補牌位置。**橫牌框盡量畫大一點，實際發牌時讓牌盡量落在框的中央**，並查看裁切預覽。
- [ ] 另存定位 XML 並重開核對。尺寸正確，`card_1` 至 `card_6` 各一筆，座標在畫面範圍內。解析度或構圖有變就重新校準。

## 2. pydealerclient

- [ ] 備份生效中的 `config.xml`、`models/videolist.xml` 與定位 XML，記錄備份位置。
- [ ] 核對 `vid`、`BAC`、A008、實測尺寸、六格 XML、核准的模型端點及版本、Mock Dealer 連線和輸出設定。
- [ ] 確認模型服務可用，啟動開發 Mock Dealer，再啟動 Detector。核對載入日誌有 `count=6`、影像正常，且 Mock Dealer 顯示 `Detector ready (TCP)`。

## 3. 開發 Mock Dealer

- [ ] 選 **BAC Classic (6 slots)**。每局依序執行 **Start → Dispatch 1–6 → Save Result → Stop**，先收齊六格結果再儲存。
- [ ] 各局逐格核對回傳與實際牌面，單獨確認 5、6 都有當局正確結果。
- [ ] 依局號核對最終 CSV 的六個 index、已啟用的存圖及兩端日誌，確認 Stop 已執行。

| 測試局 | 局號 | 1–4 正確 | 5 正確 | 6 正確 | Save／CSV | Stop |
|---|---|---|---|---|---|---|
| 1 | ＿＿＿＿ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 2 | ＿＿＿＿ | ☐ | ☐ | ☐ | ☐ | ☐ |
| 3 | ＿＿＿＿ | ☐ | ☐ | ☐ | ☐ | ☐ |

- [ ] 記錄證據位置及測試結論。若未通過，停止開新局、保留證據，依手冊成套回復並重驗。Mock Dealer UAT 通過後，正式 Dealer 驗收仍須另行簽核。
