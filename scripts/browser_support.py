"""Edge local e Chromium empacotado no CI Linux."""

import os


def launch_browser(playwright):
    channel = os.environ.get("HUNTER_BROWSER_CHANNEL", "msedge")
    if channel not in ("msedge", "chrome", "chromium"):
        raise ValueError("Canal de navegador invalido.")
    return playwright.chromium.launch(
        headless=True, **({} if channel == "chromium" else {"channel": channel})
    )
