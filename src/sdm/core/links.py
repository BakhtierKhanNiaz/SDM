"""Where people get SDM and its browser extension (M11). One place, so a release only has to
update these."""

# The public repository (M11d).
PROJECT_URL = "https://github.com/Conditions-tech/SDM"
RELEASES_URL = f"{PROJECT_URL}/releases/latest"
# Listings on the free extension stores, once published (None until then).
EDGE_STORE_URL: str | None = None
FIREFOX_STORE_URL: str | None = None


def extension_page(browser_key: str) -> str:
    """Where a user of this browser gets SDM's extension."""
    if browser_key == "edge" and EDGE_STORE_URL:
        return EDGE_STORE_URL
    if browser_key == "firefox" and FIREFOX_STORE_URL:
        return FIREFOX_STORE_URL
    return RELEASES_URL
