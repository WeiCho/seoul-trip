# 首爾旅程手冊

版面沿用九州手冊（`WeiCho/kyushu-2026-joeemma`）的 `render.py` 與 `template/`，另外加上口袋名單（`wishlist`）與 Naver 地圖連結；
**樣板以本 repo 為準**，不要再用 `travel-planner/template/` 覆蓋回來。

- 資料：`E:/Projects/travel-planner/trips/首爾/trip.json` 改完複製成本 repo 的 `trip.json` 再 push，`deploy.yml` 自動渲染部署。
- 天氣：`forecast.yml` 每天 06:10／18:10（韓國時間）跑 `scripts/update_forecast.py`，把 Open-Meteo 預報寫進線上 `trip.json` 的 `days[].forecast`。
  所以複製前要先 `git pull`，並保留線上那份的 `forecast`／`forecast_extra`，不要用本機舊的蓋掉。
- 封面照：`template/_hero_image.j2`（北村韓屋村，Pexels，Artem Krapivin）。
