# 首爾旅程手冊

`render.py` 與功能腳本（`template/_scripts.j2`）沿用九州手冊（`WeiCho/kyushu-2026-joeemma`），外觀是自己的：
jyuutaku-family.co.jp 的淡雅風格、iPhone 優先，設計決定記在 `DESIGN.md`。另外加上口袋名單（`wishlist`）與 Naver 地圖連結。
**樣板以本 repo 為準**，不要再用 `travel-planner/template/` 覆蓋回來。

- 資料：`E:/Projects/travel-planner/trips/首爾/trip.json` 改完複製成本 repo 的 `trip.json` 再 push，`deploy.yml` 自動渲染部署。
- 天氣：`forecast.yml` 每天 06:10／18:10（韓國時間）跑 `scripts/update_forecast.py`，把 Open-Meteo 預報寫進線上 `trip.json` 的 `days[].forecast`。
  所以複製前要先 `git pull`，並保留線上那份的 `forecast`／`forecast_extra`，不要用本機舊的蓋掉。
- 封面照：`template/_hero_image.j2`（北村韓屋村，Pexels，Artem Krapivin）；封面弧形照片帶與交通區背景都用這一張。
- 字型：英文 Questrial 內嵌在 `template/_questrial_font.j2`；中文用手機系統字，不另外下載。
