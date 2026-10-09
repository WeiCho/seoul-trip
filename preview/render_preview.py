"""產生風格預覽：trip.json + preview/<名稱>.html.j2 → preview/行程表-<名稱>預覽.html

跟 render.py 共用驗證與資料整理（validate / enrich），只換樣板；不寫 index.html、sw.js，
不影響線上手冊。用法：python preview/render_preview.py family
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import render as R  # noqa: E402
from jinja2 import Environment, FileSystemLoader, select_autoescape  # noqa: E402



def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "family"
    out = ROOT / "preview" / f"行程表-{name}預覽.html"
    data = json.loads((ROOT / "trip.json").read_text(encoding="utf-8"))
    R.validate(data)
    context = R.enrich(data)
    context["data_json"] = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    env = Environment(
        # preview/ 放新樣板與腳本，template/ 只借封面照 _hero_image.j2
        loader=FileSystemLoader([str(ROOT / "preview"), str(ROOT / "template")]),
        autoescape=select_autoescape(["html", "j2"]),
    )
    env.globals["fx_alt"] = R.make_fx_alt(context["trip"].get("fx"))
    out.write_text(env.get_template(f"{name}.html.j2").render(**context), encoding="utf-8")
    print(f"已輸出：{out}")


if __name__ == "__main__":
    main()
