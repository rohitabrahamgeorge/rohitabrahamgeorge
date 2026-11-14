"""Attach to the persistent browser instead of launching a new one.

    from pwb import page
    p = page()            # the already-open tab; cookies/logins are kept
    p.goto("https://example.com")
"""
import os
import subprocess
from playwright.sync_api import sync_playwright

_START = os.path.join(os.path.dirname(os.path.realpath(__file__)), "start-browser.sh")
_pw = None


def browser():
    global _pw
    subprocess.run([_START], check=True, capture_output=True)
    _pw = _pw or sync_playwright().start()
    return _pw.chromium.connect_over_cdp("http://127.0.0.1:9222")


def page():
    """Return the existing open tab (creating one only if none exist)."""
    ctx = browser().contexts[0]
    return ctx.pages[0] if ctx.pages else ctx.new_page()
