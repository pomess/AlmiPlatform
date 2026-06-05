"""Tests for the virtual filesystem."""

from __future__ import annotations

from atlas_runtime.research.filesystem import (
    VirtualFS,
    make_read_file_tool,
    make_write_file_tool,
)
from atlas_runtime.research.url_whitelist import URLWhitelist


def test_vfs_isolation():
    """Two VFS instances are fully isolated."""
    vfs1 = VirtualFS()
    vfs2 = VirtualFS()

    vfs1.write("/findings.md", "content from run 1")
    vfs2.write("/findings.md", "content from run 2")

    assert vfs1.read("/findings.md") == "content from run 1"
    assert vfs2.read("/findings.md") == "content from run 2"


def test_vfs_write_returns_pointer():
    vfs = VirtualFS()
    pointer = vfs.write("/findings_test.md", "Some content https://example.com here")

    assert "[artifact:/findings_test.md]" in pointer
    assert "1 sources" in pointer


def test_vfs_read_nonexistent():
    vfs = VirtualFS()
    assert vfs.read("/nonexistent.md") == ""


def test_vfs_list_files():
    vfs = VirtualFS()
    vfs.write("/a.md", "aaa")
    vfs.write("/b.md", "bbb")

    files = vfs.list_files()
    assert "/a.md" in files
    assert "/b.md" in files


def test_write_file_tool():
    vfs = VirtualFS()
    write_calls: list[tuple[str, int]] = []

    def _on_write(path: str, tokens: int) -> None:
        write_calls.append((path, tokens))

    tool = make_write_file_tool(vfs, agent_name="test", on_write=_on_write)

    result = tool.invoke({"name": "findings_react", "content": "React is a UI library https://react.dev"})

    assert "[artifact:" in result
    assert vfs.has("/findings_react.md")
    assert len(write_calls) == 1
    assert write_calls[0][0] == "/findings_react.md"


def test_write_file_tool_adds_md_extension():
    vfs = VirtualFS()
    tool = make_write_file_tool(vfs)

    tool.invoke({"name": "test", "content": "hello"})
    assert vfs.has("/test.md")


def test_read_file_tool():
    vfs = VirtualFS()
    vfs.write("/data.md", "some data")
    tool = make_read_file_tool(vfs)

    result = tool.invoke({"path": "/data.md"})
    assert result == "some data"


def test_read_file_tool_not_found():
    vfs = VirtualFS()
    tool = make_read_file_tool(vfs)

    result = tool.invoke({"path": "/missing.md"})
    assert "File not found" in result


def test_write_file_tool_rejects_non_whitelisted_urls():
    """Body containing a URL not in the whitelist is rejected, no write occurs."""
    vfs = VirtualFS()
    whitelist = URLWhitelist()
    whitelist.add("https://real.example.com/")

    tool = make_write_file_tool(vfs, whitelist=whitelist)

    result = tool.invoke(
        {
            "name": "findings_x",
            "content": (
                "## Findings\nThe answer is 42 [1].\n"
                "## Sources\n[1] https://invented.example.com/page\n"
            ),
        }
    )

    assert "Cannot write" in result
    assert "https://invented.example.com/page" in result
    # File MUST NOT have been written.
    assert not vfs.has("/findings_x.md")


def test_write_file_tool_accepts_when_all_urls_whitelisted():
    vfs = VirtualFS()
    whitelist = URLWhitelist()
    whitelist.add("https://real.example.com/page")
    whitelist.add("https://other.example.com/article")

    tool = make_write_file_tool(vfs, whitelist=whitelist)

    body = (
        "## Findings\nFoo [1] and bar [2].\n"
        "## Sources\n"
        "[1] https://real.example.com/page\n"
        "[2] https://other.example.com/article\n"
    )
    result = tool.invoke({"name": "findings_x", "content": body})

    assert "[artifact:" in result
    assert vfs.has("/findings_x.md")


def test_write_file_tool_no_whitelist_is_permissive():
    """Back-compat: tests that don't pass a whitelist write freely."""
    vfs = VirtualFS()
    tool = make_write_file_tool(vfs, whitelist=None)

    result = tool.invoke(
        {
            "name": "anything",
            "content": "Random URL https://anything.example.com/x",
        }
    )

    assert "[artifact:" in result
    assert vfs.has("/anything.md")
