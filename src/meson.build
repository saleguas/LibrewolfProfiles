python.install_sources(
  [
    'librewolf_profiles/__init__.py',
    'librewolf_profiles/app.py',
    'librewolf_profiles/backend.py',
    'librewolf_profiles/main.py',
  ],
  subdir: 'librewolf_profiles',
)

configure_file(
  input: 'io.github.saleguas.librewolfprofiles.in',
  output: 'io.github.saleguas.librewolfprofiles',
  configuration: {
    'PYTHON': python.full_path(),
  },
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)
