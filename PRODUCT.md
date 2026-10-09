# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

使用者本人與兩位旅伴（共 3 人），2026/11/4–11/9 首爾五晚，住建大入口站旁 Airbnb。兩種情境：出發前在電腦上排行程；旅途中在路上用手機單手查「現在去哪、怎麼去、幾點到」。網路可能不穩，頁面要能離線開。

## Product Purpose

把整趟首爾旅程（行程、交通、口袋名單、記帳、出發前檢查、緊急聯絡）編成一份單一 HTML 手冊，部署在 GitHub Pages。成功的樣子：旅途中不用再翻筆記和訂位信；改行程只改 trip.json。

## Positioning

只屬於這趟旅程的口袋刊物，不是訂票 App、不是待辦清單。

## Operating Context

- 資料：`trip.json`（由 `E:/Projects/travel-planner/trips/首爾/trip.json` 複製），GitHub Actions 每天寫入天氣預報。
- 版面：`template/itinerary.html.j2` + `render.py`（從九州手冊搬來，加上口袋名單與 Naver 連結）。
- 頁內功能：換日、今日模式、交通分頁、口袋名單、₩ 記帳（localStorage）、出發前清單、緊急聯絡彈窗、深色／大字切換、`?edit=1` 編輯器。

## Capabilities and Constraints

- 單檔可離線（PWA service worker 快取）；外部只連地圖與官方時刻表。
- 內容主要是繁體中文，夾雜韓文店名與英文。
- 公開網站：訂位代號不得出現在頁面上。

## Brand Commitments

- 2026-10-09：先試了 eightdesign.co.jp 的活潑貼紙風（預覽後放棄，嫌字太大、手機會爆版）；改以 https://www.jyuutaku-family.co.jp/ 的淡雅風格做**預覽**（尚未套用到線上）。
- 字級要克制：使用者明講大字標題「太大、手機版會爆掉」，以直觀、舒服為準。

## Product Principles

1. 任何時刻掃一眼就能回答「現在去哪、怎麼去、幾點到」。
2. 資料與外觀分離：改版只動樣板，trip.json 不動。
3. 一份檔案就是全部：離線可讀。

## Accessibility & Inclusion

- 內文對比 ≥ 4.5:1；觸控目標 ≥ 44px；`prefers-reduced-motion` 提供無動畫版本；戶外陽光下可讀。
