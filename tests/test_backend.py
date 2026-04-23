from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from librewolf_profiles.backend import (
    Profile,
    ProfileDescriptionStore,
    default_profile_descriptions_path,
    default_profiles_root,
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


if __name__ == '__main__':
    unittest.main()
