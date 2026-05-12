"""HTTP clients for Jira, Bitbucket, Confluence, Bamboo.

Reads credentials directly from environment variables (via config.py).
No database dependency — fully standalone.
"""
import httpx

from config import (
    get_logger,
    JIRA_BASE_URL, JIRA_EMAIL, JIRA_TOKEN, JIRA_API_VERSION,
    BITBUCKET_BASE_URL, BITBUCKET_WORKSPACE, BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD,
    CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_TOKEN,
    BAMBOO_BASE_URL, BAMBOO_USERNAME, BAMBOO_TOKEN,
)

logger = get_logger("clients")

_COMMON_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


def _looks_like_pat(token: str) -> bool:
    """Detect Server/DC Personal Access Tokens (long base64 or known prefixes)."""
    if not token:
        return False
    return (
        token.startswith("BBDC-")
        or token.startswith("ATATT")
        or len(token) >= 40
    )


def _auth_for(base_url: str, username: str, token: str, cloud_domain: str = "atlassian.net") -> tuple[dict, tuple | None]:
    """Return (extra_headers, basic_auth_tuple) — Bearer for Server/DC PATs, Basic for Cloud."""
    headers: dict = {}
    is_cloud = cloud_domain in base_url.lower()
    if not is_cloud or _looks_like_pat(token):
        headers["Authorization"] = f"Bearer {token}"
        return headers, None
    return headers, (username, token)


def jira_client() -> httpx.Client | None:
    if not (JIRA_BASE_URL and JIRA_EMAIL and JIRA_TOKEN):
        logger.debug("Jira not configured")
        return None

    extra, auth = _auth_for(JIRA_BASE_URL, JIRA_EMAIL, JIRA_TOKEN)
    return httpx.Client(
        base_url=f"{JIRA_BASE_URL}/rest/api/{JIRA_API_VERSION}",
        auth=auth,
        headers={**_COMMON_HEADERS, **extra},
        timeout=30.0,
        verify=False,
    )


def jira_dashboards_client() -> httpx.Client | None:
    """Client for Jira's internal Dashboards plugin API (/rest/dashboards/1.0/).

    Used by the Jira UI for dashboard CRUD and gadget management. Not part of
    the public REST API but stable across DC versions.
    """
    if not (JIRA_BASE_URL and JIRA_EMAIL and JIRA_TOKEN):
        logger.debug("Jira not configured")
        return None

    extra, auth = _auth_for(JIRA_BASE_URL, JIRA_EMAIL, JIRA_TOKEN)
    return httpx.Client(
        base_url=f"{JIRA_BASE_URL}/rest/dashboards/1.0",
        auth=auth,
        headers={**_COMMON_HEADERS, **extra},
        timeout=30.0,
        verify=False,
    )


def jira_agile_client() -> httpx.Client | None:
    """Client for the Jira Software Agile REST API (/rest/agile/1.0/)."""
    if not (JIRA_BASE_URL and JIRA_EMAIL and JIRA_TOKEN):
        logger.debug("Jira not configured")
        return None

    extra, auth = _auth_for(JIRA_BASE_URL, JIRA_EMAIL, JIRA_TOKEN)
    return httpx.Client(
        base_url=f"{JIRA_BASE_URL}/rest/agile/1.0",
        auth=auth,
        headers={**_COMMON_HEADERS, **extra},
        timeout=30.0,
        verify=False,
    )


def bitbucket_client() -> httpx.Client | None:
    if not (BITBUCKET_BASE_URL and BITBUCKET_USERNAME and BITBUCKET_APP_PASSWORD):
        logger.debug("Bitbucket not configured")
        return None

    is_cloud = "bitbucket.org" in BITBUCKET_BASE_URL or "api.bitbucket" in BITBUCKET_BASE_URL
    headers = {**_COMMON_HEADERS}
    auth = None

    if is_cloud:
        if not BITBUCKET_WORKSPACE:
            logger.debug("Bitbucket Cloud requires BITBUCKET_WORKSPACE")
            return None
        api_base = f"{BITBUCKET_BASE_URL}/2.0/repositories/{BITBUCKET_WORKSPACE}"
        auth = (BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD)
    else:
        api_base = f"{BITBUCKET_BASE_URL}/rest/api/1.0"
        # Server/DC: BBDC- prefixed HTTP Access Tokens require Bearer auth
        if _looks_like_pat(BITBUCKET_APP_PASSWORD):
            headers["Authorization"] = f"Bearer {BITBUCKET_APP_PASSWORD}"
        else:
            auth = (BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD)

    return httpx.Client(
        base_url=api_base,
        auth=auth,
        headers=headers,
        timeout=30.0,
        verify=False,
    )


def is_bitbucket_server() -> bool:
    return "bitbucket.org" not in BITBUCKET_BASE_URL and "api.bitbucket" not in BITBUCKET_BASE_URL


def confluence_client() -> httpx.Client | None:
    if not (CONFLUENCE_BASE_URL and CONFLUENCE_EMAIL and CONFLUENCE_TOKEN):
        logger.debug("Confluence not configured")
        return None

    extra, auth = _auth_for(CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_TOKEN)
    return httpx.Client(
        base_url=f"{CONFLUENCE_BASE_URL}/rest/api",
        auth=auth,
        headers={**_COMMON_HEADERS, **extra},
        timeout=30.0,
        verify=False,
    )


def confluence_experimental_client() -> httpx.Client | None:
    """Client for Confluence's /rest/experimental API (version history endpoints)."""
    if not (CONFLUENCE_BASE_URL and CONFLUENCE_EMAIL and CONFLUENCE_TOKEN):
        logger.debug("Confluence not configured")
        return None

    extra, auth = _auth_for(CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_TOKEN)
    return httpx.Client(
        base_url=f"{CONFLUENCE_BASE_URL}/rest/experimental",
        auth=auth,
        headers={**_COMMON_HEADERS, **extra},
        timeout=30.0,
        verify=False,
    )


def bamboo_client() -> httpx.Client | None:
    if not (BAMBOO_BASE_URL and BAMBOO_USERNAME and BAMBOO_TOKEN):
        logger.debug("Bamboo not configured")
        return None

    headers = {"Accept": "application/json"}
    auth = None
    if _looks_like_pat(BAMBOO_TOKEN):
        headers["Authorization"] = f"Bearer {BAMBOO_TOKEN}"
    else:
        auth = (BAMBOO_USERNAME, BAMBOO_TOKEN)

    return httpx.Client(
        base_url=f"{BAMBOO_BASE_URL}/rest/api/latest",
        auth=auth,
        headers=headers,
        timeout=30.0,
        verify=False,
    )
