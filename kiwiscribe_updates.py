"""Verificação e instalação de atualizações via GitHub Releases.

Espelha o fluxo do Kiwi-Splitter: no máximo 1 verificação por dia, baixa o
instalador da plataforma atual (.exe no Windows, .deb no Linux) e oferece
instalar. No Linux usa pkexec+apt para substituir o pacote do sistema.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

APP_NAME = "Kiwiscribe"
GITHUB_OWNER = "fgbkiwi"
GITHUB_REPO = "Kiwiscribe"
GITHUB_RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_PAGE = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

UPDATE_STATE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA")
    or os.environ.get("XDG_DATA_HOME")
    or os.path.join(os.path.expanduser("~"), ".local", "share"),
    APP_NAME,
)
UPDATE_CHECK_FILE = os.path.join(UPDATE_STATE_DIR, "update_check.json")

_USER_SHADOW_DESKTOP = "kiwiscribe.desktop"
_USER_SHADOW_MARKERS = (
    "/.local/bin/kiwiscribe",
    "/.local/opt/kiwiscribe",
)


class DebInstallCancelled(Exception):
    """O usuário recusou a senha de administrador ou fechou o diálogo do sistema."""


def parse_version(version: str) -> Tuple[int, ...]:
    cleaned = (version or "").strip().lstrip("vV")
    parts: List[int] = []
    for chunk in cleaned.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def version_is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def load_update_check_state() -> Dict[str, Any]:
    try:
        if os.path.exists(UPDATE_CHECK_FILE):
            with open(UPDATE_CHECK_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def save_update_check_state(state: Dict[str, Any]) -> None:
    try:
        os.makedirs(UPDATE_STATE_DIR, exist_ok=True)
        with open(UPDATE_CHECK_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


def should_check_for_updates_today() -> bool:
    state = load_update_check_state()
    return state.get("last_check_date") != date.today().isoformat()


def mark_update_checked() -> None:
    state = load_update_check_state()
    state["last_check_date"] = date.today().isoformat()
    save_update_check_state(state)


def _installer_suffixes() -> Tuple[str, ...]:
    """Extensão do instalador desta plataforma (o .exe do Windows não serve no Linux)."""
    if sys.platform.startswith("linux"):
        return (".deb",)
    if sys.platform == "darwin":
        return (".dmg", ".pkg")
    return (".exe",)


def _installer_extension() -> str:
    return _installer_suffixes()[0]


def _preferred_arch_tokens() -> Tuple[str, ...]:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return ("amd64", "x86_64", "win64")
    if machine in ("aarch64", "arm64"):
        return ("arm64", "aarch64")
    return (machine,) if machine else ()


def pick_installer_asset(assets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    suffixes = _installer_suffixes()
    named: List[Dict[str, Any]] = []
    fallback: List[Dict[str, Any]] = []
    for asset in assets or []:
        name = str(asset.get("name") or "")
        url = asset.get("browser_download_url")
        if not url:
            continue
        lower = name.lower()
        if not lower.endswith(suffixes):
            continue
        if "kiwiscribe" in lower or "kiwi_scribe" in lower:
            named.append(asset)
        else:
            fallback.append(asset)
    candidates = named or fallback
    if not candidates:
        return None

    arch_tokens = _preferred_arch_tokens()
    other_arch = ("amd64", "arm64", "aarch64", "x86_64", "i386", "win64")

    def _rank(asset: Dict[str, Any]) -> Tuple[int, int, str]:
        name = str(asset.get("name") or "")
        lower = name.lower()
        if arch_tokens and any(token in lower for token in arch_tokens):
            arch_rank = 0
        elif any(token in lower for token in other_arch):
            arch_rank = 2
        else:
            arch_rank = 1
        generic_rank = 0 if ("setup" in lower or "_" in lower or "-" in lower) else 1
        return (arch_rank, generic_rank, name)

    candidates.sort(key=_rank)
    return candidates[0]


def installer_download_dir() -> str:
    """Pasta gravável onde o instalador baixado fica até ser executado."""
    if sys.platform.startswith("linux"):
        cache_root = os.environ.get("XDG_CACHE_HOME") or os.path.join(
            os.path.expanduser("~"), ".cache"
        )
        path = os.path.join(cache_root, "kiwiscribe", "updates")
    else:
        path = os.path.join(tempfile.gettempdir(), "kiwiscribe-updates")
    os.makedirs(path, exist_ok=True)
    return path


def _user_desktop_path(home: str) -> str:
    return os.path.join(home, ".local", "share", "applications", _USER_SHADOW_DESKTOP)


def _desktop_file_shadows_system_package(desktop_path: str) -> bool:
    try:
        with open(desktop_path, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return False
    return any(marker in text for marker in _USER_SHADOW_MARKERS)


def user_local_install_shadows_system(home: Optional[str] = None) -> bool:
    """True quando o atalho em ~/.local aponta para a cópia antiga, e não para /usr/bin."""
    home_path = os.path.abspath(home or os.path.expanduser("~"))
    return _desktop_file_shadows_system_package(_user_desktop_path(home_path))


def retire_user_local_install(home: Optional[str] = None) -> bool:
    """Remove a cópia em ~/.local que o menu prefere ao pacote do sistema."""
    home_path = os.path.abspath(home or os.path.expanduser("~"))
    desktop = _user_desktop_path(home_path)
    if not _desktop_file_shadows_system_package(desktop):
        return False

    try:
        os.remove(desktop)
    except OSError:
        pass

    launcher = os.path.join(home_path, ".local", "bin", "kiwiscribe")
    try:
        with open(launcher, "r", encoding="utf-8", errors="replace") as handle:
            launcher_text = handle.read()
        if "/.local/opt/kiwiscribe" in launcher_text:
            os.remove(launcher)
    except OSError:
        pass

    opt_dir = os.path.join(home_path, ".local", "opt", "kiwiscribe")
    if os.path.isfile(os.path.join(opt_dir, "Kiwiscribe.py")) or os.path.isfile(
        os.path.join(opt_dir, "kiwiscribe_launcher.py")
    ):
        shutil.rmtree(opt_dir, ignore_errors=True)

    icons_root = os.path.join(home_path, ".local", "share", "icons")
    if os.path.isdir(icons_root):
        for dirpath, _dirnames, _filenames in os.walk(icons_root):
            if os.path.basename(dirpath) != "apps":
                continue
            icon = os.path.join(dirpath, "kiwiscribe.png")
            if os.path.isfile(icon):
                try:
                    os.remove(icon)
                except OSError:
                    pass

    applications_dir = os.path.join(home_path, ".local", "share", "applications")
    update_db = shutil.which("update-desktop-database")
    if update_db and os.path.isdir(applications_dir):
        subprocess.run([update_db, "-q", applications_dir], check=False)
    icon_cache = shutil.which("gtk-update-icon-cache")
    hicolor = os.path.join(icons_root, "hicolor")
    if icon_cache and os.path.isdir(hicolor):
        subprocess.run(
            [icon_cache, "-f", "-t", hicolor],
            check=False,
            capture_output=True,
        )
    return True


def install_deb_package(installer_path: str) -> None:
    """Instala o .deb com apt (pkexec). Evita xdg-open, que no Pop!_OS não atualiza o menu."""
    path = os.path.abspath(installer_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    try:
        os.chmod(path, 0o644)
    except OSError:
        pass

    apt = shutil.which("apt-get")
    pkexec = shutil.which("pkexec")
    if not apt or not pkexec:
        raise RuntimeError(
            "Não encontrei apt-get e pkexec para instalar o pacote.\n"
            f"Instale manualmente com:\nsudo apt install {path}"
        )

    proc = subprocess.run(
        [pkexec, apt, "install", "-y", path],
        capture_output=True,
        text=True,
    )
    if proc.returncode in (126, 127):
        raise DebInstallCancelled()
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        if len(detail) > 1200:
            detail = detail[-1200:]
        raise RuntimeError(
            detail or f"A instalação terminou com código {proc.returncode}."
        )


def launch_downloaded_installer(installer_path: str) -> None:
    """Abre o instalador do Windows. No Linux a instalação é install_deb_package."""
    subprocess.Popen([installer_path], shell=False)


class UpdateCheckThread(QThread):
    update_available = pyqtSignal(str, str, str)  # version, filename, download_url
    check_failed = pyqtSignal(str)
    check_finished = pyqtSignal()

    def __init__(self, app_version: str):
        super().__init__()
        self.app_version = app_version

    def run(self):
        checked_ok = False
        try:
            req = urllib.request.Request(
                GITHUB_RELEASES_API,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"{APP_NAME}/{self.app_version}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            checked_ok = True

            remote_version = str(payload.get("tag_name") or payload.get("name") or "").strip()
            if not remote_version:
                return

            asset = pick_installer_asset(payload.get("assets") or [])
            if not asset:
                return

            download_url = str(asset.get("browser_download_url") or "")
            filename = str(
                asset.get("name") or f"{APP_NAME}_{remote_version}{_installer_extension()}"
            )
            if download_url and version_is_newer(remote_version, self.app_version):
                self.update_available.emit(remote_version.lstrip("vV"), filename, download_url)
        except urllib.error.HTTPError as exc:
            # 404 = ainda não há releases publicadas; conta como verificação ok
            if exc.code == 404:
                checked_ok = True
            else:
                self.check_failed.emit(f"Falha ao verificar atualizações (HTTP {exc.code}).")
        except Exception as exc:
            self.check_failed.emit(f"Falha ao verificar atualizações: {exc}")
        finally:
            if checked_ok:
                mark_update_checked()
            self.check_finished.emit()


class InstallerDownloadThread(QThread):
    progress = pyqtSignal(int)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, download_url: str, filename: str, app_version: str):
        super().__init__()
        self.download_url = download_url
        self.filename = filename
        self.app_version = app_version

    def run(self):
        dest_path = ""
        try:
            safe_name = os.path.basename(self.filename) or f"{APP_NAME}-update{_installer_extension()}"
            dest_path = os.path.join(installer_download_dir(), safe_name)
            req = urllib.request.Request(
                self.download_url,
                headers={"User-Agent": f"{APP_NAME}/{self.app_version}"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as out:
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                chunk_size = 1024 * 256
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        self.progress.emit(min(100, int(downloaded * 100 / total)))
                    else:
                        self.progress.emit(-1)
            self.progress.emit(100)
            self.finished_ok.emit(dest_path)
        except Exception as exc:
            try:
                if dest_path and os.path.exists(dest_path):
                    os.remove(dest_path)
            except Exception:
                pass
            self.failed.emit(str(exc))


class DebInstallThread(QThread):
    succeeded = pyqtSignal(bool)  # havia atalho antigo em ~/.local
    failed = pyqtSignal(str, bool)  # mensagem, cancelada

    def __init__(self, installer_path: str):
        super().__init__()
        self.installer_path = installer_path

    def run(self):
        try:
            had_shadow = user_local_install_shadows_system()
            install_deb_package(self.installer_path)
            retire_user_local_install()
            self.succeeded.emit(had_shadow)
        except DebInstallCancelled:
            self.failed.emit("Instalação cancelada.", True)
        except Exception as exc:
            self.failed.emit(str(exc), False)
