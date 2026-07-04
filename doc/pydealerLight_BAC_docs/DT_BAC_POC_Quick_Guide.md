# BAC POC 蹇€熸寚鍗?

## 1. 閫傜敤鑼冨洿

鏈寚鍗楄鏄庡綋鍓?BAC POC 鐨勫疄鐜颁笌鎿嶄綔鏂瑰紡锛屼富瑕佺敱浠ヤ笅閮ㄥ垎缁勬垚锛?

- `mock_dealer_app_BAC`锛堝惎鍔ㄥ櫒 + BAC / DT GUI锛?
- `pydealerLight`锛圔AC / BALL3 / BJ21 鍏辩敤鎺ㄨ绔級
- 閫氳繃 `engine_api_url` 瀵规帴鐨勫閮ㄦā鍨嬪紩鎿?

褰撳墠鎺ㄨ崘婕旂ず璺緞濡備笅锛?

1. 妯℃嫙鑽峰畼閫氳繃 **HTTP** 鎺у埗涓€灞€寮€濮嬨€佹淳鐗岀储寮曘€佷繚瀛樼粨鏋滀笌鍋滄
2. `pydealerLight` 璐熻矗浠庤棰戞祦瑁佸垏 ROI锛屽苟鎶婃瘡涓?**active index** 鐨?PNG 鍥鹃€佸埌澶栭儴妯″瀷寮曟搸
3. `pydealerLight` 鍐嶉€氳繃鏃㈡湁鐨?**TCP socket 鍗忚** 鎴?**HTTP request 鍗忚**锛屾妸 `idx + dealer_classid + score` 鍥炰紶缁欐ā鎷熻嵎瀹?
4. BAC 鐨勬渶缁?CSV 寤鸿閫氳繃 **Save Result** 涓诲姩鍐欏嚭锛沗STOP` 鍙綔涓?**缁撴潫褰撳墠鐗屽眬**

---

## 2. 绯荤粺鎬昏

### Mock Dealer BAC

涓昏鑱岃矗锛?

- 鎻愪緵鍚姩椤碉紝鍙€?**TCP / HTTP / Both** 鎺у埗妯″紡 涓?  **DVR** 寮€鍏?
- 鎻愪緵鍚姩椤碉紝鍙€?**DT (3 slots)** 鎴?**BAC Classic (6 slots)** 
- 涓荤晫闈㈡彁渚?鎵嬪姩)锛?
  - `Start New Round && Prediction`
  - `Dispatch index`
  - `Save Result`
  - `Stop Prediction`
- 閫氳繃 HTTP POST 鎴栨棫鐗?TCP 浜岃繘鍒跺崗璁帶鍒舵娴嬬
- 閫氳繃 TCP 鎺ユ敹鎺ㄨ缁撴灉骞舵洿鏂扮墝闈?UI

### pydealerLight

涓昏鑱岃矗锛?

- 璇诲彇 `config.xml` 鎸囧畾鐨?`vid`
- 浠?`models/videolist.xml` 閫夊嚭瀵瑰簲瑙嗛婧?/ position file / engine_api_url
- 閫氳繃 TCP/HTTP 鏈嶅姟鎺ユ敹锛?
  - `/start_predict`
  - `/dispatch_index`
  - `/save_result`
  - `/stop_predict`
- 瀵?active index 鍋?ROI 瑁佸垏锛屽苟閫佸埌妯″瀷寮曟搸
- 鎶婄鍚堥棬妲涚殑缁撴灉杞垚 PH_BAC dealer class id 鍚庡洖浼犵粰 mock dealer

### 澶栭儴妯″瀷寮曟搸

涓昏鑱岃矗锛?

- 閫氳繃 `engine_api_url` 鎺ユ敹鍗曞紶 ROI PNG
- 杩斿洖 `nClass / nScore / onebox / group_text`
- 鐢?`pydealerLight` 瀹屾垚淇″績鍊艰繃婊ゃ€佺被鍒槧灏勩€佺粨鏋滅紦瀛樹笌鍥炰紶

---

### 3锛夊綋鍓嶄笂浼犻厤缃笌 BAC Classic 6-slot 涔嬮棿鏈変竴涓敞鎰忕偣

褰撳墠涓婁紶鐨?`config.xml` 浣跨敤锛?

```xml
<common vid="DTBAC_httpapi" ... />
```

鑰?`videolist.xml` 涓繖涓?profile 瀵瑰簲锛?

- `gametype="BAC"`
- `position_file="models/DT_livestream_20260406.xml"`

杩欎釜 position file **鐩墠鍙湁 3 涓?ROI object**銆?

涔熷氨鏄锛?

- **Mock Dealer 鍚姩鍣ㄥ凡缁忔敮鎸?BAC Classic 6 slots**
- 浣?**褰撳墠榛樿 pydealerLight 閰嶇疆浠嶅亸鍚?3-slot / DTBAC profile**

---

## 3. 鍗曞眬娴佺▼涓庢搷浣滈『搴?

鎺ㄨ崘鍚姩椤哄簭锛?

**model engine 鈫?mock dealer 鈫?pydealerLight**

瀹屾暣娴佺▼濡備笅锛?

### 1锛夐厤缃‘璁?

纭锛?

- `config.xml`
- `models/videolist.xml`
- 褰撳墠 `vid`
- `position_file`
- `engine_api_url`
- HTTP 绔彛涓?dealer TCP 绔彛

### 2锛夊惎鍔ㄦā鍨嬪紩鎿?

妯″瀷寮曟搸蹇呴』鍏堝惎鍔紝骞剁洃鍚?`countsPredict` URL锛堜緥濡?`8787` 鎴?`5000`锛夈€?

### 3锛夊惎鍔?Mock Dealer BAC

鐒跺悗鍦ㄥ惎鍔ㄩ〉閫夋嫨锛?

- Control mode锛氬缓璁?`HTTP` 鎴?`Both`
- Game mode锛氫緷褰曞埗鐩爣閫夋嫨 `DT (3 slots)` 鎴?`BAC Classic (6 slots)`
- DVR锛氭寜闇€瑕佸紑鍚?

### 4锛夊惎鍔?pydealerLight

瀹冧細锛?

- 鍚姩瑙嗛閲囨牱
- 鍚姩 HTTP / HTTPS 鎺у埗鏈嶅姟
- 杩炴帴 mock dealer 鐨?TCP listener

### 5锛夋墜鍔ㄥ紑濮嬩竴灞€

鍦?mock dealer 鐐瑰嚮锛?

- `Start New Round && Prediction`

杩欎竴姝ヤ細锛?

- 鐢熸垚 gmcode
- 鍙戦€?`start_predict`
- 璁╂帹璁虹杩涘叆褰撳墠 round

### 6锛夋淳閫佺储寮曞苟绛夊緟缁撴灉

鎺ョ潃锛?

- 鎵嬪姩鐐?`Dispatch 1~6`
- 鎴栦娇鐢?`Dispatch All`

`pydealerLight` 浼氬 active index 鐨?ROI 鍋氭帹璁猴紝杈惧埌 `detecttimes` 鍚庯紝鎶婄粨鏋滃洖浼?UI銆?

### 7锛変繚瀛樹笌鍋滄

鎺ㄨ崘椤哄簭锛?

1. `Save Result`
2. `Stop Prediction`

杩欐牱鏈€鎺ヨ繎褰撳墠 BAC 浠ｇ爜鐨勮璁￠鏈熴€?

---

## 4. 鍏抽敭閰嶇疆鏂囦欢

### `config.xml`锝滄帹璁虹鍏ㄥ眬璁剧疆锛堝綋鍓嶄笂浼犵増鏈級

```xml
<common vid="DTBAC_httpapi" freq="5" onelabel="1" detecttimes="3"
        saveimagescore="0.85" redispatch_reset_cooldown_s="1.0"
        live_stall_timeout_s="10.0" live_reopen_cooldown_s="3.0" />
