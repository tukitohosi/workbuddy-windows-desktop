"""Install this connector under the Chinese WorkBuddy user profile."""
import contextlib
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from uuid import uuid4


NAME = "windows-desktop-control"
MARKER = ".workbuddy-connector-owner"
OWNER = b"workbuddy/windows-desktop-control/1\n"
V1_FILES = ("server.py", "desktop.ps1")
V11_FILES = (*V1_FILES, "status_overlay.py")
V12_FILES = (*V11_FILES, "pointer_effects.py", "edge_glow.py")
FILES = (*V12_FILES, "execution.py")
KNOWN_RELEASES = (FILES, V12_FILES, V11_FILES, V1_FILES)
FLAGS = ["-I", "-B", "-u"]
BOM = b"\xef\xbb\xbf"


def checked(path):
    if os.path.lexists(path) and path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f"Unexpected linked item: {path.name}")
    return path


@contextlib.contextmanager
def install_lock(root):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    mutex = kernel.CreateMutexW
    mutex.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    mutex.restype = wintypes.HANDLE
    key = hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()
    handle = mutex(None, False, "Local\\WorkBuddyDesktop-" + key)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    handle = wintypes.HANDLE(handle)
    try:
        if kernel.WaitForSingleObject(handle, 15000) not in (0, 128):
            raise ValueError("Another install or uninstall is running.")
        try:
            yield
        finally:
            kernel.ReleaseMutex(handle)
    finally:
        kernel.CloseHandle(handle)


