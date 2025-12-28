from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from typing import Dict, Any, Optional
from .util import slugify

def jinja_env() -> Environment:
    templates_dir = (Path(__file__).resolve().parent.parent / "templates")
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"])
    )

def render_html(env, data: Dict[str, Any], doc_name: str, file_id: str, out_dir: str, preview_png: Optional[str] = None) -> str:
    html = env.get_template("report.html.j2").render(
        data=data,
        doc_name=doc_name,
        file_id=file_id,
        title=f"{doc_name} — Digest",
        preview_png=preview_png,
    )
    report_name = slugify(doc_name)
    out_path = Path(out_dir) / f"{report_name}.html"
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)
