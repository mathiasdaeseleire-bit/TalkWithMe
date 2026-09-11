r"""Installing TalkWithMe properly: a stable home, a Start-menu entry, and
autostart at login.

Running from dist\ inside the build folder works but is fragile — a
rebuild replaces the file underneath a pinned shortcut, and moving the
project breaks it. So install() copies the exe to a per-user location the
way real Windows apps do, and points everything at that copy.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys

from . import autostart
from .icon import save_ico

log = logging.getLogger("talkwithme.install")

APP_NAME = "TalkWithMe"
SAC_POLICY_KEY = r"SYSTEM\CurrentControlSet\Control\CI\Policy"
SAC_VALUE = "VerifiedAndReputablePolicyState"
SAC_OFF, SAC_ON, SAC_EVALUATION = 0, 1, 2


def smart_app_control_state() -> int | None:
    """0 off, 1 on, 2 evaluation, None when the machine has no such policy.

    Smart App Control blocks executables that are neither signed by a
    trusted publisher nor known-good to Microsoft's reputation service. A
    self-built one-file exe is both unsigned and unknown, so it is refused
    outright — and unlike SmartScreen there is no "run anyway" and no
    exclusion list.
    """
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, SAC_POLICY_KEY) as key:
            value, _ = winreg.QueryValueEx(key, SAC_VALUE)
            return int(value)
    except (FileNotFoundError, OSError, ValueError):
        return None


def python_launcher() -> tuple[str, str] | None:
    """The signed pythonw.exe and the project directory to run from.

    The way past Smart App Control without weakening it: python.exe and
    pythonw.exe carry a valid Python Software Foundation signature, so the
    thing Windows is asked to trust is Python itself, which it already
    does. Our code is then just a script that Python reads.
    """
    launcher = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(launcher):
        return None
    project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(os.path.join(project, "talkwithme", "__main__.py")):
        return None
    return launcher, project


def _install_root() -> str:
    r"""Where to put the exe so that Windows can actually find it.

    Installing from inside a packaged (MSIX) host is the trap here. Such a
    host redirects writes under AppData\Local into
    ...\Packages\<app>\LocalCache, and the write appears to succeed: the
    installer reads its own file back happily. Explorer, outside the
    container, sees nothing there. The shortcut then resolves to a missing
    target and shows a blank document icon.

    Detecting the redirection is done by writing a probe and looking for a
    copy of it in the package cache, because the path string itself does
    not change. When redirected, fall back to a folder under the user
    profile that hosts leave alone.
    """
    local = os.environ.get("LOCALAPPDATA", "")
    candidate = os.path.join(local, "Programs") if local else ""
    if candidate and not _is_redirected(candidate):
        return candidate
    return os.path.join(os.path.expanduser("~"), "Documents")


def _is_redirected(folder: str) -> bool:
    packages = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Packages")
    probe = os.path.join(folder, ".talkwithme_probe")
    try:
        os.makedirs(folder, exist_ok=True)
        with open(probe, "w", encoding="ascii") as f:
            f.write("probe")
    except OSError:
        return True
    try:
        for root, _dirs, files in os.walk(packages):
            if ".talkwithme_probe" in files:
                return True
    except OSError:
        pass
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass
    return False


INSTALL_DIR = os.path.join(_install_root(), APP_NAME)
INSTALLED_EXE = os.path.join(INSTALL_DIR, f"{APP_NAME}.exe")
ICON_PATH = os.path.join(INSTALL_DIR, f"{APP_NAME}.ico")
START_MENU_DIR = os.path.join(os.environ.get("APPDATA", ""),
                               r"Microsoft\Windows\Start Menu\Programs")
SHORTCUT_PATH = os.path.join(START_MENU_DIR, f"{APP_NAME}.lnk")


def is_installed() -> bool:
    return os.path.exists(INSTALLED_EXE)


def running_from_install_dir() -> bool:
    if not getattr(sys, "frozen", False):
        return False
    return os.path.normcase(sys.executable) == os.path.normcase(INSTALLED_EXE)


def _create_shortcut(path: str, target: str, icon: str | None = None,
                      description: str = "", arguments: str = "",
                      working_dir: str | None = None) -> None:
    """A .lnk via the Windows Script Host COM object — the only way to make
    a real shortcut without shipping extra dependencies."""
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    link = shell.CreateShortCut(path)
    link.TargetPath = target
    link.Arguments = arguments
    link.WorkingDirectory = working_dir or os.path.dirname(target)
    link.Description = description or f"{APP_NAME} — dicteren met je stem"
    # Point at the icon embedded in the exe rather than a loose .ico:
    # Windows refreshes that reliably, and there is no second file to
    # go missing or fall out of date.
    if icon and os.path.exists(icon):
        link.IconLocation = icon
    else:
        link.IconLocation = f"{target},0"
    link.save()


def install(source_exe: str | None = None) -> str:
    """Copy the exe into place, add a Start-menu entry, enable autostart.
    Returns the installed exe path."""
    source = source_exe or (sys.executable if getattr(sys, "frozen", False) else None)
    if source is None:
        raise RuntimeError(
            "Installeren kan alleen vanaf de gebouwde .exe "
            "(bouw eerst met: pyinstaller talkwithme.spec)")

    os.makedirs(INSTALL_DIR, exist_ok=True)

    if os.path.normcase(source) != os.path.normcase(INSTALLED_EXE):
        # Windows locks a running exe, so a reinstall over a live copy
        # fails; move the old one aside first and let it go on reboot.
        if os.path.exists(INSTALLED_EXE):
            stale = INSTALLED_EXE + ".old"
            try:
                if os.path.exists(stale):
                    os.remove(stale)
                os.replace(INSTALLED_EXE, stale)
            except OSError as e:
                log.warning("kon oude versie niet opzijzetten: %s", e)
        shutil.copy2(source, INSTALLED_EXE)

    try:
        save_ico(ICON_PATH)
    except Exception as e:
        log.warning("kon icoon niet schrijven: %s", e)

    # Smart App Control refuses an unsigned, unknown exe outright: no
    # "run anyway", no exclusion list, and switching it off is permanent.
    # Launching through the signed pythonw.exe sidesteps it without
    # weakening anything, so prefer that when SAC is active.
    launcher = python_launcher() if smart_app_control_state() == SAC_ON else None

    try:
        if launcher:
            pythonw, project = launcher
            _create_shortcut(SHORTCUT_PATH, pythonw, f"{ICON_PATH},0",
                              arguments="-m talkwithme", working_dir=project)
            log.info("Smart App Control staat aan; snelkoppeling gaat via %s", pythonw)
        else:
            _create_shortcut(SHORTCUT_PATH, INSTALLED_EXE, f"{ICON_PATH},0")
    except Exception as e:
        log.warning("kon Start-menu snelkoppeling niet maken: %s", e)

    autostart.enable(launcher)
    return INSTALLED_EXE


def uninstall() -> None:
    autostart.disable()
    for path in (SHORTCUT_PATH, ICON_PATH):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            log.warning("kon %s niet verwijderen: %s", path, e)