def unique_object(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError("Existing configuration has duplicate JSON keys.")
    return obj


def snapshot(path):
    return path.read_bytes() if path.exists() else None


class ConfigChanged(Exception):
    """The external editor won; read its state again before merging our change."""


def exchange_config(path, staged):
    # Ask Windows for the actual displaced file, including a revision written
    # by another process after our last read. ReplaceFile also preserves ACLs.
    backup = path.with_name(".mcp-recovery-" + uuid4().hex + ".json")
    replace = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
    replace.argtypes = [wintypes.LPCWSTR] * 3 + [wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p]
    if not replace(str(path), str(staged), str(backup), 0, None, None):
        err = ctypes.get_last_error()
        if backup.exists():
            raise OSError(f"Configuration replacement failed. Previous data retained at {backup}")
        raise ctypes.WinError(err)
    return backup


def restore_concurrent_save(path, displaced, installed):
    # Retry only if our own speculative write is still current. If a second
    # writer races our rollback, keep both external revisions for recovery;
    # each writer might have independently changed a different connector.
    if snapshot(path) != installed:
        raise ValueError(f"Multiple concurrent saves. Live configuration preserved; review {displaced}.")
    try:
        recovered = exchange_config(path, displaced)
    except OSError as exc:
        raise OSError(f"Configuration recovery interrupted. Check {displaced}. {exc}") from exc
    if recovered.read_bytes() != installed:
        raise ValueError(f"Concurrent save during recovery. Both revisions retained: {path} and {recovered}.")
    recovered.unlink()
    raise ConfigChanged()


def save_config(path, before, obj):
    encoded = (json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if before and before.startswith(BOM):
        encoded = BOM + encoded
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".mcp-update-", delete=False) as f:
        temp = Path(f.name)
    try:
        temp.write_bytes(encoded)
        if snapshot(path) != before:
            raise ConfigChanged()
        if before is None:
            try:
                os.rename(temp, path)  # Windows refuses overwrite, even if a writer races our check.
            except FileExistsError as exc:
                raise ConfigChanged() from exc
        else:
            previous = exchange_config(path, temp)
            if previous.read_bytes() != before:
                restore_concurrent_save(path, previous, encoded)
            previous.unlink()
    finally:
        temp.unlink(missing_ok=True)


def digest(folder, names=FILES):
    result = hashlib.sha256()
    for name in names:
        data = checked(folder / name).read_bytes()
        result.update(hashlib.sha256(data).digest())
    return result.hexdigest()[:24]


def owned_entry(entry, base):
    if not isinstance(entry, dict) or entry.get("type", "stdio") != "stdio":
        return False
    if not isinstance(entry.get("command"), str) or Path(entry["command"]).name.lower() != "python.exe":
        return False
    args = entry.get("args")
    if not isinstance(args, list) or len(args) != 4 or args[:-1] != FLAGS or not isinstance(args[-1], str):
        return False
    script = Path(args[-1])
    return (script.name == "server.py" and script.parent.parent == base
            and bool(re.fullmatch(r"v-[0-9a-f]{24}", script.parent.name)))


def install_files(base, payload):
    dest = base / ("v-" + digest(payload))
    if checked(dest).exists():
        if digest(dest) != dest.name[2:]:
            raise ValueError("An installed file has changed. Existing files were preserved.")
        return dest
    with tempfile.TemporaryDirectory(dir=base) as scratch:
        staged = Path(scratch) / "release"
        staged.mkdir()
        for name in FILES:
            shutil.copyfile(payload / name, staged / name)
        if digest(staged) != dest.name[2:]:
            raise ValueError("Package contents changed during installation.")
        os.rename(staged, dest)
    return dest


def remove_owned_files(base):
    for folder in base.iterdir():
        if not re.fullmatch(r"v-[0-9a-f]{24}", folder.name) or not checked(folder).is_dir():
            continue
        names = next((release for release in KNOWN_RELEASES
                      if all((folder / name).is_file() for name in release)
                      and digest(folder, release) == folder.name[2:]), None)
        if names is None:
            continue
        for name in names:
            (folder / name).unlink()
        if not any(folder.iterdir()):
            folder.rmdir()
    if set(p.name for p in base.iterdir()) == {MARKER}:
        (base / MARKER).unlink()
        base.rmdir()
    else:
        print("Kept modified or unrecognized files in the connector folder.")


def configure(action, root, payload):
    path = checked(root / "mcp.json")
    base = checked(checked(root / "local-tools") / NAME)
    marker = checked(base / MARKER)
    before = snapshot(path)
    cfg = json.loads(before.decode("utf-8-sig"), object_pairs_hook=unique_object) if before is not None else {}
    if not isinstance(cfg, dict) or not isinstance(cfg.get("mcpServers", {}), dict):
        raise ValueError("Unexpected MCP configuration format.")
    servers = cfg.setdefault("mcpServers", {})
    if base.exists() and (not marker.is_file() or marker.read_bytes() != OWNER):
        raise ValueError("A folder with the same name already exists and belongs to another installation.")
    if NAME in servers and (not base.exists() or not owned_entry(servers[NAME], base)):
        raise ValueError("A connector with this name already exists and is not owned by this installer.")
    if action == "uninstall":
        if NAME in servers:
            del servers[NAME]
            save_config(path, before, cfg)
        if base.exists():
            remove_owned_files(base)
        print("Connector removed from Chinese WorkBuddy.")
        return
    digest(payload)
    if not base.exists():
        base.mkdir(parents=True)
        marker.write_bytes(OWNER)
    dest = install_files(base, payload)
    entry = {**servers.get(NAME, {}), "type": "stdio", "command": sys.executable,
             "args": FLAGS + [str(dest / "server.py")]}
    if servers.get(NAME) != entry:
        servers[NAME] = entry
        save_config(path, before, cfg)
    print("Connector configured in Chinese WorkBuddy: " + NAME)


def apply(action, root, payload):
    if not root.is_dir() or root.name != ".workbuddy":
        raise ValueError("The Chinese WorkBuddy profile (.workbuddy) was not found.")
    with install_lock(root):
        for _ in range(3):
            try:
                configure(action, root, payload)
                return
            except ConfigChanged:
                continue
        raise ValueError("Configuration keeps changing. Please finish the other edit and retry.")


if __name__ == "__main__":
    if sys.platform != "win32" or sys.argv[1:] not in (["install"], ["uninstall"]):
        sys.exit("Use install.ps1 or uninstall.ps1 on Windows.")
    try:
        apply(sys.argv[1], Path.home() / ".workbuddy", Path(__file__).resolve().parent / "payload")
    except (ValueError, OSError) as exc:
        sys.exit("Setup failed: " + str(exc))
