"""Guards for the static frontend. There is no browser test runner, so these
check the contract the page depends on: it is served, it works offline, it
never uses innerHTML, and it carries the design spec's colour tokens."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parent.parent / "static"
FONT_FILES = [
    "IBMPlexSans-Variable-latin.woff2",
    "IBMPlexMono-Regular-latin.woff2",
    "IBMPlexMono-SemiBold-latin.woff2",
    "OFL.txt",
]
COLOUR_TOKENS = {
    "--paper": "#F3F1EA",
    "--surface": "#FBFAF6",
    "--ink": "#16181C",
    "--navy": "#1D3A6E",
    "--altered": "#B3261E",
    "--review": "#955300",
    "--clear": "#1F6B3A",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "fe.db"))
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(config, "EVIDENCE_DIR", str(tmp_path / "evidence"))
    from app.main import app, startup
    startup()
    return TestClient(app)


def test_index_serves_the_screening_form(client):
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert 'id="screen-form"' in html
    for name in ("document", "visa", "selfie"):
        assert re.search(rf'<input[^>]*type="file"[^>]*name="{name}"', html), name
    for name in ("full_name", "dob", "passport_no", "nationality", "email", "phone"):
        assert re.search(rf'<input[^>]*name="{name}"', html), name


@pytest.mark.parametrize("path", ["/static/styles.css", "/static/app.js"]
                         + [f"/static/fonts/{f}" for f in FONT_FILES])
def test_static_assets_are_served(client, path):
    assert client.get(path).status_code == 200


def test_no_network_urls_in_static_files():
    offenders = []
    for p in STATIC.rglob("*"):
        if p.is_file() and p.suffix in (".html", ".css", ".js"):
            text = p.read_text(encoding="utf-8")
            if "http://" in text or "https://" in text:
                offenders.append(str(p.relative_to(STATIC)))
    assert offenders == []


@pytest.mark.parametrize("forbidden", ["innerHTML", "outerHTML", "insertAdjacentHTML",
                                       "document.write", 'HTML"]', "HTML']"])
def test_app_js_never_injects_html(forbidden):
    assert forbidden not in (STATIC / "app.js").read_text(encoding="utf-8")


def test_app_js_counts_checks_from_engines_run():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "engines_run" in js


def test_app_js_validates_evidence_url_before_use():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert r"/^\/evidence\/[0-9a-f]{32}\.jpg$/" in js


def test_app_js_reasons_heading_counts_all_findings():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert '"· top "' in js and "nonInfo" in js


def test_index_has_inline_favicon_and_short_nationality_label(client):
    html = client.get("/").text
    assert '<link rel="icon" href="data:,">' in html
    assert re.search(r'<label for="f-nationality"[^>]*>Nationality</label>', html)
    assert 'placeholder="3-letter code, e.g. IND"' in html


@pytest.mark.parametrize("token,hexval", COLOUR_TOKENS.items())
def test_css_defines_colour_tokens(token, hexval):
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert re.search(rf"{re.escape(token)}\s*:\s*{hexval}\s*;", css, re.IGNORECASE), token
