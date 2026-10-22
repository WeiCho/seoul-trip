#!/usr/bin/env python3
"""trip.json + template/itinerary.html.j2 → 行程表.html

用法：python render.py trips/<旅程名>
"""
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
TEMPLATE_DIR = ROOT / "template"
TEMPLATE_NAME = "itinerary.html.j2"
OUTPUT_NAME = "行程表.html"
# PWA 附屬檔（放到 HTTPS 空間時可安裝、離線；單檔 file:// 用法不受影響）
SW_NAME = "sw.js"
MANIFEST_NAME = "manifest.webmanifest"
ICON_NAME = "icon.svg"
INDEX_NAME = "index.html"

INDEX_HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url=%(html)s">
<link rel="canonical" href="%(html)s">
<title>旅程手冊</title>
<script>location.replace("%(html)s");</script>
</head>
<body>前往 <a href="%(html)s">旅程手冊</a>…</body>
</html>
"""

SW_JS = """/* 旅程手冊離線快取（PWA）。以 file:// 開啟時不會註冊，不影響單檔離線用法 */
const CACHE = "trip-%(version)s";
const ASSETS = ["./", "./%(index)s", "./%(html)s", "./%(manifest)s", "./%(icon)s"];
self.addEventListener("install", (e) => {
  // cache: "reload" 跳過瀏覽器的 HTTP 快取（GitHub Pages 給 10 分鐘），不然新版 SW 可能存到舊頁
  e.waitUntil(caches.open(CACHE)
    .then((c) => c.addAll(ASSETS.map((u) => new Request(u, {cache: "reload"}))))
    .then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  if (new URL(req.url).origin !== location.origin) return; // 外部連結（地圖等）走網路
  const save = (res) => {
    if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
    return res;
  };
  // 頁面本身網路優先：手冊每天自動更新天氣，快取優先會讓人一直看到前一版；
  // 沒網路（山區、飛機上）才退回快取。圖示等靜態檔維持快取優先
  if (req.mode === "navigate") {
    e.respondWith(fetch(req, {cache: "no-cache"}).then(save)
      .catch(() => caches.match(req).then((hit) => hit || caches.match("./%(html)s"))));
    return;
  }
  e.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then(save)
      .catch(() => caches.match("./%(html)s")))
  );
});
"""

ITEM_TYPES = ("景點", "餐廳", "交通", "住宿", "購物")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
LATLNG_RE = re.compile(r"^-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?$")
WEEKDAYS = ("週一", "週二", "週三", "週四", "週五", "週六", "週日")

# 花費分類：items 的 type 與 bookings 的 type 各自對映到統一的花費類別
CATEGORY_OF_ITEM = {"景點": "景點", "餐廳": "餐飲", "交通": "交通", "住宿": "住宿", "購物": "購物"}
CATEGORY_OF_BOOKING = {
    "航班": "交通", "飛機": "交通", "機票": "交通",
    "飯店": "住宿", "旅館": "住宿", "民宿": "住宿", "住宿": "住宿",
    "餐廳": "餐飲",
}
# 待確認偵測：名稱或備註命中這些字樣視為尚未定案
PENDING_RE = re.compile(r"待補|待確認|待報價|待補充|尚未|未定|TBD", re.IGNORECASE)
# 本日路線一鍵導航：Google Maps 消費者版路線點數上限（origin + waypoints + destination）
MAX_ROUTE_POINTS = 10

# 結構化交通（items[].transit）
TRANSIT_MODES = {
    "subway": "🚇", "train": "🚆", "bus": "🚌", "walk": "🚶", "taxi": "🚕",
    "flight": "✈️", "boat": "⛴️",
}
MAP_APPS = ("google", "kakao", "naver")
PRIORITIES = ("must", "optional")
# 排程鬆緊（九州回顧）：只警告、不擋產出
MAX_SPOTS_PER_DAY = 3          # 每天「景點＋購物」上限
SPOT_TYPES = ("景點", "購物")
BUFFER_MIN = 20                # 停留＋交通之外，至少再留的分鐘數


class TripError(ValueError):
    """trip.json 內容不合法。訊息需指出是哪裡、哪一筆。"""


def _require(obj, key, ctx):
    if key not in obj or obj[key] in (None, ""):
        raise TripError(f"{ctx} 缺少必填欄位「{key}」")
    return obj[key]


def _parse_date(value, ctx):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise TripError(f"{ctx} 日期格式錯誤（應為 YYYY-MM-DD）：{value!r}") from None


def _check_time(value, ctx):
    if not TIME_RE.match(str(value)):
        raise TripError(f"{ctx} 時間格式錯誤（應為 24 小時制 HH:MM）：{value!r}")
    return str(value)


def _check_cost(obj, ctx):
    cost = obj.get("cost", 0)
    if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0:
        raise TripError(f"{ctx} 的 cost 必須是 ≥ 0 的數字：{cost!r}")
    return cost


def _check_transit(tr, ictx):
    ctx = f"{ictx} 的 transit"
    if not isinstance(tr, dict):
        raise TripError(f"{ctx} 必須是物件")
    mode = tr.get("mode")
    if mode is not None and mode not in TRANSIT_MODES:
        raise TripError(f"{ctx}.mode 必須是 {'/'.join(TRANSIT_MODES)}：{mode!r}")
    minutes = tr.get("minutes")
    if minutes is not None and (
        not isinstance(minutes, int) or isinstance(minutes, bool) or minutes <= 0
    ):
        raise TripError(f"{ctx}.minutes 必須是正整數（分鐘）：{minutes!r}")
    for key in ("first", "last"):
        if tr.get(key):
            _check_time(tr[key], f"{ctx}.{key}")
    deps = tr.get("departures") or []
    if not isinstance(deps, list):
        raise TripError(f"{ctx}.departures 必須是 HH:MM 陣列")
    for dep in deps:
        _check_time(dep, f"{ctx}.departures")
    steps = tr.get("steps") or []
    if not isinstance(steps, list):
        raise TripError(f"{ctx}.steps 必須是陣列")
    for s_idx, step in enumerate(steps, 1):
        if isinstance(step, str):
            continue
        if not isinstance(step, dict) or not step.get("text"):
            raise TripError(f"{ctx}.steps 第 {s_idx} 步缺少 text")
    for key in ("from_ll", "to_ll"):
        if tr.get(key) and not LATLNG_RE.match(str(tr[key])):
            raise TripError(f"{ctx}.{key} 格式應為「緯度,經度」：{tr[key]!r}")


def validate(data):
    """驗證 trip.json 結構，錯誤丟 TripError。"""
    if not isinstance(data, dict):
        raise TripError("trip.json 頂層必須是物件")

    trip = _require(data, "trip", "trip.json")
    # destination 是選用的：封面拿掉那一行之後，trip.json 可以整個不寫
    for key in ("title", "currency"):
        _require(trip, key, "trip")
    if "budget" not in trip:
        raise TripError("trip 缺少必填欄位「budget」")
    _check_cost({"cost": trip["budget"]}, "trip.budget")
    start = _parse_date(_require(trip, "start_date", "trip"), "trip.start_date")
    end = _parse_date(_require(trip, "end_date", "trip"), "trip.end_date")
    if end < start:
        raise TripError(f"end_date（{end}）不得早於 start_date（{start}）")

    days = _require(data, "days", "trip.json")
    if not isinstance(days, list) or not days:
        raise TripError("days 必須至少包含一天")

    prev_date = None
    for d_idx, day in enumerate(days, 1):
        ctx = f"days 第 {d_idx} 天"
        d = _parse_date(_require(day, "date", ctx), f"{ctx} 的 date")
        if d < start or d > end:
            raise TripError(f"{ctx} 的日期 {d} 不在旅程區間（{start} ~ {end}）內")
        if prev_date is not None:
            if d == prev_date:
                raise TripError(f"{ctx} 的日期 {d} 與前一天重複")
            if d < prev_date:
                raise TripError(
                    f"{ctx} 的日期 {d} 早於前一天（{prev_date}），days 需依日期遞增排列"
                )
        prev_date = d
        items = day.get("items")
        if not isinstance(items, list):
            raise TripError(f"{ctx} 缺少 items 陣列")
        prev_time, prev_name = None, None
        for item in items:
            name = _require(item, "name", f"{ctx} 的某筆行程")
            ictx = f"{ctx} 的「{name}」"
            t = _check_time(_require(item, "time", ictx), ictx)
            itype = _require(item, "type", ictx)
            if itype not in ITEM_TYPES:
                raise TripError(f"{ictx} 的 type 必須是 {'/'.join(ITEM_TYPES)}：{itype!r}")
            _check_cost(item, ictx)
            if item.get("priority") not in (None, *PRIORITIES):
                raise TripError(f"{ictx} 的 priority 必須是 {'/'.join(PRIORITIES)}：{item['priority']!r}")
            if item.get("transit") is not None:
                _check_transit(item["transit"], ictx)
            if prev_time is not None and t < prev_time:
                raise TripError(
                    f"{ctx} 行程未依時間排序：「{name}」（{t}）排在「{prev_name}」（{prev_time}）之後"
                )
            prev_time, prev_name = t, name

    apps = trip.get("map_apps")
    if apps is not None and (not isinstance(apps, list) or any(a not in MAP_APPS for a in apps)):
        raise TripError(f"trip.map_apps 必須是 {'/'.join(MAP_APPS)} 組成的陣列：{apps!r}")

    for b_idx, booking in enumerate(data.get("bookings") or [], 1):
        ctx = f"bookings 第 {b_idx} 筆"
        _require(booking, "type", ctx)
        _require(booking, "name", ctx)
        if booking.get("date"):
            _parse_date(booking["date"], f"{ctx} 的 date")
        if booking.get("time"):
            _check_time(booking["time"], ctx)
        _check_cost(booking, ctx)

    notes = data.get("notes") or []
    if not isinstance(notes, list):
        raise TripError("notes 必須是字串陣列")

    alerts = data.get("alerts") or []
    if not isinstance(alerts, list):
        raise TripError("alerts 必須是字串陣列")

    transit = data.get("transit") or []
    if not isinstance(transit, list):
        raise TripError("transit 必須是陣列")
    for t_idx, t in enumerate(transit, 1):
        _require(t, "route", f"transit 第 {t_idx} 段")
        # 交通區按天分頁，所以 day 是必填——沒填的話那一段不會出現在任何一頁上
        day_no = _require(t, "day", f"transit 第 {t_idx} 段")
        if not isinstance(day_no, int) or isinstance(day_no, bool)                 or not 1 <= day_no <= len(data["days"]):
            raise TripError(
                f"transit 第 {t_idx} 段的 day 必須是 1～{len(data['days'])} 的整數：{day_no!r}"
            )
        # 九州回顧後加的欄位（逐步指引、首末班、發車時刻、座標），規則同 items[].transit。
        # 一段交通可以有兩個以上的方案（options），例如「機場巴士」與「塞車改搭鐵路」；
        # 沒有 options 時整段本身就是唯一方案
        opts = t.get("options")
        if opts is not None and (not isinstance(opts, list) or not opts):
            raise TripError(f"transit 第 {t_idx} 段的 options 必須是非空陣列")
        for o_idx, o in enumerate(opts or [t], 1):
            octx = f"transit 第 {t_idx} 段" + (f"的方案 {o_idx}" if opts else "")
            if opts:
                _require(o, "label", octx)
            _check_transit(o, octx)
            # live：要在大卡上顯示哪幾站的即時到站（需要 trip.live_api 指向 travel-planner/worker）
            live = o.get("live") or []
            if not isinstance(live, list) or any(not isinstance(x, dict) or not x.get("station") for x in live):
                raise TripError(f"{octx} 的 live 必須是陣列，每項至少要有 station")
        if t.get("at"):
            _check_time(t["at"], f"transit 第 {t_idx} 段的 at")

    transit_links = data.get("transit_links") or []
    if not isinstance(transit_links, list):
        raise TripError("transit_links 必須是陣列")
    for l_idx, link in enumerate(transit_links, 1):
        ctx = f"transit_links 第 {l_idx} 項"
        _require(link, "label", ctx)
        _require(link, "url", ctx)

    wishlist = data.get("wishlist") or []
    if not isinstance(wishlist, list):
        raise TripError("wishlist 必須是陣列")
    for w_idx, w in enumerate(wishlist, 1):
        name = _require(w, "name", f"wishlist 第 {w_idx} 項")
        itype = w.get("type")
        if itype and itype not in ITEM_TYPES:
            raise TripError(
                f"wishlist「{name}」的 type 必須是 {'/'.join(ITEM_TYPES)}：{itype!r}"
            )

    highlights = data.get("highlights") or []
    if not isinstance(highlights, list):
        raise TripError("highlights 必須是陣列")
    for h_idx, h in enumerate(highlights, 1):
        _require(h, "title", f"highlights 第 {h_idx} 項")


def make_icon_svg(trip):
    """單色松綠圓角方塊 + 襯線首字，作為 PWA / 主畫面圖示。"""
    label = trip.get("hero_word") or trip.get("title") or "旅"
    glyph = xml_escape(label[0])
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">'
        '<rect width="512" height="512" rx="112" fill="#315b49"/>'
        '<text x="50%" y="54%" text-anchor="middle" dominant-baseline="central" '
        'font-family="Noto Serif TC,Georgia,serif" font-size="300" font-weight="700" '
        f'fill="#f7f3ea">{glyph}</text></svg>'
    )


def make_manifest(trip):
    return {
        "name": trip["title"],
        "short_name": (trip.get("hero_word") or trip["title"])[:12],
        "start_url": "./" + OUTPUT_NAME,
        "scope": "./",
        "display": "standalone",
        "background_color": "#f7f3ea",
        "theme_color": "#f7f3ea",
        "icons": [
            {"src": ICON_NAME, "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}
        ],
    }


def naver_url(query):
    return "https://map.naver.com/p/search/" + quote(str(query))


def map_url(query):
    return "https://www.google.com/maps/search/?api=1&query=" + quote(str(query))


def dir_url(query):
    return "https://www.google.com/maps/dir/?api=1&destination=" + quote(str(query))


def build_route_url(queries):
    """把當日各站的 map_query 串成 Google Maps 多點路線連結。

    回傳 (url, capped)：
    - 0 站 → (None, False)
    - 1 站 → 退化為單點搜尋連結
    - 多站 → dir 路線；超過上限時只取前段＋終點並回報 capped=True（不靜默截斷）
    """
    qs = [q for q in queries if q]
    if not qs:
        return None, False
    if len(qs) == 1:
        return map_url(qs[0]), False
    capped = False
    if len(qs) > MAX_ROUTE_POINTS:
        qs = qs[:MAX_ROUTE_POINTS - 1] + [qs[-1]]
        capped = True
    origin, destination, waypoints = qs[0], qs[-1], qs[1:-1]
    url = (
        "https://www.google.com/maps/dir/?api=1"
        "&origin=" + quote(str(origin))
        + "&destination=" + quote(str(destination))
    )
    if waypoints:
        url += "&waypoints=" + quote("|".join(str(w) for w in waypoints))
    return url, capped


def _minutes_of(hhmm):
    h, m = str(hhmm).split(":")
    return int(h) * 60 + int(m)


def parse_duration(text):
    """「1.5h」「40m」「2h35m」「80-110m」「1-2h」→ 分鐘數（區間取上限）；看不懂回傳 None。"""
    t = re.sub(r"\s+", "", str(text or "")).lower()
    for a, b in (("小時", "h"), ("分鐘", "m"), ("分", "m"), ("hr", "h"), ("min", "m")):
        t = t.replace(a, b)
    rng = re.fullmatch(r"([\d.]+)-([\d.]+)([hm])", t)
    if rng:
        val, unit = float(rng.group(2)), rng.group(3)
        return round(val * 60) if unit == "h" else round(val)
    hm = re.fullmatch(r"(?:([\d.]+)h)?(?:(\d+)m)?", t)
    if hm and (hm.group(1) or hm.group(2)):
        return round(float(hm.group(1) or 0) * 60) + int(hm.group(2) or 0)
    return None


def transit_links(tr, from_query, to_query, apps):
    """依 trip.map_apps 產生 A→B 大眾運輸路線深連結。缺起點或終點就不產生。"""
    a = tr.get("from_query") or from_query
    b = tr.get("to_query") or to_query
    a_name = tr.get("from") or a
    b_name = tr.get("to") or b
    a_ll = str(tr.get("from_ll") or "").replace(" ", "")
    b_ll = str(tr.get("to_ll") or "").replace(" ", "")
    # 沒有搜尋字串時，Google 直接用座標
    a, b = a or a_ll, b or b_ll
    links = []
    # 走路、計程車要用各家的步行／開車模式，其餘都是大眾運輸
    kind = {"walk": "walk", "taxi": "car"}.get(tr.get("mode"), "transit")
    for app in apps:
        if app == "google" and a and b:
            mode = {"walk": "walking", "car": "driving"}.get(kind, "transit")
            links.append({"label": "Google 路線", "url": (
                "https://www.google.com/maps/dir/?api=1&origin=" + quote(str(a))
                + "&destination=" + quote(str(b)) + "&travelmode=" + mode)})
        # Kakao 只吃座標：用站名的 ?sName=&eName= 會開出起訖點空白的路線頁（實測）
        elif app == "kakao" and a_ll and b_ll:
            links.append({"label": "Kakao 路線", "url": (
                "https://map.kakao.com/link/by/"
                + {"walk": "walk", "car": "car"}.get(kind, "traffic") + "/"
                + quote(f"{a_name},{a_ll}", safe=",") + "/" + quote(f"{b_name},{b_ll}", safe=","))})
        elif app == "naver" and a_ll and b_ll:
            (alat, alng), (blat, blng) = a_ll.split(","), b_ll.split(",")
            links.append({"label": "Naver 路線", "app": "naver", "url": (
                f"https://map.naver.com/p/directions/{alng},{alat},{quote(str(a_name))},,/"
                f"{blng},{blat},{quote(str(b_name))},,/-/" + kind)})
    return links


def enrich_transit(tr, from_query, to_query, apps):
    """transit 物件 → 模板要用的欄位（摘要列、步驟、時刻、深連結）。"""
    tr = dict(tr)
    tr["icon"] = TRANSIT_MODES.get(tr.get("mode"), "→")
    route = " → ".join(x for x in (tr.get("from"), tr.get("to")) if x)
    tr["title"] = " ".join(x for x in (tr.get("line"), route) if x) or "前往下一站"
    sub = []
    if tr.get("direction"):
        sub.append(tr["direction"])
    if tr.get("minutes"):
        sub.append(f"約 {tr['minutes']} 分")
    tr["sub"] = "・".join(sub)
    tr["steps"] = [
        {"text": st} if isinstance(st, str) else st for st in tr.get("steps") or []
    ]
    sched = []
    if tr.get("first"):
        sched.append(f"首班 {tr['first']}")
    if tr.get("last"):
        sched.append(f"末班 {tr['last']}")
    if tr.get("headway"):
        sched.append(tr["headway"])
    tr["sched"] = " · ".join(sched)
    tr["route_links"] = transit_links(tr, from_query, to_query, apps)
    return tr


def pacing_warnings(day_no, items):
    """排太緊的警告（九州回顧）：景點＋購物過多、或兩站之間來不及。"""
    warnings = []
    spots = [it for it in items if it["type"] in SPOT_TYPES]
    if len(spots) > MAX_SPOTS_PER_DAY:
        warnings.append(
            f"Day {day_no} 排了 {len(spots)} 個景點／購物（建議最多 {MAX_SPOTS_PER_DAY} 個）"
        )
    # 只檢查有填交通時間的段落：舊的 next_transit 文字沒有分鐘數可算
    for item, nxt in zip(items, items[1:]):
        tr = item.get("transit") or {}
        if not tr.get("minutes"):
            continue
        stay = parse_duration(item.get("duration")) or 0
        need = stay + tr["minutes"] + BUFFER_MIN
        gap = _minutes_of(nxt["time"]) - _minutes_of(item["time"])
        if gap < need:
            warnings.append(
                f"Day {day_no}「{item['name']}」→「{nxt['name']}」只隔 {gap} 分，"
                f"停留 {stay}＋交通 {tr['minutes']}＋緩衝 {BUFFER_MIN} 需要 {need} 分"
            )
    return warnings


def make_fx_alt(fx):
    """回傳一個 fx_alt(v) 函式：有匯率且金額非零時輸出「 ≈ ¥12,345」，否則空字串。"""
    def fx_alt(v):
        if not fx or not fx.get("rate") or not v:
            return ""
        alt = float(v) * fx["rate"]
        return f" ≈ {fx.get('currency', '')}{alt:,.0f}"
    return fx_alt


def _norm(s):
    """名稱正規化：去掉所有空白，供疑似重複比對。"""
    return re.sub(r"\s+", "", str(s or ""))


def _pending_reason(obj, is_booking=False):
    """判斷單筆 item/booking 是否待確認，回傳原因字串或 None。

    明確 status=confirmed 會抑制所有自動旗標（使用者已人工確認）。
    """
    status = obj.get("status")
    if status == "confirmed":
        return None
    if status == "pending":
        return "標記為待確認"
    text = f"{obj.get('name', '')} {obj.get('note', '')}"
    if PENDING_RE.search(text):
        return "內容含待確認字樣"
    if is_booking and obj.get("cost", 0) and not obj.get("code"):
        return "有金額但缺確認碼"
    return None


def enrich(data):
    """加上衍生欄位，回傳模板 context。不修改原始 data。"""
    trip = dict(data["trip"])
    trip.setdefault("travelers", 1)
    start = _parse_date(trip["start_date"], "start_date")
    end = _parse_date(trip["end_date"], "end_date")
    trip["num_days"] = (end - start).days + 1
    end_label = f"{end.month:02d}.{end.day:02d}"
    if end.year != start.year:
        end_label = f"{end.year}.{end_label}"
    trip["range_label"] = f"{start.year}.{start.month:02d}.{start.day:02d} – {end_label}"
    if not trip.get("hero_word"):
        # hero 浮水印：取目的地最後一段（「日本・東京」→「東京」），最多 4 字。
        # 沒寫 destination 就退回標題
        source = str(trip.get("destination") or trip["title"]).strip()
        segment = re.split(r"[・·,，/\s]+", source)[-1]
        trip["hero_word"] = segment[:4] or str(trip["title"])[:4]

    apps = trip.get("map_apps") or ["google"]
    warnings = []
    days = []
    spent = 0
    by_cat = {}          # 花費類別 → 金額
    paid_items = []      # (名稱, 金額) 供疑似重複比對
    pending = []         # 待確認清單
    for day in data["days"]:
        d = _parse_date(day["date"], "date")
        items = []
        subtotal = 0
        day_no = len(days) + 1
        for raw in day["items"]:
            item = dict(raw)
            item.setdefault("cost", 0)
            subtotal += item["cost"]
            if item["cost"]:
                cat = CATEGORY_OF_ITEM.get(item["type"], "其他")
                by_cat[cat] = by_cat.get(cat, 0) + item["cost"]
                paid_items.append((item["name"], item["cost"]))
            if item.get("map_query"):
                item["map_url"] = map_url(item["map_query"])
            # 首爾的行程導航一律開 Naver：Google 在韓國不能步行導航
            if item.get("naver_query"):
                item["nav_url"] = naver_url(item["naver_query"])
            reason = _pending_reason(item)
            if reason:
                pending.append({
                    "where": f"Day {day_no}「{item['name']}」",
                    "reason": reason,
                    "anchor": f"day-{day_no}",
                })
            items.append(item)
        # 交通銜接列連到「下一站」的導航；結構化 transit 優先於 next_transit 文字
        for idx, item in enumerate(items):
            nxt = items[idx + 1] if idx + 1 < len(items) else {}
            nq = nxt.get("map_query")
            if item.get("transit"):
                item["transit"] = enrich_transit(item["transit"], item.get("map_query"), nq, apps)
            elif item.get("next_transit") and nq:
                item["transit_url"] = dir_url(nq)
        warnings += pacing_warnings(day_no, items)
        route_url, route_capped = build_route_url(
            [it.get("map_query") for it in items]
        )
        spent += subtotal
        days.append({
            **day,
            "items": items,
            "weekday": WEEKDAYS[d.weekday()],
            "date_label": f"{d.month}月{d.day}日",
            # 跳日列的格子只有 55px 上下，塞不下「10月15日 · 週四」，
            # 另備一組短寫：10/15 與單字的「四」
            "date_short": f"{d.month}/{d.day}",
            "weekday_short": WEEKDAYS[d.weekday()][-1],
            "subtotal": subtotal,
            "day_no": day_no,
            "route_url": route_url,
            "route_capped": route_capped,
        })

    bookings = []
    for raw in data.get("bookings") or []:
        booking = dict(raw)
        booking.setdefault("cost", 0)
        spent += booking["cost"]
        if booking["cost"]:
            cat = CATEGORY_OF_BOOKING.get(booking["type"], "其他")
            by_cat[cat] = by_cat.get(cat, 0) + booking["cost"]
        reason = _pending_reason(booking, is_booking=True)
        if reason:
            pending.append({
                "where": f"訂位「{booking['name']}」",
                "reason": reason,
                "anchor": "budget",
            })
        # 疑似重複：與某行程項目名稱相近且金額相同
        if booking["cost"] and booking.get("status") != "confirmed":
            nb = _norm(booking["name"])
            for iname, icost in paid_items:
                ni = _norm(iname)
                if icost == booking["cost"] and (nb in ni or ni in nb):
                    pending.append({
                        "where": f"訂位「{booking['name']}」",
                        "reason": f"與行程項目「{iname}」金額相同、名稱相近，疑似重複計價",
                        "anchor": "budget",
                    })
                    break
        bookings.append(booking)

    # 交通按天分組：交通區跟行程一樣一次只顯示一天，但只列有要自己搭車的那幾天
    # （包車或機場接送的日子沒有區間可寫，留一格空的只會讓人多點一次）
    def enrich_option(o):
        o = dict(o)
        o["steps"] = [{"text": st} if isinstance(st, str) else st for st in o.get("steps") or []]
        sched = [f"首班 {o['first']}" if o.get("first") else "",
                 f"末班 {o['last']}" if o.get("last") else "", o.get("headway") or ""]
        o["sched"] = " · ".join(x for x in sched if x)
        o["route_links"] = transit_links(o, o.get("from_query"), o.get("to_query"), apps)
        return o

    transit = []
    for raw in data.get("transit") or []:
        t = dict(raw)
        t["options"] = [enrich_option(o) for o in (raw.get("options") or [raw])]
        transit.append(t)
    for day in days:
        day["transit"] = [t for t in transit if t.get("day") == day["day_no"]]
        # at＝這段交通從哪個行程項目出發（HH:MM），讓項目的對話框可以跳到這一段
        for k, t in enumerate(day["transit"], 1):
            t["anchor"] = f"leg-{day['day_no']}-{k}"
            for item in day["items"]:
                if t.get("at") and item["time"] == t["at"]:
                    item.setdefault("legs", []).append(t)
    transit_days = [day for day in days if day["transit"]]

    wishlist = []
    for raw in data.get("wishlist") or []:
        w = dict(raw)
        if w.get("map_query"):
            w["map_url"] = map_url(w["map_query"])
        if w.get("naver_query"):
            w["naver_url"] = naver_url(w["naver_query"])
        wishlist.append(w)
    # 依 category 分組，組的順序照第一次出現的順序（食物、逛街…）
    wishlist_groups = []
    for w in wishlist:
        cat = w.get("category") or "其他"
        for g in wishlist_groups:
            if g["label"] == cat:
                g["items"].append(w)
                break
        else:
            wishlist_groups.append({"label": cat, "items": [w]})

    budget = trip["budget"]
    travelers = trip["travelers"] or 1
    by_category = sorted(
        ({"label": k, "amount": v} for k, v in by_cat.items() if v),
        key=lambda x: -x["amount"],
    )
    return {
        "trip": trip,
        "days": days,
        "bookings": bookings,
        "notes": data.get("notes") or [],
        "alerts": data.get("alerts") or [],
        "transit": transit,
        "transit_days": transit_days,
        # 不綁哪一天的一句話（付款方式），放在交通大標下當說明
        "transit_note": data.get("transit_note") or "",
        "transit_links": data.get("transit_links") or [],
        "wishlist": wishlist,
        "wishlist_groups": wishlist_groups,
        "highlights": data.get("highlights") or [],
        "pending": pending,
        "warnings": warnings,
        "totals": {
            "spent": spent,
            "budget": budget,
            "over": spent > budget,
            "has_costs": spent > 0,
            "per_person": round(spent / travelers),
            "by_category": by_category,
        },
    }


def render(trip_dir):
    """讀取 trip_dir/trip.json，渲染並原子性寫出 行程表.html。回傳輸出路徑。"""
    trip_dir = Path(trip_dir)
    src = trip_dir / "trip.json"
    if not src.is_file():
        raise TripError(f"找不到 {src}")
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise TripError(f"{src} 不是合法 JSON：{e}") from None

    validate(data)
    context = enrich(data)
    # 供頁內編輯器讀取的原始資料（跳脫 < 以免 </script> 或 <!-- 破壞 script 區塊）
    context["data_json"] = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "j2"]),
    )
    env.globals["fx_alt"] = make_fx_alt(context["trip"].get("fx"))
    html = env.get_template(TEMPLATE_NAME).render(**context)
    for w in context["warnings"]:
        print(f"⚠ 排太緊：{w}")

    out = trip_dir / OUTPUT_NAME
    tmp = out.with_suffix(".html.tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(out)

    # PWA 附屬檔：內容變動時 cache 版本跟著變，強制更新
    version = hashlib.md5(html.encode("utf-8")).hexdigest()[:8]
    (trip_dir / ICON_NAME).write_text(make_icon_svg(context["trip"]), encoding="utf-8")
    (trip_dir / MANIFEST_NAME).write_text(
        json.dumps(make_manifest(context["trip"]), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (trip_dir / INDEX_NAME).write_text(INDEX_HTML % {"html": OUTPUT_NAME}, encoding="utf-8")
    (trip_dir / SW_NAME).write_text(
        SW_JS % {"version": version, "index": INDEX_NAME, "html": OUTPUT_NAME,
                 "manifest": MANIFEST_NAME, "icon": ICON_NAME},
        encoding="utf-8",
    )
    return out


def main(argv):
    if len(argv) != 2:
        print("用法：python render.py trips/<旅程名>")
        return 2
    try:
        out = render(argv[1])
    except TripError as e:
        print(f"渲染失敗：{e}")
        return 1
    print(f"已輸出：{out}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main(sys.argv))
