"""Small GTK fixture used for optional live Linux AT-SPI acceptance."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


window = Gtk.Window(title="Open RPA AT-SPI Acceptance Fixture")
window.set_default_size(420, 140)
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=16)
window.add(box)
status = Gtk.Label(label="Ready")
status.set_name("StatusLabel")
status.get_accessible().set_name("Status")
entry = Gtk.Entry()
entry.set_name("OrganisationEntry")
entry.get_accessible().set_name("Organisation")
entry.set_placeholder_text("Organisation")
password = Gtk.Entry()
password.set_visibility(False)
password.set_name("PasswordEntry")
password.get_accessible().set_name("Password")
button = Gtk.Button(label="Save")
button.set_name("SaveButton")
button.connect("clicked", lambda *_args: status.set_text("Saved " + entry.get_text()))
box.pack_start(status, False, False, 0)
box.pack_start(entry, False, False, 0)
box.pack_start(password, False, False, 0)
box.pack_start(button, False, False, 0)
window.connect("destroy", Gtk.main_quit)
window.show_all()
Gtk.main()
