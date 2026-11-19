# Unreleased

- Connect Dictionary, Thesaurus, and Moby Thesaurus side panels to the WordDesk lookup services, with clickable suggestions and related words, API key file settings, and theme-aware results.

# Write v1.0.7

- Use the typewriter-key W icon throughout the app, update installer, desktop launcher, and RPM.

- Establish Write as a separate app with its own launcher, desktop entry, settings, RPM package, update source, and release signing identity.

- Hover over the heading panel icon to choose Hide, Narrow, Full, or Auto Hide. The panel slides open or closed in about 0.75 seconds. Auto Hide reveals it at the right window edge and waits five seconds after the pointer leaves before closing.
- Hover over the document title to copy its path or open its containing folder.
- Remove extra spaces and newlines with one cleanup action.
- Scroll past the end of notes and preserve paragraph spacing when replacing documents.

# Write v1.0.6

- Remember the window's exact size, position, and maximized state, including placement against screen edges. Use XWayland when available to restore positions on Wayland desktops.
- Fix trackpad scrolling while a Markdown line is active.
- Keep unsaved-change detection accurate when display formatting changes Qt's modified flag.

# Write v1.0.5

- Continue the in-app upgrade after the administrator approves the release key.

# Write v1.0.4

- Fix the release checksum list so installed Write versions can verify and install updates.
- Accept checksum lists from older releases when checking future updates.

# Write v1.0.3

- Use the redesigned app icon in the window, desktop launcher, and RPM installer.
- Restore the last open file and use the native KDE file picker.
- Improve heading navigation, themes, tables, font sizing, and editor controls.

# Write v1.0.2

- Fix the Fedora release build for the signed updater.

# Write v1.0.1

- Add a signed, user-initiated RPM updater under Settings → Updates.
- Keep RPM package identity and existing user settings and data unchanged.

# Write v1.0.0

First release of Write, a native Markdown and plain text notepad for Fedora KDE.

- Editable Markdown source with syntax styling and a heading navigation panel.
- Offline English spell checking, suggestions, and a personal dictionary.
- Three built-in themes plus system colors.
- Configurable font size, paragraph spacing, and page width.
- Recent files, drag-and-drop opening, and whitespace cleanup actions.
- Fedora RPM installer with an application menu entry and file associations.

Download the `.noarch.rpm` asset and install it with
`sudo dnf install ./write-app-1.0.0-1.fc44.noarch.rpm`.
DNF installs the required Qt/Python libraries and spelling dictionary.
The `.src.rpm` asset is for rebuilding the package, not installing the app.
