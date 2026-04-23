from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from librewolf_profiles.backend import (
    BackendSettings,
    LibreWolfBackend,
    Profile,
    ProfileDescriptionStore,
    SettingsStore,
    default_profile_descriptions_path,
    default_native_profiles_ini,
    default_profiles_root,
    default_settings_path,
    parse_profiles_ini,
)


SAMPLE_PROFILES_INI = """\
[Profile3]
Name=yt_funnybug
IsRelative=1
Path=oj32391k.yt_funnybug

[Profile2]
Name=TaoriLLC
IsRelative=1
Path=ofw4tqvf.TaoriLLC

[InstallAA67A15BF0F93AE3]
Default=jr8d867f.default-default
Locked=1

[Profile1]
Name=default
IsRelative=1
Path=e7siv8hw.default
Default=1

[Profile0]
Name=main
IsRelative=1
Path=jr8d867f.default-default

[General]
StartWithLastProfile=0
Version=2
"""


class ParseProfilesIniTests(unittest.TestCase):
    def test_parse_profiles(self) -> None:
        profiles = parse_profiles_ini(SAMPLE_PROFILES_INI)

        self.assertEqual([profile.name for profile in profiles], ['default', 'main', 'TaoriLLC', 'yt_funnybug'])
        self.assertEqual([profile.name for profile in profiles if profile.is_default], ['default', 'main'])
        self.assertTrue(all(profile.description == '' for profile in profiles))

    def test_default_profiles_root(self) -> None:
        path = default_profiles_root('io.gitlab.librewolf-community')
        self.assertTrue(str(path).endswith('/.var/app/io.gitlab.librewolf-community/.librewolf'))

    def test_default_profile_descriptions_path(self) -> None:
        path = default_profile_descriptions_path()
        self.assertEqual(path.name, 'descriptions.json')
        self.assertEqual(path.parent.name, 'librewolf-profiles')

    def test_default_native_profiles_ini(self) -> None:
        path = default_native_profiles_ini()
        self.assertTrue(str(path).endswith('/.librewolf/profiles.ini'))

    def test_default_settings_path(self) -> None:
        path = default_settings_path()
        self.assertEqual(path.name, 'settings.json')
        self.assertEqual(path.parent.name, 'librewolf-profiles')

    def test_profile_description_store_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / 'descriptions.json'
            store = ProfileDescriptionStore(storage_path=storage_path)

            profile = Profile(name='main', path='jr8d867f.default-default')
            store.set(profile.path, 'Main browsing profile')

            reloaded_store = ProfileDescriptionStore(storage_path=storage_path)
            self.assertEqual(reloaded_store.get(profile.path), 'Main browsing profile')

            reloaded_store.set(profile.path, '   ')
            cleared_store = ProfileDescriptionStore(storage_path=storage_path)
            self.assertEqual(cleared_store.get(profile.path), '')

    def test_settings_store_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / 'settings.json'
            store = SettingsStore(storage_path=storage_path)
            settings = BackendSettings(
                librewolf_command='flatpak run io.gitlab.librewolf-community',
                profiles_ini='~/custom/profiles.ini',
            )

            store.save(settings)
            reloaded_store = SettingsStore(storage_path=storage_path)
            self.assertEqual(reloaded_store.load(), settings)

    def test_resolve_configuration_prefers_detected_flatpak(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                'LIBREWOLF_PROFILES_SETTINGS_FILE': str(Path(temp_dir) / 'settings.json'),
                'LIBREWOLF_PROFILES_DESCRIPTIONS_FILE': str(Path(temp_dir) / 'descriptions.json'),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                backend = LibreWolfBackend()

            with mock.patch.object(
                backend,
                '_list_flatpak_applications',
                return_value=['io.gitlab.librewolf-community'],
            ):
                config = backend.resolve_configuration()

            self.assertEqual(config.launcher.args, ('flatpak', 'run', 'io.gitlab.librewolf-community'))
            self.assertEqual(config.launcher.flatpak_app_id, 'io.gitlab.librewolf-community')
            self.assertEqual(config.launcher.source, 'auto-detected Flatpak install')
            self.assertTrue(str(config.profiles_ini).endswith('/.var/app/io.gitlab.librewolf-community/.librewolf/profiles.ini'))

    def test_resolve_configuration_supports_command_and_profiles_override(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                'LIBREWOLF_PROFILES_SETTINGS_FILE': str(Path(temp_dir) / 'settings.json'),
                'LIBREWOLF_PROFILES_DESCRIPTIONS_FILE': str(Path(temp_dir) / 'descriptions.json'),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                backend = LibreWolfBackend()

            config = backend.resolve_configuration(
                BackendSettings(
                    librewolf_command='flatpak run io.example.CustomLibreWolf',
                    profiles_ini='~/custom/profiles.ini',
                )
            )

            self.assertEqual(config.launcher.args, ('flatpak', 'run', 'io.example.CustomLibreWolf'))
            self.assertEqual(config.launcher.flatpak_app_id, 'io.example.CustomLibreWolf')
            self.assertEqual(config.launcher.source, 'settings override')
            self.assertEqual(config.profiles_source, 'settings override')
            self.assertTrue(str(config.profiles_ini).endswith('/custom/profiles.ini'))

    def test_resolve_configuration_falls_back_to_native_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                'LIBREWOLF_PROFILES_SETTINGS_FILE': str(Path(temp_dir) / 'settings.json'),
                'LIBREWOLF_PROFILES_DESCRIPTIONS_FILE': str(Path(temp_dir) / 'descriptions.json'),
            }
            with mock.patch.dict(os.environ, env, clear=False):
                backend = LibreWolfBackend()

            with mock.patch.object(backend, '_list_flatpak_applications', return_value=[]):
                with mock.patch.object(backend, '_auto_detect_native_command', return_value='/usr/bin/librewolf'):
                    config = backend.resolve_configuration()

            self.assertEqual(config.launcher.args, ('/usr/bin/librewolf',))
            self.assertEqual(config.launcher.source, 'auto-detected system command')
            self.assertEqual(config.profiles_ini, default_native_profiles_ini())


if __name__ == '__main__':
    unittest.main()
