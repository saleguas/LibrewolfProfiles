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

KNOWN_LIBREWOLF_FLATPAK_APP_IDS = (
    'io.gitlab.librewolf-community',
)
PROFILE_SECTION_RE = re.compile(r'Profile[0-9]+')
PROFILE_DESCRIPTIONS_DIR = 'librewolf-profiles'
PROFILE_DESCRIPTIONS_FILE = 'descriptions.json'
SETTINGS_FILE = 'settings.json'
SETTINGS_FILE_ENV = 'LIBREWOLF_PROFILES_SETTINGS_FILE'
BROWSER_COMMAND_ENV = 'LIBREWOLF_PROFILES_BROWSER_COMMAND'


class BackendError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    path: str
    is_default: bool = False
    description: str = ''


@dataclass(frozen=True, slots=True)
class BackendSettings:
    librewolf_command: str = ''
    profiles_ini: str = ''


@dataclass(frozen=True, slots=True)
class LauncherSpec:
    args: tuple[str, ...]
    source: str
    flatpak_app_id: str | None = None

    @property
    def summary(self) -> str:
        return ' '.join(shlex.quote(part) for part in self.args)


@dataclass(frozen=True, slots=True)
class ResolvedConfiguration:
    launcher: LauncherSpec
    profiles_ini: Path
    profiles_source: str


def default_profiles_root(app_id: str) -> Path:
    return Path.home() / '.var' / 'app' / app_id / '.librewolf'


def default_native_profiles_ini() -> Path:
    return Path.home() / '.librewolf' / 'profiles.ini'


def default_state_root() -> Path:
    configured_root = os.environ.get('XDG_CONFIG_HOME')
    if configured_root:
        return Path(configured_root).expanduser()

    return Path.home() / '.config'


def default_profile_descriptions_path() -> Path:
    return default_state_root() / PROFILE_DESCRIPTIONS_DIR / PROFILE_DESCRIPTIONS_FILE


def default_settings_path() -> Path:
    return default_state_root() / PROFILE_DESCRIPTIONS_DIR / SETTINGS_FILE


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


class SettingsStore:
    def __init__(self, storage_path: Path | None = None) -> None:
        configured_path = os.environ.get(SETTINGS_FILE_ENV)
        if storage_path is not None:
            self.storage_path = storage_path
        elif configured_path:
            self.storage_path = Path(configured_path).expanduser()
        else:
            self.storage_path = default_settings_path()

        self._settings = self._load()

    def load(self) -> BackendSettings:
        return self._settings

    def save(self, settings: BackendSettings) -> None:
        self._settings = settings
        self._save()

    def _load(self) -> BackendSettings:
        if not self.storage_path.exists():
            return BackendSettings()

        try:
            payload = json.loads(self.storage_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError) as exc:
            raise BackendError(f'Unable to read saved settings: {self.storage_path}') from exc

        if not isinstance(payload, dict):
            raise BackendError(f'Invalid settings file: {self.storage_path}')

        librewolf_command = payload.get('librewolf_command', '')
        profiles_ini = payload.get('profiles_ini', '')

        return BackendSettings(
            librewolf_command=librewolf_command.strip() if isinstance(librewolf_command, str) else '',
            profiles_ini=profiles_ini.strip() if isinstance(profiles_ini, str) else '',
        )

    def _save(self) -> None:
        payload = {
            'librewolf_command': self._settings.librewolf_command,
            'profiles_ini': self._settings.profiles_ini,
        }

        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.storage_path.with_suffix('.tmp')
            content = json.dumps(payload, indent=2, sort_keys=True)
            temp_path.write_text(f'{content}\n', encoding='utf-8')
            temp_path.replace(self.storage_path)
        except OSError as exc:
            raise BackendError(f'Unable to save settings: {self.storage_path}') from exc


