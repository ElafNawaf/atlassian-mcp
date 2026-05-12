"""Minimal smoke tests for the Confluence version-history tools (MOCK_MODE).

Run: python test_smoke.py
"""
import os

os.environ.setdefault("MOCK_MODE", "true")

import tools  # noqa: E402


def test_get_page_versions():
    out = tools.confluence_get_page_versions("12345", limit=5)
    assert isinstance(out, dict), out
    assert "results" in out and len(out["results"]) >= 1
    assert out["results"][0]["number"] == 3
    print("ok  confluence_get_page_versions")


def test_get_page_version():
    out = tools.confluence_get_page_version("12345", version_number=2)
    assert isinstance(out, dict), out
    body = out["content"]["body"]["storage"]["value"]
    assert "version 2" in body
    print("ok  confluence_get_page_version")


def test_supporting_reads():
    assert tools.confluence_get_child_pages("12345")["results"][0]["title"] == "Child Page"
    assert tools.confluence_get_page_ancestors("12345")["ancestors"][0]["id"] == "1"
    assert tools.confluence_get_attachments("12345")["results"][0]["title"] == "diagram.png"
    assert tools.confluence_get_page_labels("12345")["results"][0]["name"] == "technical-debt"
    print("ok  confluence supporting reads (child pages, ancestors, attachments, labels)")


def test_server_imports():
    import server  # noqa: F401
    print("ok  server imports cleanly")


if __name__ == "__main__":
    test_get_page_versions()
    test_get_page_version()
    test_supporting_reads()
    test_server_imports()
    print("\nAll smoke tests passed.")
