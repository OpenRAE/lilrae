"""Windows native handle primitives for project lifecycle ownership."""

from __future__ import annotations

import os
from pathlib import Path

try:
    import msvcrt
except ModuleNotFoundError:
    msvcrt = None

_WIN_DIRECTORY_ACCESS = 0x00100187
_WIN_FILE_ACCESS = 0x00100183
_WIN_SHARE_ALL = 0x00000007
_WIN_OPEN_EXISTING = 3
_WIN_OPEN_IF = 3
_WIN_ROOT_OPEN_FLAGS = 0x02200000
_WIN_OBJECT_CASE_INSENSITIVE = 0x00000040
_WIN_SYNC_OPEN_REPARSE = 0x00200020
_WIN_DIRECTORY_OBJECT = 0x00000001
_WIN_FILE_OBJECT = 0x00000040
_WIN_FILE_ATTRIBUTE_NORMAL = 0x00000080
_WIN_FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400
_WIN_FILE_ATTRIBUTE_TAG_INFO = 9


def _windows_open_root_handle(project_dir: Path) -> int:
    """Open the trusted project root itself, exposing any root reparse point."""

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE

    handle = create_file(
        str(project_dir),
        _WIN_DIRECTORY_ACCESS,
        _WIN_SHARE_ALL,
        None,
        _WIN_OPEN_EXISTING,
        _WIN_ROOT_OPEN_FLAGS,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle in (None, invalid_handle):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(handle)


def _windows_open_relative_handle(
    parent_handle: int, component: str, *, directory: bool, create: bool = True
) -> int:
    """Open or create one child relative to an already-validated directory."""

    import ctypes
    from ctypes import wintypes

    class UnicodeString(ctypes.Structure):
        """Windows UNICODE_STRING used by descriptor-relative opens."""

        _fields_ = [
            ("Length", wintypes.USHORT),
            ("MaximumLength", wintypes.USHORT),
            ("Buffer", wintypes.LPWSTR),
        ]

    class ObjectAttributes(ctypes.Structure):
        """Windows OBJECT_ATTRIBUTES binding for a relative child name."""

        _fields_ = [
            ("Length", wintypes.ULONG),
            ("RootDirectory", wintypes.HANDLE),
            ("ObjectName", ctypes.POINTER(UnicodeString)),
            ("Attributes", wintypes.ULONG),
            ("SecurityDescriptor", wintypes.LPVOID),
            ("SecurityQualityOfService", wintypes.LPVOID),
        ]

    class IoStatusValue(ctypes.Union):
        """Status-or-pointer union embedded in IO_STATUS_BLOCK."""

        _fields_ = [("Status", ctypes.c_long), ("Pointer", wintypes.LPVOID)]

    class IoStatusBlock(ctypes.Structure):
        """Windows IO_STATUS_BLOCK returned by NtCreateFile."""

        _anonymous_ = ("value",)
        _fields_ = [("value", IoStatusValue), ("Information", ctypes.c_size_t)]

    name_buffer = ctypes.create_unicode_buffer(component)
    name_bytes = component.encode("utf-16-le")
    object_name = UnicodeString(
        Length=len(name_bytes),
        MaximumLength=len(name_bytes) + 2,
        Buffer=ctypes.cast(name_buffer, wintypes.LPWSTR),
    )
    attributes = ObjectAttributes(
        Length=ctypes.sizeof(ObjectAttributes),
        RootDirectory=wintypes.HANDLE(parent_handle),
        ObjectName=ctypes.pointer(object_name),
        Attributes=_WIN_OBJECT_CASE_INSENSITIVE,
        SecurityDescriptor=None,
        SecurityQualityOfService=None,
    )
    io_status = IoStatusBlock()
    handle = wintypes.HANDLE()

    ntdll = ctypes.WinDLL("ntdll")
    nt_create_file = ntdll.NtCreateFile
    nt_create_file.argtypes = (
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.DWORD,
        ctypes.POINTER(ObjectAttributes),
        ctypes.POINTER(IoStatusBlock),
        wintypes.LPVOID,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.LPVOID,
        wintypes.ULONG,
    )
    nt_create_file.restype = ctypes.c_long
    object_type = _WIN_DIRECTORY_OBJECT if directory else _WIN_FILE_OBJECT
    options = _WIN_SYNC_OPEN_REPARSE | object_type
    desired_access = _WIN_DIRECTORY_ACCESS if directory else _WIN_FILE_ACCESS
    status = nt_create_file(
        ctypes.byref(handle),
        desired_access,
        ctypes.byref(attributes),
        ctypes.byref(io_status),
        None,
        _WIN_FILE_ATTRIBUTE_NORMAL,
        _WIN_SHARE_ALL,
        _WIN_OPEN_IF if create else 1,  # NT FILE_OPEN opens an existing object only.
        options,
        None,
        0,
    )
    if status < 0:
        rtl_status_to_error = ntdll.RtlNtStatusToDosError
        rtl_status_to_error.argtypes = (ctypes.c_long,)
        rtl_status_to_error.restype = wintypes.ULONG
        raise ctypes.WinError(rtl_status_to_error(status))
    return int(handle.value)


def _windows_reject_reparse_point(handle: int) -> None:
    """Reject symlinks, junctions, and every other Windows reparse object."""

    import ctypes
    from ctypes import wintypes

    class FileAttributeTagInfo(ctypes.Structure):
        """Windows FILE_ATTRIBUTE_TAG_INFO response structure."""

        _fields_ = [
            ("FileAttributes", wintypes.DWORD),
            ("ReparseTag", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_info = kernel32.GetFileInformationByHandleEx
    get_info.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    )
    get_info.restype = wintypes.BOOL
    info = FileAttributeTagInfo()
    if not get_info(
        wintypes.HANDLE(handle),
        _WIN_FILE_ATTRIBUTE_TAG_INFO,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    if info.FileAttributes & _WIN_FILE_ATTRIBUTE_REPARSE_POINT:
        raise OSError("lifecycle lock path contains a reparse point")


def _windows_handle_to_fd(handle: int) -> int:
    """Transfer an owned Windows file handle to a Python descriptor."""

    if msvcrt is None:
        raise OSError("Windows descriptor support is unavailable")
    flags = os.O_RDWR | getattr(os, "O_BINARY", 0)
    return msvcrt.open_osfhandle(handle, flags)


def _windows_close_handle(handle: int) -> None:
    """Close a raw Windows handle that was not transferred to a descriptor."""

    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    if not close_handle(wintypes.HANDLE(handle)):
        raise ctypes.WinError(ctypes.get_last_error())
