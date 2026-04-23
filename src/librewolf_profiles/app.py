from __future__ import annotations

import sys

import gi

from . import APP_ID
from .backend import BackendError, LibreWolfBackend, Profile

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Adw, Gdk, Gio, Gtk, Pango  # noqa: E402


PROFILE_ROW_CSS = """
row.profile-row label.profile-title {
    font-size: 14px;
    font-weight: 600;
}

row.profile-row label.profile-path,
row.profile-row entry.profile-description-entry {
    font-size: 12px;
}

row.profile-row entry.profile-description-entry {
    min-height: 28px;
    padding-top: 2px;
    padding-bottom: 2px;
}

row.profile-row label.profile-badge {
    min-height: 0;
    padding: 1px 6px;
}
"""


def install_css() -> None:
    display = Gdk.Display.get_default()
    if display is None:
        return

    provider = Gtk.CssProvider()
    provider.load_from_data(PROFILE_ROW_CSS.encode('utf-8'))
    Gtk.StyleContext.add_provider_for_display(
        display,
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )


class ProfileRow(Gtk.ListBoxRow):
    def __init__(self, profile: Profile, on_description_changed) -> None:
        super().__init__()
        self.profile = profile
        self._on_description_changed = on_description_changed
        self._description_entry = Gtk.Entry()

        self.set_activatable(False)
        self.set_selectable(True)
        self.add_css_class('profile-row')

        prefix_icon = Gtk.Image.new_from_icon_name('globe-symbolic')
        prefix_icon.set_pixel_size(16)
        prefix_icon.set_margin_start(4)
        prefix_icon.set_margin_end(4)
        prefix_icon.set_valign(Gtk.Align.CENTER)

        title_label = Gtk.Label(xalign=0)
        title_label.set_text(profile.name)
        title_label.add_css_class('profile-title')

        path_label = Gtk.Label(xalign=0)
        path_label.set_text(profile.path)
        path_label.add_css_class('dim-label')
        path_label.add_css_class('profile-path')
        path_label.set_ellipsize(Pango.EllipsizeMode.END)

        identity_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        identity_box.set_hexpand(True)

        title_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        title_line.append(title_label)

        if profile.is_default:
            default_badge = Gtk.Label(label='Default')
            default_badge.add_css_class('accent')
            default_badge.add_css_class('caption')
            default_badge.add_css_class('profile-badge')
            title_line.append(default_badge)

        identity_box.append(title_line)
        identity_box.append(path_label)

        self._description_entry.set_placeholder_text('Add a note for this profile')
        self._description_entry.set_text(profile.description)
        self._description_entry.set_width_chars(12)
        self._description_entry.add_css_class('profile-description-entry')
        self._description_entry.connect('changed', self._description_changed)

        description_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        description_box.set_halign(Gtk.Align.FILL)
        description_box.set_valign(Gtk.Align.CENTER)
        description_box.set_size_request(120, -1)
        description_box.append(self._description_entry)

        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        content_box.set_margin_top(8)
        content_box.set_margin_bottom(8)
        content_box.set_margin_start(8)
        content_box.set_margin_end(8)
        content_box.append(prefix_icon)
        content_box.append(identity_box)
        content_box.append(description_box)

        self.set_child(content_box)

    def _description_changed(self, entry: Gtk.Entry) -> None:
        description = entry.get_text()
        self.profile = Profile(
            name=self.profile.name,
            path=self.profile.path,
            is_default=self.profile.is_default,
            description=description,
        )
        self._on_description_changed(self.profile, description)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app)
        self.backend = LibreWolfBackend()
        self.rows_by_name: dict[str, ProfileRow] = {}

        self.set_title('LibreWolf Profiles')
        self.set_default_size(490, 720)

        header_bar = Adw.HeaderBar()

        create_button = Gtk.Button(label='New Profile')
        create_button.add_css_class('suggested-action')
        create_button.connect('clicked', self._show_create_dialog)
        header_bar.pack_start(create_button)

        refresh_button = Gtk.Button()
        refresh_button.set_icon_name('view-refresh-symbolic')
        refresh_button.set_tooltip_text('Reload profiles')
        refresh_button.connect('clicked', self._refresh_profiles)
        header_bar.pack_start(refresh_button)

        manager_button = Gtk.Button(label='Default Manager')
        manager_button.connect('clicked', self._open_profile_manager)
        header_bar.pack_end(manager_button)

        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        outer_box.set_margin_top(18)
        outer_box.set_margin_bottom(18)
        outer_box.set_margin_start(12)
        outer_box.set_margin_end(12)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.add_css_class('dim-label')
        self.status_label.set_wrap(True)
        outer_box.append(self.status_label)

        self.listbox = Gtk.ListBox()
        self.listbox.add_css_class('boxed-list')
        self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.listbox.connect('selected-rows-changed', self._update_actions)

        scroller = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(self.listbox)
        outer_box.append(scroller)

        action_bar = Gtk.ActionBar()
        self.launch_button = Gtk.Button(label='Launch Profile')
        self.launch_button.add_css_class('suggested-action')
        self.launch_button.set_sensitive(False)
        self.launch_button.connect('clicked', self._launch_selected)
        action_bar.set_center_widget(self.launch_button)
        outer_box.append(action_bar)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(outer_box)

        self.set_content(toolbar_view)
        self._refresh_profiles()

    def _refresh_profiles(self, *_args: object, select_name: str | None = None) -> None:
        self.rows_by_name.clear()

        child = self.listbox.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self.listbox.remove(child)
            child = next_child

        try:
            profiles = self.backend.load_profiles()
        except BackendError as exc:
            self.status_label.set_text(f'Unable to load profiles from {self.backend.profiles_ini}: {exc}')
            self._update_actions()
            return

        default_names = [profile.name for profile in profiles if profile.is_default]
        default_summary = ', '.join(default_names) if default_names else 'none'
        self.status_label.set_text(
            f'Loaded {len(profiles)} profile(s) from {self.backend.profiles_ini}. '
            f'Default profile: {default_summary}.'
        )

        for profile in profiles:
            row = ProfileRow(profile, self._save_profile_description)
            self.rows_by_name[profile.name] = row
            self.listbox.append(row)

        if select_name and select_name in self.rows_by_name:
            self.listbox.select_row(self.rows_by_name[select_name])
        else:
            first_row = self.listbox.get_row_at_index(0)
            if first_row is not None:
                self.listbox.select_row(first_row)

        self._update_actions()

    def _update_actions(self, *_args: object) -> None:
        self.launch_button.set_sensitive(self._selected_profile() is not None)

    def _selected_profile(self) -> Profile | None:
        row = self.listbox.get_selected_row()
        if row is None:
            return None

        return row.profile

    def _launch_selected(self, *_args: object) -> None:
        profile = self._selected_profile()
        if profile is None:
            return

        self._launch_profile(profile.name)

    def _launch_profile(self, profile_name: str) -> None:
        try:
            self.backend.launch_profile(profile_name)
        except BackendError as exc:
            self._show_message('Unable to launch profile', str(exc))
            return

        self.close()

    def _open_profile_manager(self, *_args: object) -> None:
        try:
            self.backend.open_profile_manager()
        except BackendError as exc:
            self._show_message('Unable to open profile manager', str(exc))
            return

        self.close()

    def _save_profile_description(self, profile: Profile, description: str) -> None:
        try:
            self.backend.save_profile_description(profile, description)
        except BackendError as exc:
            self._show_message('Unable to save description', str(exc))

    def _show_create_dialog(self, *_args: object) -> None:
        dialog = Gtk.Dialog(title='Create New Profile', transient_for=self, modal=True)
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        dialog.add_button('Create', Gtk.ResponseType.OK)

        create_button = dialog.get_widget_for_response(Gtk.ResponseType.OK)
        if create_button is not None:
            create_button.add_css_class('suggested-action')

        content_area = dialog.get_content_area()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)

        heading = Gtk.Label(
            label='Choose a name for the new LibreWolf profile.',
            xalign=0,
        )
        heading.set_wrap(True)
        box.append(heading)

        entry = Gtk.Entry()
        entry.set_activates_default(True)
        entry.set_placeholder_text('Profile name')
        box.append(entry)

        content_area.append(box)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.connect('response', self._on_create_response, entry)
        dialog.present()

    def _on_create_response(self, dialog: Gtk.Dialog, response: int, entry: Gtk.Entry) -> None:
        if response != Gtk.ResponseType.OK:
            dialog.destroy()
            return

        profile_name = entry.get_text().strip()
        if not profile_name:
            self._show_message('Profile name required', 'Enter a name before creating the profile.')
            return

        existing = {name.casefold() for name in self.rows_by_name}
        if profile_name.casefold() in existing:
            self._show_message('Profile already exists', f'A LibreWolf profile named "{profile_name}" already exists.')
            return

        dialog.destroy()

        try:
            self.backend.create_profile(profile_name)
        except BackendError as exc:
            self._show_message('Unable to create profile', str(exc))
            return

        self._refresh_profiles(select_name=profile_name)

    def _show_message(self, heading: str, body: str) -> None:
        dialog = Adw.MessageDialog(transient_for=self, heading=heading, body=body)
        dialog.add_response('ok', 'OK')
        dialog.set_default_response('ok')
        dialog.set_close_response('ok')
        dialog.present()


class LibreWolfProfilesApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self) -> None:
        install_css()
        window = self.props.active_window
        if window is None:
            window = MainWindow(self)

        window.present()


def main() -> int:
    app = LibreWolfProfilesApplication()
    return app.run(sys.argv)
