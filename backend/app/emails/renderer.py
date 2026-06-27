from pathlib import Path
from string import Template
import html


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
ASSET_DIR = Path(__file__).resolve().parent / "assets"
BRAND_NAME = "BMSC Base de Conocimiento"
LOGO_CID = "bmsc-logo"
LOGO_FILENAME = "bmsc-logo.png"
LOGO_PATH = ASSET_DIR / LOGO_FILENAME


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_template(template_name: str, context: dict[str, object]) -> str:
    path = TEMPLATE_DIR / template_name
    template = Template(path.read_text(encoding="utf-8"))
    return template.substitute({key: str(value) for key, value in context.items()})


def render_html_email(title: str, content: str) -> str:
    return render_template(
        "base.html",
        {
            "title": escape(title),
            "brand_name": BRAND_NAME,
            "logo_cid": LOGO_CID,
            "content": content,
        },
    )
