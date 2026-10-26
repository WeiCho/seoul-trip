# 首爾旅程手冊

2026-11-04～11-09，3 人，住建大入口站旁 Airbnb（`서울 광진구 동일로18길 69`）。
線上：<https://weicho.github.io/seoul-trip/>（**public repo**）。使用者常從手機 Claude App 下指令，回覆用繁體中文、簡短。

## 流程

1. 開工先 `git pull`（`forecast.yml` 每天兩次會 push 天氣進 `trip.json`）。
2. 只改 `trip.json`（唯一的資料來源；`E:/Projects/travel-planner/trips/首爾/` 已不用）。要動樣板才碰 `template/`、`render.py`，樣板以本 repo 為準。
3. 驗證：`pip install "jinja2>=3.1"`，`python render.py .`，沒有錯誤、看一下「⚠ 排太緊」警告並回報。產出的 `行程表.html`、`index.html` 等在 `.gitignore`，不要 commit。
4. **改完就 commit & push，不用問。** push 被拒就 `git pull --rebase` 再推；`days[].forecast`／`forecast_extra` 是 Actions 寫的，不要手改或蓋掉。
5. push 後 `deploy.yml` 自動渲染部署，約 1–2 分鐘上線。回報時說改了哪一天、哪幾站。

## 資料規則

- **不寫訂位代號、保單號、護照號碼等個資**（repo 是 public）。
- 每天 `theme` 只寫地區，例「南怡島・聖水」，不寫長串店名。
- 每天第一站是住宿（type「住宿」、「從 Airbnb 出發」），最後一站「回 Airbnb」；抵達日第一站是機場，回國日以航班結束。
  出發時間 = 第一個行程時間 − 交通分鐘 − 20 分緩衝 − 5 分，往下取整到 5 分。
- `transit[].at` 是「從哪一站出發」的時間，不是目的地。改了站的時間，要一起檢查前後的 transit `at` 與 `next_transit`。
- 同一區（地鐵 3 站內、走得到）的店合成一站「○○自由逛」，店家放 `items[].shops`（店名＋一行位置・營業＋naver_query）；離 4 站以上才拆站並加交通卡。餐廳、要預約的、看日落等有時間點的才獨立成站。
- 一天景點／購物別超過 3 個（render.py 會警告）。
- 每站要有 `naver_query`（韓文，用來開 Naver Map 的綠色 N）；航班、搭車中、台灣機場不放。
- 彈窗只放 1–2 句 `note`、停留 `duration`、營業 `booking.hours`、下一站 `next_transit`；不加官網或其他連結、不加「可捨棄」。
- 重要景點與餐廳加 `photo`（img／alt／credit）：用該店本身在 Google 地圖上好看的照片，熱連結 `https://lh3.googleusercontent.com/<id>=w900-k-no-rw`，credit 寫「圖：拍攝者／Google 地圖（年/月）」；不要通用示意圖。找不到就先不放，回報缺圖。
- 交通 `options[].steps` 每一步一句話，盡量配真實照片（`img` 存 `img/`，或熱連結）；Kakao 로드뷰、Wikimedia Commons（要標作者與授權到 `credit`）。都找不到才用 `sign` 畫仿地鐵指標牌，並回報哪步缺圖。
- 口袋名單 `wishlist`：一家店一筆，同品牌分店合併；不放 IG 來源連結。購買清單 `shopping[]`：name 中文、ko 韓文、img、where／where_ko。

## 設計

看 `DESIGN.md`：字不要大、畫面乾淨、iPhone 優先；「刻意拿掉的東西」那段不要加回來。

## 已知事實（別再查錯）

- 夢炭、南永敦只有現場候位（11:00 起機台登記），不能預約。
- 6013 往機場站牌在동일로西側（05694，跟 Airbnb 同側），從機場來在東側（05695）；上車刷 T-money（每人 ≥ ₩17,000）或付現，WOWPASS 曾被拒。
- 機票：去程 KE5660（OZ712 執飛）11/4 TPE T2 11:05 → ICN T2 14:40；回程 KE2029 11/9 ICN T2 16:20 → TPE T1 18:10。