<dealer id="1001" host="127.0.0.1" port="2331" />
<save folder="./_round_end_imgs" autoUpload="1" />
<savePredictImage folder="./predict_images" enable="1" />
<http port="1234" https_port="1235" />
```

璇存槑锛?

- `detecttimes="3"`锛氬悓 index 缁撴灉绱杈?3 娆″悗鎵嶄細 dispatch
- `saveimagescore="0.85"`锛氫綆浜庨槇鍊肩殑 BAC 缁撴灉浼氳蹇界暐
- `http port="1234"`锛歮ock dealer 榛樿涔熶細鎵撳埌杩欎釜绔彛

### `models/videolist.xml`锝滃綋鍓嶉€夌敤 DT 瑙嗛婧?

褰撳墠閰嶇疆瀹為檯閫変腑鐨勬槸锛?

```xml
<video
    vid="DTBAC_httpapi"
    gametype="BAC"
    stream="rtmp://STREAM_HOST/app/stream"
    width="1920" height="1080"
    position_file="models/DT_livestream_20260406.xml"
    engine_api_url="http://127.0.0.1:8787/countsPredict"
    skip_freq_live="5"
/>
```

### mock dealer `.env` 榛樿鍊?

```text
HTTP_BASE_URL=http://127.0.0.1:1234
HTTP_TABLE=B004
HTTP_DEVICE_ID=obs
HTTP_STREAM_ID=OBS233jk
LOGIN_VID=B004
LOGIN_GMTYPE=BAC
```

---

## 5. BAC 鎺у埗 API

浠ヤ笅绀轰緥宸插榻?`BAC_HTTP_TEST.postman_collection.json` 褰撳墠鍙傛暟璁剧疆銆?

Postman 榛樿鍙橀噺锛?

```text
base_url = http://127.0.0.1:1234
gmcode   = BAC_HTTP_TEST_001
```

### START锝淧OST `/start_predict`

```http
POST http://127.0.0.1:1234/start_predict?gmcode=BAC_HTTP_TEST_001&gmstate=2
Content-Type: application/json
```

```json
{
  "gmcode": "BAC_HTTP_TEST_001",
  "gmstate": 2
}
```

> 娉ㄦ剰锛氬綋鍓?BAC 瀹炵幇鐨?Start 浣跨敤 `gmstate = 2`锛屼笉鏄?BALL3 鏂囨。閲岀殑 `1`銆?

### DISPATCH锝淧OST `/dispatch_index`

浠ヤ笅涓?Postman 涓?`dispatch_index 1` 鐨勭ず渚嬶紱`dispatch_index 2 / 3` 浠呴渶鏀?`index` 鍊笺€?

```http
POST http://127.0.0.1:1234/dispatch_index?gmcode=BAC_HTTP_TEST_001&gmstate=0&index=1
Content-Type: application/json
```

```json
{
  "gmcode": "BAC_HTTP_TEST_001",
  "gmstate": 0,
  "index": 1
}
```

### SAVE锝淧OST `/save_result`

```http
POST http://127.0.0.1:1234/save_result?gmcode=BAC_HTTP_TEST_001&gmstate=0
Content-Type: application/json
```

```json
{
  "gmcode": "BAC_HTTP_TEST_001",
  "gmstate": 0
}
```

### STOP锝淧OST `/stop_predict`

```http
POST http://127.0.0.1:1234/stop_predict?gmcode=BAC_HTTP_TEST_001&gmstate=0
Content-Type: application/json
```

```json
{
  "gmcode": "BAC_HTTP_TEST_001",
  "gmstate": 0
}
```

### GET 鐗堟湰锛堜笌 Postman collection 瀵归綈锛?

```http
GET http://127.0.0.1:1234/start_predict?gmcode=BAC_HTTP_TEST_001&gmstate=2
GET http://127.0.0.1:1234/dispatch_index?gmcode=BAC_HTTP_TEST_001&gmstate=0&index=1
GET http://127.0.0.1:1234/save_result?gmcode=BAC_HTTP_TEST_001&gmstate=0
GET http://127.0.0.1:1234/stop_predict?gmcode=BAC_HTTP_TEST_001&gmstate=0
```

### pydealerLight 鏀跺埌鍚庝細鍋氫粈涔?

- **On Start Predict**锛氳褰曞綋鍓?gmcode锛屽紑鍚?BAC 棰勬祴鐘舵€?
- **On Dispatch Index**锛氭妸璇?index 鍔犲叆 active list锛屽苟寮€濮嬪璇?ROI 鎺ㄨ
- **On Save Result**锛氭妸缂撳瓨鐨?BAC final rows 钀藉埌 CSV
- **On Stop Predict**锛氬叧闂?predictFlag锛涜嫢杩樻湁 pending final rows锛屽垯鍋?fallback SaveFinalResult
- 鑻ョ己灏?`gmcode`锛孒TTP 鏈嶅姟杩斿洖 `400`
- 褰撳墠 Postman collection 鍚屾椂鎻愪緵 **POST JSON** 涓?**GET query** 涓ょ璋冪敤鏂瑰紡

## 6. 杈撳嚭銆佸懡鍚嶄笌楠岃瘉閲嶇偣

### 鐩綍缁撴瀯

```text
./csv/YYYY-MM-DD/finalresult_YYYYMMDD.csv
./csv/YYYY-MM-DD/<session_start>.csv
./predict_images/YYYY-MM-DD/
./_round_end_imgs/
./log/YYYY-MM-DD/YYYYMMDDHH.log
./logs/BAC_HTTP_YYYYMMDD_HHMMSS.log   (mock dealer)
```

### BAC CSV 琛ㄥご

褰撳墠 BAC 浣跨敤 legacy header锛?

```text
game,idx,class_dealer,class_model,score,card_number,endid
```

璇存槑锛?

- `game` = gmcode
- `idx` = 鐗屼綅 index
- `class_dealer` = 鏄犲皠鍚庣殑 PH_BAC dealer class id
- `class_model` = engine 鍘熷 class id
- `score` = 妯″瀷淇″績鍊?
- `card_number` = rank 1~13

### BAC 鍥剧墖淇濆瓨閫昏緫

- `predict_images/YYYY-MM-DD/`
  - 淇濆瓨 **姣忎釜琚帴鍙楃粨鏋滅殑 ROI 灏忓浘**
  - 鏂囦欢鍚嶄細甯︼細`gmcode / index / dealer_classid / suit / rank / predict_classid / score`
- `_round_end_imgs/`
  - 褰撳墠 BAC 閫昏緫涓紝褰撴娴嬪埌鏈夋晥缁撴灉涓斿紑鍚?`save_full_image` 鏃讹紝浼氫繚瀛樺甫 gmcode 鐨勫叏鍥捐瘉鎹?

### 鏈€灏忛獙鏀舵竻鍗?

- mock dealer 鎴愬姛鏄剧ず `Detector ready (TCP)`
- 鐐瑰嚮 Start 鍚?gmcode 姝ｅ父鐢熸垚
- 鑷冲皯涓€涓?dispatch index 杩斿洖鐗岄潰缁撴灉
- `Save Result` 鍚?CSV 涓嚭鐜拌 gmcode 鐨勬渶缁堣祫鏂?
- `predict_images` 鏈夊搴?ROI 灏忓浘
- `_round_end_imgs` 鏈夊搴斿叏鍥捐瘉鎹紙鑻ュ惎鐢ㄤ繚瀛橈級
- log 涓棤鎸佺画鎬?HTTP / engine / TCP error

---

## 7. 鎺ㄨ崘鎿嶄綔娴佺▼锛圫OP锛?

### A锝滃噯澶?

1. 鍏堝惎鍔ㄦā鍨嬪紩鎿?
2. 鍚姩 `pydealerLight`
3. 鍚姩 `mock_dealer_app_BAC`
4. 鍦ㄥ惎鍔ㄩ〉閫夋嫨锛?
   - 寤鸿 `HTTP` 鎴?`Both`
   - 褰?BAC Classic 鏃堕€?`BAC Classic (6 slots)`
5. 纭鐣岄潰鍑虹幇 `Detector ready (TCP)`

### B锝滄墽琛屼竴灞€

1. 鐐瑰嚮 **Start New Round && Prediction**
2. 渚濈墝浣嶉『搴忕偣鍑?**Dispatch 1 ~ Dispatch N**锛屾垨浣跨敤 **Dispatch All**
3. 绛夊緟姣忎釜 index 鍒拌揪 `detecttimes`
4. 瑙傚療 UI 鍗＄墝涓?event log 鏄惁鍚屾鏇存柊

### C锝滄敹灏句笌楠岃瘉

1. 鐐瑰嚮 **Save Result**
2. 鍐嶇偣鍑?**Stop Prediction**
3. 鎵撳紑 `csv / predict_images / _round_end_imgs / log / logs`
4. 淇濈暀 CSV 涓庡浘鍍忚瘉鎹紝渚?QA / 婕旂ず / 闂杩芥煡浣跨敤

---

## 8. 鎺掗敊寤鸿

### HTTP 404 / 鎺у埗澶辫触

鏈€甯歌鍘熷洜鏄鍙ｄ笉涓€鑷淬€傝纭锛?

- mock dealer `.env` 鐨?`HTTP_BASE_URL`
- `pydealerLight/config.xml` 鐨?`<http port="1234" https_port="1235" />`

### 鍙湁 3 涓綅缃湁鏁堬紝涓嶆槸 6 涓?

璇锋鏌ュ綋鍓?`vid` 鏄惁浠嶄负锛?

```xml
<common vid="DTBAC_httpapi" />
```

鑻ユ槸锛屽垯褰撳墠 position file 浠嶄负 `DT_livestream_20260406.xml`锛屽彧鏈?3 涓?ROI銆?

### 娌℃湁 mock dealer 杩炴帴

纭锛?

- pydealerLight 鐨?dealer host / port 鎸囧悜 `127.0.0.1:2331`
- mock dealer 宸插厛鎵撳紑 TCP listener
- 鍗充娇浣犳墦绠楃敤 HTTP 鎺у埗锛屽綋鍓嶅疄鐜颁粛闇€瑕?TCP login / result return

### 娌℃湁棰勬祴缁撴灉

璇锋鏌ワ細

- `engine_api_url` 鏄惁姝ｇ‘
- 妯″瀷寮曟搸鏄惁宸插惎鍔?
- position file 鐨?ROI 鏄惁瀵瑰噯鐗屼綅
- `saveimagescore=0.85` 鏄惁杩囬珮
- 褰撳墠 index 鏄惁鐪熺殑宸茶 dispatch

### Save Result 鍚?CSV 浠嶄负绌?

璇风‘璁わ細

- 鏄惁宸叉湁鑷冲皯涓€涓?index 杈惧埌 `detecttimes`
- 鏄惁鍦ㄥ悓涓€ gmcode 涓嬫搷浣?
- 鑻?Save Result 澶棭锛屽彲鑳藉皻鏈舰鎴?final rows

### STOP 鍚庢墠鏈?CSV

杩欐槸褰撳墠浠ｇ爜鍏佽鐨?fallback 琛屼负锛?

- BAC 棣栭€?**Save Result** 鍐欏嚭
- 鑻?pending final rows 杩樺湪锛宍STOP` 涔熶細琛ュ仛涓€娆?`SaveFinalResult`

---

