"""stdio MCP server exposing the ASC CLI commands as tools.

Every call is stateless: the APK is opened, queried and closed per request, the
same as one CLI invocation. Tool functions are plain module-level functions so
they can be tested without the optional ``mcp`` dependency.
"""
import functools

from droidasc.cli import _build_member_find, _format_class_name

DEFAULT_LIMIT = 1000
THREADS = 8


def _join_limited(lines : list, limit : int) -> str:
    if not lines:
        return "(no matches)"
    if limit <= 0 or len(lines) <= limit:
        return "\n".join(lines)
    return "\n".join(lines[:limit]) + (
        f"\n... truncated: showing {limit} of {len(lines)} lines, "
        "narrow the query or raise limit"
    )


def getclass(apk_path : str, class_name : str) -> str:
    """Decompile one class from the APK and return its Java source.

    class_name accepts a Dalvik descriptor (Lcom/poc/Main;) or a Java name (com.poc.Main).
    """
    from droidasc.asc_client.apk_handler import ApkHandler
    from droidasc.asc_client.asc_handler import AscHandler

    dalvik_class = _format_class_name(class_name)
    hit = ApkHandler(apk_path, max_workers=THREADS).get_class_dex(dalvik_class)
    if hit is None:
        raise ValueError(f"Class {dalvik_class} not found in APK.")
    return AscHandler().getclass(hit[1], dalvik_class)


def listclass(apk_path : str, prefix : str | None = None, limit : int = DEFAULT_LIMIT) -> str:
    """List Dalvik class descriptors defined in the APK, one per line.

    prefix filters by package/class prefix (com.poc or Lcom/poc).
    limit caps the returned lines (0 = unlimited).
    """
    from droidasc.asc_client.apk_handler import ApkHandler

    names = ApkHandler(apk_path, max_workers=THREADS).list_classes(prefix)
    return _join_limited(names, limit)


def getmanifest(apk_path : str) -> str:
    """Decode AndroidManifest.xml from the APK and return it as XML."""
    from droidasc.asc_client.manifest_handler import get_manifest_xml

    return get_manifest_xml(apk_path, pretty=True)


def findrefs(
    apk_path : str,
    find_type : str,
    value : str | None = None,
    class_name : str | None = None,
    fuzzy_class : bool = False,
    limit : int = DEFAULT_LIMIT,
) -> str:
    """Find code references across all DEX entries in the APK.

    find_type is one of string / type / method / field.
    value: fuzzy pattern for string/type (required); fuzzy member name for method/field.
    class_name: owner class for method/field (Dalvik or Java name); exact unless fuzzy_class.
    method/field need at least one of value or class_name.
    limit caps the returned lines (0 = unlimited).
    """
    from droidasc.asc_client.apk_handler import ApkHandler

    if find_type in ("string", "type"):
        if not value:
            raise ValueError(f"{find_type} query needs value")
        find = {find_type: value}
    elif find_type in ("method", "field"):
        find = _build_member_find(find_type, class_name, fuzzy_class, value)
    else:
        raise ValueError("find_type must be one of string, type, method, field")

    lines = []
    for _dex_name, dex_lines in ApkHandler(apk_path, max_workers=THREADS).for_each_findrefs(find_type, find):
        lines.extend(dex_lines)
    return _join_limited(lines, limit)


TOOLS = (getclass, listclass, getmanifest, findrefs)


def main():
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError

    def as_tool_error(fn):
        # surface the message to the client; the SDK hides text of unexpected exceptions
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                raise ToolError(str(e)) from e
        return wrapper

    server = MCPServer(
        "droidasc",
        instructions=(
            "Fast on-demand Android APK decompiler. Every tool takes an APK path; "
            "use listclass/findrefs to locate code, then getclass to read it."
        ),
    )
    for fn in TOOLS:
        server.add_tool(as_tool_error(fn), structured_output=False)
    server.run("stdio")


if __name__ == "__main__":
    main()
