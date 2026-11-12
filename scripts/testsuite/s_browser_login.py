"""Browser login: drives a real headless Chrome over DevTools, never contacting Overleaf."""

import pytest

from integrations.overleaf import browser_login

pytestmark = pytest.mark.skipif(browser_login.find_browser() is None, reason="no Chrome-family browser installed")


@pytest.fixture(autouse=True)
def isolated_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERLEAF_MCP_HOME", str(tmp_path / "home"))


def plant(value):
    def on_ready(devtools):
        devtools.send(
            "Storage.setCookies",
            {"cookies": [{"name": "overleaf_session2", "value": value, "domain": ".overleaf.com", "path": "/"}]},
        )

    return on_ready


def test_captures_session_once_signed_in():
    seen = []

    def validate(cookie):
        seen.append(cookie)
        return cookie == "overleaf_session2=signed-in"

    cookie = browser_login.capture_session(
        "https://www.overleaf.com", validate, headless=True, on_ready=plant("signed-in"), timeout=30, start_url="about:blank"
    )
    assert cookie == "overleaf_session2=signed-in"
    assert seen == ["overleaf_session2=signed-in"]


def test_times_out_when_never_signed_in():
    with pytest.raises(browser_login.AuthError, match="Not signed in"):
        browser_login.capture_session(
            "https://www.overleaf.com", lambda c: False, headless=True, on_ready=plant("anonymous"), timeout=4, start_url="about:blank"
        )


def test_cookie_filter():
    cookies = [
        {"name": "overleaf_session2", "value": "x", "domain": ".evil-overleaf.com"},
        {"name": "GCLB", "value": "y", "domain": "www.overleaf.com"},
        {"name": "overleaf_session2", "value": "z", "domain": ".overleaf.com"},
    ]
    assert browser_login.overleaf_cookies(cookies, "www.overleaf.com") == "overleaf_session2=z"
    assert browser_login.overleaf_cookies(cookies[:2], "www.overleaf.com") == ""
