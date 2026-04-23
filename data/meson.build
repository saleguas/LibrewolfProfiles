applications_dir = join_paths(get_option('datadir'), 'applications')
icons_dir = join_paths(get_option('datadir'), 'icons', 'hicolor', 'scalable', 'apps')
metainfo_dir = join_paths(get_option('datadir'), 'metainfo')

install_data(
  'io.github.saleguas.librewolfprofiles.desktop',
  install_dir: applications_dir,
)

install_data(
  'io.github.saleguas.librewolfprofiles.metainfo.xml',
  install_dir: metainfo_dir,
)

install_data(
  'icons/hicolor/scalable/apps/io.github.saleguas.librewolfprofiles.svg',
  install_dir: icons_dir,
)
