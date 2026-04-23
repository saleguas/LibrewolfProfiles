from __future__ import annotations

import configparser
import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

LIBREWOLF_FLATPAK_APP_ID = 'io.gitlab.librewolf-community'
PROFILE_SECTION_RE = re.compile(r'Profile[0-9]+')
PROFILE_DESCRIPTIONS_DIR = 'librewolf-profiles'
PROFILE_DESCRIPTIONS_FILE = 'descriptions.json'


class BackendError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    path: str
    is_default: bool = False
    description: str = ''


def default_profiles_root(app_id: str) -> Path:
    return Path.home() / '.var' / 'app' / app_id / '.librewolf'


def default_state_root() -> Path:
    configured_root = os.environ.get('XDG_CONFIG_HOME')
    if configured_root:
        return Path(configured_root).expanduser()

    return Path.home() / '.config'


def default_profile_descriptions_path() -> Path:
    return default_state_root() / PROFILE_DESCRIPTIONS_DIR / PROFILE_DESCRIPTIONS_FILE


def parse_profiles_ini(text: str) -> list[Profile]:
    parser = configparser.RawConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read_string(text)

    install_defaults = {
        parser.get(section, 'Default', fallback='').strip()
        for section in parser.sections()
        if section.startswith('Install')
    }

    profiles: list[Profile] = []
    for section in parser.sections():
        if not PROFILE_SECTION_RE.fullmatch(section):
            continue

        name = parser.get(section, 'Name', fallback='').strip()
        path = parser.get(section, 'Path', fallback='').strip()
        if not name or not path:
            continue

        is_default = parser.getboolean(section, 'Default', fallback=False) or path in install_defaults
        profiles.append(Profile(name=name, path=path, is_default=is_default))

    return sorted(profiles, key=lambda item: item.name.casefold())


class ProfileDescriptionStore:
    def __init__(self, storage_path: Path | None = None) -> None:
        configured_path = os.environ.get('LIBREWOLF_PROFILES_DESCRIPTIONS_FILE')
        if storage_path is not None:
            self.storage_path = storage_path
        elif configured_path:
            self.storage_path = Path(configured_path).expanduser()
        else:
            self.storage_path = default_profile_descriptions_path()

        self._descriptions = self._load()

    def get(self, profile_path: str) -> str:
        return self._descriptions.get(profile_path, '')

    def set(self, profile_path: str, description: str) -> None:
        if description.strip():
            self._descriptions[profile_path] = description
        else:
            self._descriptions.pop(profile_path, None)

        self._save()

    def _load(self) -> dict[str, str]:
        if not self.storage_path.exists():
            return {}

        try:
            payload = json.loads(self.storage_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError) as exc:
            raise BackendError(f'Unable to read saved profile descriptions: {self.storage_path}') from exc

        if not isinstance(payload, dict):
            raise BackendError(f'Invalid profile descriptions file: {self.storage_path}')

        descriptions: dict[str, str] = {}
        for key, value in payload.items():
            if isinstance(key, str) and isinstance(value, str):
                descriptions[key] = value

        return descriptions

    def _save(self) -> None:
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.storage_path.with_suffix('.tmp')
            content = json.dumps(self._descriptions, indent=2, sort_keys=True)
            temp_path.write_text(f'{content}\n', encoding='utf-8')
            temp_path.replace(self.storage_path)
        except OSError as exc:
            raise BackendError(f'Unable to save profile descriptions: {self.storage_path}') from exc


class LibreWolfBackend:
    def __init__(self) -> None:
        self.librewolf_app_id = os.environ.get('LIBREWOLF_FLATPAK_APP_ID', LIBREWOLF_FLATPAK_APP_ID)

        configured_root = os.environ.get('LIBREWOLF_PROFILES_ROOT')
        if configured_root:
            self.profiles_root = Path(configured_root).expanduser()
        else:
            self.profiles_root = default_profiles_root(self.librewolf_app_id)

        configured_ini = os.environ.get('LIBREWOLF_PROFILES_INI')
        self.profiles_ini = Path(configured_ini).expanduser() if configured_ini else self.profiles_root / 'profiles.ini'

        self.in_flatpak = Path('/.flatpak-info').exists()
        self.description_store = ProfileDescriptionStore()

    def load_profiles(self) -> list[Profile]:
        profiles = parse_profiles_ini(self.read_profiles_ini())
        return [
            replace(profile, description=self.description_store.get(profile.path))
            for profile in profiles
        ]

    def save_profile_description(self, profile: Profile, description: str) -> None:
        self.description_store.set(profile.path, description)

    def read_profiles_ini(self) -> str:
        if self.in_flatpak:
            return self.run_host(['cat', str(self.profiles_ini)])

        if not self.profiles_ini.exists():
            raise BackendError(f'LibreWolf profiles file not found: {self.profiles_ini}')

        return self.profiles_ini.read_text(encoding='utf-8')

    def create_profile(self, name: str) -> None:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise BackendError('Profile name cannot be empty.')

        self.ensure_librewolf_available()
        self.run_host(['flatpak', 'run', self.librewolf_app_id, '-CreateProfile', cleaned_name])

    def open_profile_manager(self) -> None:
        self.ensure_librewolf_available()
        self.spawn_host(
            [
                'bash',
                '-lc',
                'exec flatpak run "$1" --new-instance --ProfileManager',
                'bash',
                self.librewolf_app_id,
            ]
        )

    def launch_profile(self, profile_name: str) -> None:
        cleaned_name = profile_name.strip()
        if not cleaned_name:
            raise BackendError('Profile name cannot be empty.')

        self.ensure_librewolf_available()
        self.spawn_host(
            [
                'bash',
                '-lc',
                'flatpak run "$1" --new-instance -P "$2" || exec flatpak run "$1" -P "$2"',
                'bash',
                self.librewolf_app_id,
                cleaned_name,
            ]
        )

    def ensure_librewolf_available(self) -> None:
        self.run_host(['flatpak', 'info', self.librewolf_app_id])

    def run_host(self, args: list[str]) -> str:
        command = self._host_prefix() + args

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise BackendError(self._missing_command_message(args[0])) from exc
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or '').strip()
            pretty_command = ' '.join(shlex.quote(part) for part in args)
            raise BackendError(message or f'Command failed: {pretty_command}') from exc

        return completed.stdout

    def spawn_host(self, args: list[str]) -> None:
        command = self._host_prefix() + args

        try:
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise BackendError(self._missing_command_message(args[0])) from exc

    def _host_prefix(self) -> list[str]:
        if not self.in_flatpak:
            return []

        flatpak_spawn = shutil.which('flatpak-spawn')
        if not flatpak_spawn:
            raise BackendError('flatpak-spawn is required inside the Flatpak sandbox.')

        return [flatpak_spawn, '--host']

    def _missing_command_message(self, command_name: str) -> str:
        if command_name == 'flatpak':
            return 'The flatpak command is required to control LibreWolf but was not found.'

        return f'Required command not found: {command_name}'
