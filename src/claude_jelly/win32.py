"""Win32 API 绑定：常量、结构体与函数签名。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_ERASEBKGND = 0x0014
WM_NCHITTEST = 0x0084
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_MOUSELEAVE = 0x02A3
WM_TIMER = 0x0113
WM_HOTKEY = 0x0312
WM_APP_LAUNCHED = 0x8001
WM_NULL = 0x0000

HTCLIENT = 1
HTTRANSPARENT = -1

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008

SW_HIDE = 0
SW_SHOW = 5
SW_SHOWNA = 8
SW_RESTORE = 9

HWND_TOPMOST = ctypes.c_void_p(-1)
HWND_NOTOPMOST = ctypes.c_void_p(-2)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
HOTKEY_ID = 0xBEEF

MF_STRING = 0x0000
MF_POPUP = 0x0010
MF_CHECKED = 0x0008
MF_SEPARATOR = 0x0800
MF_GRAYED = 0x0001
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TPM_NONOTIFY = 0x0080

OFN_FILEMUSTEXIST = 0x00001000
OFN_PATHMUSTEXIST = 0x00000800
OFN_EXPLORER = 0x00080000
OFN_NOCHANGEDIR = 0x00000008


ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
SPI_GETWORKAREA = 0x0030
ERROR_ALREADY_EXISTS = 183

HWND = ctypes.c_void_p
HDC = ctypes.c_void_p
HANDLE = ctypes.c_void_p
HMENU = ctypes.c_void_p
HBITMAP = ctypes.c_void_p
HINSTANCE = ctypes.c_void_p
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
)
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, HWND, ctypes.c_ssize_t)

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
comdlg32 = ctypes.WinDLL("comdlg32", use_last_error=True)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("style", ctypes.c_uint),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
        ("hIconSm", ctypes.c_void_p),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wt.LONG), ("cy", wt.LONG)]


class OPENFILENAMEW(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wt.DWORD),
        ("hwndOwner", HWND),
        ("hInstance", HINSTANCE),
        ("lpstrFilter", wt.LPCWSTR),
        ("lpstrCustomFilter", wt.LPWSTR),
        ("nMaxCustFilter", wt.DWORD),
        ("nFilterIndex", wt.DWORD),
        ("lpstrFile", wt.LPWSTR),
        ("nMaxFile", wt.DWORD),
        ("lpstrFileTitle", wt.LPWSTR),
        ("nMaxFileTitle", wt.DWORD),
        ("lpstrInitialDir", wt.LPCWSTR),
        ("lpstrTitle", wt.LPCWSTR),
        ("Flags", wt.DWORD),
        ("nFileOffset", wt.WORD),
        ("nFileExtension", wt.WORD),
        ("lpstrDefExt", wt.LPCWSTR),
        ("lCustData", wt.LPARAM),
        ("lpfnHook", ctypes.c_void_p),
        ("lpTemplateName", wt.LPCWSTR),
        ("pvReserved", ctypes.c_void_p),
        ("dwReserved", wt.DWORD),
        ("FlagsEx", wt.DWORD),
    ]


def _wide_buffer(text: str, extra: int = 1) -> ctypes.Array:
    """带内嵌 NUL 的宽字符缓冲区（LPWSTR 赋值会在第一个 NUL 截断）。"""
    buf = ctypes.create_unicode_buffer(len(text) + extra)
    for i, ch in enumerate(text):
        buf[i] = ch
    return buf


def pick_image_file(
    owner: int = 0, title: str = "选择图片", initial_dir: str = ""
) -> str:
    """弹出系统文件选择框，返回选中的图片路径；用户取消时返回空串。"""
    file_buf = ctypes.create_unicode_buffer(32768)
    filter_buf = _wide_buffer(
        "图片文件\0*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp\0"
        "所有文件\0*.*\0"
    )
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = owner
    ofn.lpstrFilter = ctypes.cast(filter_buf, wt.LPCWSTR)
    ofn.lpstrFile = ctypes.cast(file_buf, wt.LPWSTR)
    ofn.nMaxFile = len(file_buf)
    ofn.lpstrInitialDir = initial_dir or None
    ofn.lpstrTitle = title
    ofn.lpstrDefExt = "png"
    ofn.Flags = (
        OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_EXPLORER | OFN_NOCHANGEDIR
    )
    if not comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
        return ""
    return file_buf.value


def _setup_win32() -> None:
    u, g, k = user32, gdi32, kernel32

    u.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    u.RegisterClassExW.restype = ctypes.c_ushort

    u.CreateWindowExW.argtypes = [
        ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        HWND, HMENU, HINSTANCE, ctypes.c_void_p,
    ]
    u.CreateWindowExW.restype = HWND

    u.DefWindowProcW.argtypes = [
        HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
    ]
    u.DefWindowProcW.restype = LRESULT

    u.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), HWND, ctypes.c_uint, ctypes.c_uint]
    u.GetMessageW.restype = ctypes.c_int
    u.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
    u.TranslateMessage.restype = wt.BOOL
    u.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
    u.DispatchMessageW.restype = LRESULT

    u.DestroyWindow.argtypes = [HWND]
    u.DestroyWindow.restype = wt.BOOL
    u.PostQuitMessage.argtypes = [ctypes.c_int]
    u.PostMessageW.argtypes = [HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
    u.PostMessageW.restype = wt.BOOL

    u.SetWindowPos.argtypes = [
        HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint,
    ]
    u.SetWindowPos.restype = wt.BOOL
    u.ShowWindow.argtypes = [HWND, ctypes.c_int]
    u.ShowWindow.restype = wt.BOOL
    u.IsWindow.argtypes = [HWND]
    u.IsWindow.restype = wt.BOOL
    u.IsWindowVisible.argtypes = [HWND]
    u.IsWindowVisible.restype = wt.BOOL
    u.IsIconic.argtypes = [HWND]
    u.IsIconic.restype = wt.BOOL
    u.GetForegroundWindow.restype = HWND
    u.SetForegroundWindow.argtypes = [HWND]
    u.SetForegroundWindow.restype = wt.BOOL
    u.BringWindowToTop.argtypes = [HWND]
    u.BringWindowToTop.restype = wt.BOOL
    u.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(wt.DWORD)]
    u.GetWindowThreadProcessId.restype = wt.DWORD
    u.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
    u.AttachThreadInput.restype = wt.BOOL
    u.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
    u.GetCursorPos.restype = wt.BOOL
    u.ScreenToClient.argtypes = [HWND, ctypes.POINTER(wt.POINT)]
    u.ScreenToClient.restype = wt.BOOL
    u.ClientToScreen.argtypes = [HWND, ctypes.POINTER(wt.POINT)]
    u.ClientToScreen.restype = wt.BOOL
    u.GetWindowRect.argtypes = [HWND, ctypes.POINTER(wt.RECT)]
    u.GetWindowRect.restype = wt.BOOL
    u.SetCapture.argtypes = [HWND]
    u.SetCapture.restype = HWND
    u.ReleaseCapture.argtypes = []
    u.ReleaseCapture.restype = wt.BOOL
    u.SetTimer.argtypes = [HWND, ctypes.c_size_t, ctypes.c_uint, ctypes.c_void_p]
    u.SetTimer.restype = ctypes.c_size_t
    u.KillTimer.argtypes = [HWND, ctypes.c_size_t]
    u.KillTimer.restype = wt.BOOL
    u.RegisterHotKey.argtypes = [HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    u.RegisterHotKey.restype = wt.BOOL
    u.UnregisterHotKey.argtypes = [HWND, ctypes.c_int]
    u.UnregisterHotKey.restype = wt.BOOL
    u.RegisterWindowMessageW.argtypes = [ctypes.c_wchar_p]
    u.RegisterWindowMessageW.restype = ctypes.c_uint
    u.EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_ssize_t]
    u.EnumWindows.restype = wt.BOOL
    u.GetClassNameW.argtypes = [HWND, ctypes.c_wchar_p, ctypes.c_int]
    u.GetClassNameW.restype = ctypes.c_int
    u.GetWindowTextW.argtypes = [HWND, ctypes.c_wchar_p, ctypes.c_int]
    u.GetWindowTextW.restype = ctypes.c_int

    u.GetDpiForSystem.argtypes = []
    u.GetDpiForSystem.restype = ctypes.c_uint
    u.SystemParametersInfoW.argtypes = [
        ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint
    ]
    u.SystemParametersInfoW.restype = wt.BOOL
    u.LoadCursorW.argtypes = [HINSTANCE, ctypes.c_void_p]
    u.LoadCursorW.restype = ctypes.c_void_p

    u.CreatePopupMenu.argtypes = []
    u.CreatePopupMenu.restype = HMENU
    u.AppendMenuW.argtypes = [HMENU, ctypes.c_uint, ctypes.c_size_t, ctypes.c_wchar_p]
    u.AppendMenuW.restype = wt.BOOL
    u.TrackPopupMenu.argtypes = [
        HMENU, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        HWND, ctypes.c_void_p,
    ]
    u.TrackPopupMenu.restype = ctypes.c_uint
    u.DestroyMenu.argtypes = [HMENU]
    u.DestroyMenu.restype = wt.BOOL

    u.UpdateLayeredWindow.argtypes = [
        HWND, HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(SIZE), HDC,
        ctypes.POINTER(wt.POINT), wt.DWORD, ctypes.POINTER(BLENDFUNCTION),
        wt.DWORD,
    ]
    u.UpdateLayeredWindow.restype = wt.BOOL

    u.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    u.SetProcessDpiAwarenessContext.restype = wt.BOOL
    u.MessageBoxW.argtypes = [HWND, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
    u.MessageBoxW.restype = ctypes.c_int
    u.SwitchToThisWindow.argtypes = [HWND, wt.BOOL]
    u.SwitchToThisWindow.restype = None

    g.CreateCompatibleDC.argtypes = [HDC]
    g.CreateCompatibleDC.restype = HDC
    g.CreateDIBSection.argtypes = [
        HDC, ctypes.POINTER(BITMAPINFO), ctypes.c_uint,
        ctypes.POINTER(ctypes.c_void_p), HANDLE, wt.DWORD,
    ]
    g.CreateDIBSection.restype = HBITMAP
    g.SelectObject.argtypes = [HDC, HANDLE]
    g.SelectObject.restype = HANDLE
    g.DeleteObject.argtypes = [HANDLE]
    g.DeleteObject.restype = wt.BOOL
    g.DeleteDC.argtypes = [HDC]
    g.DeleteDC.restype = wt.BOOL

    k.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    k.GetModuleHandleW.restype = ctypes.c_void_p
    k.GetCurrentThreadId.argtypes = []
    k.GetCurrentThreadId.restype = wt.DWORD
    k.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, ctypes.c_wchar_p]
    k.CreateMutexW.restype = ctypes.c_void_p

    comdlg32.GetOpenFileNameW.argtypes = [ctypes.POINTER(OPENFILENAMEW)]
    comdlg32.GetOpenFileNameW.restype = wt.BOOL


_setup_win32()
