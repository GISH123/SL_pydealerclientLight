# J20 BAC UAT 部署操作手冊

本手冊適用於 J20 的 A008 即時影像、六牌位 ROI 校準，以及開發版 Mock Dealer 的端到端驗證。現場請使用內部開發 GPU 機與核准的 UAT 環境。文中標示 **TODO** 的項目須由部署負責人確認。連線資訊從核准的內部管道取得，測試紀錄與截圖對外分享前須遮蔽連線資訊及憑證資料。

現場可搭配 [J20 BAC UAT 部署檢查表](J20_BAC_Deployment_Checklist.md) 使用。

## 第一階段｜Poker Crop Tool 校準六個牌位

1. 在內部開發 GPU 機開啟 Poker Crop Tool，使用核准的來源連接 **A008 即時串流**。確認影像持續更新、桌面與牌位可辨識。**TODO** 確認工具版本、啟動方式、連線與匯出操作畫面。
2. 從工具的來源資訊確認實際解碼影格的寬與高，記錄 **W:H**。若工具只顯示預覽視窗大小，請以現場核准的方式讀取來源影格尺寸。**TODO** 補上 A008 實測 W:H 與讀取位置。
3. 依 J20 牌位對照逐一重畫 ROI 1–6。以實際出牌位置核對每個框，尤其分別確認第 5、6 格的補牌位置。框線須涵蓋牌面辨識區域，避免截斷牌面、裁到相鄰牌或框出影格範圍。**TODO** 以現場畫面確認 J20 六格對照及畫面方向。
4. 將定位 XML 匯出為新檔，保留原檔。重新開啟匯出的檔案，確認疊框仍對準同一 A008 影像。檢查 XML 有六筆 `object`，名稱 `card_1` 至 `card_6` 各出現一次，`size` 的寬高對應實測 W:H，每筆 `bndbox` 都有合法的 `xmin`、`ymin`、`xmax`、`ymax`，且 `0 ≤ xmin < xmax ≤ W`、`0 ≤ ymin < ymax ≤ H`。比對 [既有六格定位 XML](../../models/20260427_test.xml) 的結構即可，J20 座標以此次校準結果為準。
5. 串流解析度、畫面方向、裁切範圍或鏡位變更時，暫停驗證，重新確認來源並校準六格。將新定位 XML 和 `models/videolist.xml` 的 `width`、`height` 一併更新，再重做三階段驗證。單靠等比例縮放座標無法確認牌位仍與目前畫面吻合。

> 截圖預留｜A008 實測 W:H、六格疊框（標清楚 5、6）及定位 XML 匯出畫面。TODO 從部署示範影片擷取。

## 第二階段｜設定 pydealerclient 並確認就緒

1. 記錄目前版本與執行目錄。變更前備份生效中的 `config.xml`、`models/videolist.xml` 與現用定位 XML，標記時間與版本，並保存在核准的內部位置。備份可能包含內部連線資訊，請依現場規範保存。
2. 使用下列欄位對照核准的 J20 UAT 設定。可參考 [主設定範例](../../config.example.xml) 和 [影片清單範例](../../models/videolist.example.xml) 的 XML 結構。

   | 檔案與欄位 | J20 應核對的內容 |
   |---|---|
   | `config.xml` 的 `common/@vid` | 選定的 J20 UAT 設定檔識別字，與影片清單中的一筆 `video/@vid` 完全相同。**TODO** 確認識別字。 |
   | `models/videolist.xml` 的 `video` | `gametype` 使用 `BAC`。 `stream` 指向 A008。 `width`、`height` 填實測尺寸。 `position_file` 指向新校準的六格 XML，並從程式執行目錄確認路徑可讀。 |
   | 同一筆 `video` 的 `engine_api_url` | 填入 J20 核准的外部辨識模型端點。**TODO** 確認模型版本、內部設定來源及核對方式。 |
   | `config.xml` 的 `dealer`、`http` | Detector 的 TCP 目標須與開發 Mock Dealer 的監聽設定對應。Mock Dealer 的 HTTP 控制目標須與 Detector 的 HTTP 設定對應。**TODO** 確認現場控制模式與連線設定。 |
   | `common`、`bacPreprocess`、`savePredictImage`、`save` | 核對 `detecttimes`、信心門檻 `saveimagescore`、取樣頻率、模型輸入前處理與輸出目錄。確認目錄可寫。**TODO** 確認 J20 的核准參數與需留存的影像類型。 |

3. 先確認辨識模型服務可用，再啟動開發 Mock Dealer 等待 TCP 連線，接著從正確的執行目錄啟動 Detector。**TODO** 補上 J20 核准的發行版本、安裝位置、實際啟停步驟、模型健康檢查方式及預期回應。
4. 檢查 Detector 日誌的 `[RUNTIME CONFIG]`、`read_video_list` 與 `read_position success`。核對選用的 `vid`、`BAC`、A008、W:H、定位檔路徑和 `count=6`，確認沒有影格尺寸不符的訊息。核對程式使用的模型端點與部署負責人確認的服務版本，並在第三階段用實際 Dispatch 確認有有效辨識回應。
5. 確認開發 Mock Dealer 顯示 `Detector ready (TCP)`，並確認 Detector 影像持續更新。若使用 HTTP 控制，TCP 仍用於登入與辨識結果回傳。控制指令收到成功回應後，還須繼續核對實際牌面及落檔紀錄。

> 截圖預留｜已遮蔽的設定欄位、六格定位載入紀錄與 Detector ready 畫面。TODO 從部署示範影片擷取。

