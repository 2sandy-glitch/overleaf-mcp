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


def test_display_detection(tmp_path):
    runtime, x11 = tmp_path / "run", tmp_path / "x11"
    runtime.mkdir()
    x11.mkdir()

    env, flags = browser_login.display_env({"DISPLAY": ":5"}, str(runtime), str(x11))
    assert env["DISPLAY"] == ":5" and flags == []  # terminal already has a display: untouched

    with pytest.raises(browser_login.AuthError, match="--paste"):
        browser_login.display_env({}, str(runtime), str(x11))  # nothing at all (SSH)

    (x11 / "X1").touch()
    (runtime / ".mutter-Xwaylandauth.ABC").touch()
    env, flags = browser_login.display_env({}, str(runtime), str(x11))
    assert env["DISPLAY"] == ":1" and env["XAUTHORITY"].endswith(".mutter-Xwaylandauth.ABC")
    assert flags == ["--ozone-platform=x11"]

    (runtime / "wayland-0").touch()
    (runtime / "wayland-0.lock").touch()
    env, flags = browser_login.display_env({}, str(runtime), str(x11))
    assert env["WAYLAND_DISPLAY"] == "wayland-0" and env["XDG_RUNTIME_DIR"] == str(runtime)
    assert flags == ["--ozone-platform=wayland"]  # Wayland preferred


def test_early_exit_reason_skips_noise(tmp_path):
    log = tmp_path / "b.log"
    log.write_text(
        "[1:1:ERROR:ozone_platform_x11.cc:257] Missing X server or $DISPLAY\n"
        "[1:2:ERROR:registration_request.cc:291] Registration response error message: PHONE_REGISTRATION_ERROR\n"
    )
    assert browser_login._last_error(log) == "Missing X server or $DISPLAY"
    assert browser_login._last_error(tmp_path / "missing.log") == ""