class LibreWolfBackend:
    def __init__(self) -> None:
        self.in_flatpak = Path('/.flatpak-info').exists()
        self.host_spawn_available = self._detect_host_spawn()
        self.description_store = ProfileDescriptionStore()
        self.settings_store = SettingsStore()

    def load_settings(self) -> BackendSettings:
        return self.settings_store.load()

    def save_settings(self, librewolf_command: str, profiles_ini: str) -> None:
        self.settings_store.save(
            BackendSettings(
                librewolf_command=librewolf_command.strip(),
                profiles_ini=profiles_ini.strip(),
            )
        )

    def resolve_configuration(self, settings: BackendSettings | None = None) -> ResolvedConfiguration:
        effective_settings = settings if settings is not None else self.load_settings()
        launcher = self._resolve_launcher(effective_settings)
        profiles_ini, profiles_source = self._resolve_profiles_ini(effective_settings, launcher)
        return ResolvedConfiguration(
            launcher=launcher,
            profiles_ini=profiles_ini,
            profiles_source=profiles_source,
        )

    def load_profiles(self) -> tuple[ResolvedConfiguration, list[Profile]]:
        config = self.resolve_configuration()
        profiles = parse_profiles_ini(self.read_profiles_ini(config.profiles_ini))
        return config, [
            replace(profile, description=self.description_store.get(profile.path))
            for profile in profiles
        ]

    def save_profile_description(self, profile: Profile, description: str) -> None:
        self.description_store.set(profile.path, description)

    def read_profiles_ini(self, profiles_ini: Path) -> str:
        if self.in_flatpak:
            if not self.host_file_exists(profiles_ini):
                raise BackendError(f'LibreWolf profiles file not found: {profiles_ini}')

            return self.run_host(['cat', str(profiles_ini)])

        if not profiles_ini.exists():
            raise BackendError(f'LibreWolf profiles file not found: {profiles_ini}')

        return profiles_ini.read_text(encoding='utf-8')

    def create_profile(self, name: str) -> None:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise BackendError('Profile name cannot be empty.')

        config = self.resolve_configuration()
        self.run_host(list(config.launcher.args) + ['-CreateProfile', cleaned_name])

    def open_profile_manager(self) -> None:
        config = self.resolve_configuration()
        self.spawn_browser(config, ['--ProfileManager'], prefer_new_instance=True)

    def launch_profile(self, profile_name: str) -> None:
        cleaned_name = profile_name.strip()
        if not cleaned_name:
            raise BackendError('Profile name cannot be empty.')

        config = self.resolve_configuration()
        self.spawn_browser(config, ['-P', cleaned_name], prefer_new_instance=True)

    def spawn_browser(
        self,
        config: ResolvedConfiguration,
        extra_args: list[str],
        *,
        prefer_new_instance: bool = False,
    ) -> None:
        command = config.launcher.summary
        arguments = ' '.join(shlex.quote(part) for part in extra_args)

        if prefer_new_instance:
            script = (
                f'{command} --new-instance {arguments} >/dev/null 2>&1 || '
                f'exec {command} {arguments}'
            )
            self.spawn_host(['bash', '-lc', script])
            return

        self.spawn_host(list(config.launcher.args) + extra_args)

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

    def host_file_exists(self, path: Path) -> bool:
        if not self.host_spawn_available:
            return path.exists()

        try:
            self.run_host(['bash', '-lc', 'test -f "$1"', 'bash', str(path)])
        except BackendError:
            return False

        return True

    def _resolve_launcher(self, settings: BackendSettings) -> LauncherSpec:
        configured_command = settings.librewolf_command or os.environ.get(BROWSER_COMMAND_ENV, '').strip()
        if configured_command:
            return self._command_launcher(configured_command, 'settings override' if settings.librewolf_command else 'environment override')

        configured_app_id = os.environ.get('LIBREWOLF_FLATPAK_APP_ID', '').strip()
        if configured_app_id:
            return LauncherSpec(
                args=('flatpak', 'run', configured_app_id),
                source='environment override',
                flatpak_app_id=configured_app_id,
            )

        detected_app_id = self._auto_detect_flatpak_app_id()
        if detected_app_id:
            return LauncherSpec(
                args=('flatpak', 'run', detected_app_id),
                source='auto-detected Flatpak install',
                flatpak_app_id=detected_app_id,
            )

        detected_command = self._auto_detect_native_command()
        if detected_command:
            return LauncherSpec(
                args=(detected_command,),
                source='auto-detected system command',
            )

        raise BackendError(
            'LibreWolf was not found. Install LibreWolf or set a custom command in Settings.'
        )

    def _resolve_profiles_ini(
        self,
        settings: BackendSettings,
        launcher: LauncherSpec,
    ) -> tuple[Path, str]:
        if settings.profiles_ini:
            return Path(settings.profiles_ini).expanduser(), 'settings override'

        configured_ini = os.environ.get('LIBREWOLF_PROFILES_INI', '').strip()
        if configured_ini:
            return Path(configured_ini).expanduser(), 'environment override'

        configured_root = os.environ.get('LIBREWOLF_PROFILES_ROOT', '').strip()
        if configured_root:
            return Path(configured_root).expanduser() / 'profiles.ini', 'environment override'

        if launcher.flatpak_app_id:
            return default_profiles_root(launcher.flatpak_app_id) / 'profiles.ini', 'derived from Flatpak install'

        return default_native_profiles_ini(), 'default native location'

    def _command_launcher(self, command_text: str, source: str) -> LauncherSpec:
        try:
            args = tuple(shlex.split(command_text))
        except ValueError as exc:
            raise BackendError(f'Invalid LibreWolf command: {exc}') from exc

        if not args:
            raise BackendError('LibreWolf command cannot be empty.')

        flatpak_app_id = None
        if len(args) >= 3 and args[0] == 'flatpak' and args[1] == 'run':
            flatpak_app_id = args[2]

        return LauncherSpec(args=args, source=source, flatpak_app_id=flatpak_app_id)

    def _auto_detect_flatpak_app_id(self) -> str | None:
        app_ids = self._list_flatpak_applications()
        if not app_ids:
            return None

        for app_id in KNOWN_LIBREWOLF_FLATPAK_APP_IDS:
            if app_id in app_ids:
                return app_id

        matches = sorted(app_id for app_id in app_ids if 'librewolf' in app_id.casefold())
        if matches:
            return matches[0]

        return None

    def _auto_detect_native_command(self) -> str | None:
        for command_name in ('librewolf',):
            command_path = self._host_which(command_name)
            if command_path:
                return command_path

        return None

    def _list_flatpak_applications(self) -> list[str]:
        try:
            output = self.run_host(['flatpak', 'list', '--app', '--columns=application'])
        except BackendError:
            return []

        return [line.strip() for line in output.splitlines() if line.strip()]

    def _host_which(self, command_name: str) -> str | None:
        if not self.host_spawn_available:
            return shutil.which(command_name)

        try:
            resolved = self.run_host(['bash', '-lc', 'command -v "$1"', 'bash', command_name]).strip()
        except BackendError:
            return None

        return resolved or None

    def _host_prefix(self) -> list[str]:
        if not self.host_spawn_available:
            return []

        flatpak_spawn = shutil.which('flatpak-spawn')
        if not flatpak_spawn:
            raise BackendError('flatpak-spawn is required to access the host environment.')

        return [flatpak_spawn, '--host']

    def _detect_host_spawn(self) -> bool:
        flatpak_spawn = shutil.which('flatpak-spawn')
        if not flatpak_spawn:
            return False

        try:
            subprocess.run(
                [flatpak_spawn, '--host', 'true'],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

        return True

    def _missing_command_message(self, command_name: str) -> str:
        if command_name == 'flatpak':
            return 'The flatpak command is required to control LibreWolf but was not found.'

        return f'Required command not found: {command_name}'