## 第三階段｜用開發 Mock Dealer 跑完約三局

啟動**開發版 Mock Dealer**，選擇 **BAC Classic (6 slots)**，確認畫面有 1–6 格，並依核准方式設定控制模式。選擇可測到六格的 UAT 牌局，安排第 5、6 格都出現可辨識的測試牌。每局使用獨立局號 `gmcode`，依下列順序操作。

1. 按 **Start New Round && Prediction**，記錄局號，核對 Detector 的 `onStartPredict`。若透過 HTTP 追查，BAC 文件記載的 Start `gmstate` 為 `2`。
2. 依測試牌位逐一按 **Dispatch 1–6**。等當前格已有有效牌面回傳，再送下一格。每格比對實際牌面、UI index 和回傳結果。特別記錄第 5、6 格各自收到的牌面，確認兩格沒有互換、漏回或沿用前一局的結果。若要改用 **BAC_Auto Dispatch**，先確認設定順序包含全部六格，並在事件日誌核對 Save、Stop 的實際順序。
3. 六格都取得有效結果後按 **Save Result**。核對 Detector 的 `SaveFinalResult` 寫入紀錄，以及該局的最終 CSV。若未寫入，保留局號與日誌供排查。
4. 按 **Stop Prediction**，在兩端日誌確認同局停止，再開始下一局。若只看到 Stop 的補寫紀錄，請記為 Save Result 驗證未通過。

### 證據與驗收

| 核對項目 | 通過條件 |
|---|---|
| 串流與定位 | A008 持續更新，實測 W:H 與設定一致，六格 XML 載入成功且疊框對位。 |
| 控制與回傳 | 約三局各有完整的 Start → Dispatch → Save Result → Stop 紀錄。每局 index 1–6 各有對應的有效牌面，5、6 均獨立核對。 |
| CSV | 在 `csv/YYYY-MM-DD/finalresult_YYYYMMDD.csv` 依 `game`（局號）與 `idx` 核對六格。比對 `class_dealer`、`class_model`、`score`、`card_number` 與日誌及實際牌面。 |
| 影像與日誌 | 若啟用 ROI 存圖，核對設定的輸出目錄（範例為 `predict_images/YYYY-MM-DD/`）下的同局、同 index 影像。原始裁圖 `original_crop/` 與整張影格僅在對應選項啟用時確認。保留兩端日誌，確認未持續出現串流、模型或 TCP 錯誤。 |

每局記下局號、六格預期與實際牌面、Save/Stop 結果，以及 CSV、影像和日誌的證據位置。若某格未出現可驗證的牌面，記為該格未驗證，補跑可覆蓋六格的完整測試局。

開發 Mock Dealer 驗證涵蓋 UAT 的控制、實際辨識、TCP 回傳與落檔。正式驗收須另依核准流程，使用正式 Dealer、正式服務設定與實際桌務流程重驗，並由授權人員簽核。**TODO** 確認正式驗收的責任人、核准流程及簽核條件。

> 截圖預留｜六格 Mock Dealer 畫面、第 5／6 格回傳事件、同局 CSV 與 ROI 存圖。TODO 從部署示範影片擷取。

## 故障排查

| 現象 | 優先檢查 |
|---|---|
| 無影像、畫面停住或回報寬高不符 | 確認來源為 A008，重新量測解碼影格 W:H，檢查所選 `vid` 的寬高設定及串流可用性。若尺寸或畫面構圖已變，回第一階段。 |
| 只有三格，或 index 5／6 缺失、對調 | 檢查 Mock Dealer 是否為 BAC Classic、Detector 載入是否為 `BAC` 及 `count=6`、XML 名稱與座標是否正確，以及該局是否確實 Dispatch 及出牌。 |
| 無法就緒或控制失敗 | 分別核對 Mock Dealer 的 TCP 監聽與 Detector 的登入日誌，以及 HTTP 控制目標、服務狀態與所選控制模式。 |
| Dispatch 成功但無牌面回傳 | 依同一局號和 index 查 ROI 是否對位、模型端點是否正常回應、結果是否通過門檻並累積至 `detecttimes`，再查 TCP 回傳。 |
| CSV 無當局資料或找不到影像 | 查 Save 是否在有效回傳後執行、局號是否一致、Detector 是否寫入成功及目錄是否可寫。影像另確認已啟用所需存圖選項。 |

## 回復與交接

1. 發現牌位錯置、設定載入有誤或結果異常時，暫停開新局。透過開發 Mock Dealer 結束當前測試局，保留異常局號、設定版本與證據，再按核准流程停止 Detector。
2. 一併還原同一備份版本的 `config.xml`、`models/videolist.xml` 和定位 XML。若測試期間更換了模型服務版本，請與部署負責人確認核准的回復方式。不要覆蓋故障證據。
3. 重啟後核對已還原的來源、W:H、定位檔與 TCP 就緒狀態。若現有 A008 影格已與舊定位不相容，先暫停測試並重新校準。回復後先跑一局確認流程，J20 驗收仍須完成上列三局驗證。

## 參考資料

- [BAC POC 快速指南](../pydealerLight_BAC_docs/DT_BAC_POC_Quick_Guide.md)
- [Mock Dealer 使用手冊](../pydealerLight_BAC_docs/MockDealerBAC_User_Manual.html)
- [BAC／DT POC 使用與示範簡報](../pydealerLight_BAC_docs/DT_BAC_POC_使用手册与演示.pptx)
- [專案 README 的執行設定](../../README.md#runtime-configuration)
