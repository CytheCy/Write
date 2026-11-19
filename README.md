# Write

A small native notepad for Markdown and plain text, designed for Fedora KDE.

## Install on Fedora KDE

Once a Write release is published, download its `.noarch.rpm` from the
[latest release](https://github.com/CytheCy/Write/releases/latest), then install it on Fedora 44:

```bash
sudo dnf install ./write-app-1.0.7-1.fc44.noarch.rpm
```

DNF installs the required dependencies. Launch **Write** from the application menu
or run `write-app [note.md]`. Check the version with `write-app --version`.
Remove the RPM with `sudo dnf remove write-app`. The launcher is named
`write-app` to avoid colliding with the Linux `write` command.

The bundled `write.svg` is the app's typewriter-key W icon. Both the source
installer and RPM install it as `write` in the hicolor icon theme; the app and
update installer also load the bundled SVG directly for their window icons.

Once installed from an RPM, open **Settings → Updates…** to check GitHub Releases.
Write downloads the matching RPM only when you select **Install Update**, verifies
its SHA-256 checksum and RPM signature against the bundled release key, then asks
Polkit for authorization to run a DNF5 upgrade. Save or discard any unsaved note
when prompted. A separate installer shows the transaction result and offers to
restart Write. If the release is unsigned, its key is wrong, or its RPM is older,
the update is refused. Source installations do not support in-app RPM updates.

Write uses its own settings at `~/.config/Write/Write.conf` and starts with
fresh preferences. Existing notes can be opened directly. Subsequent Write
upgrades preserve settings, themes, recent files, personal spelling words,
and user notes. Future settings format changes must use a versioned migration,
back up the affected XDG files first, and continue to read older values.

If you previously used `install.sh`, its per-user launcher and desktop entry
take precedence over the RPM. Remove those generated files when switching:

```bash
rm -f ~/.local/bin/write-app ~/.local/share/applications/write.desktop
```

### Install from source

```bash
bash install.sh
```

The installer creates a local virtual environment and adds Write to the KDE application menu. It also registers it as an option for `.md` and `.txt` files. To run directly from this checkout instead:

```bash
python3 main.py [note.md]
```

Use **File → Open…** to open a note, or drag a file onto the editor. Markdown source stays directly editable while headings, emphasis, code, links, lists, and quotes receive visual styling. Heading `#` markers stay hidden until you click or move the cursor onto that line, and hide again when you leave it. Empty headings keep their `#` visible.

On launch, Write reopens the last file you opened or saved. Opening a note through your file manager opens that note instead.

Click a Markdown link's label or a web address in the text to open it in your system's default browser. Drag to select text, or hold Shift while clicking to place the cursor without opening the link. Addresses inside code spans and fenced code blocks stay as editable code.

Start a bullet with `- `, `* `, or `+ ` at the beginning of a line. Inactive bullet lines show an indented dot; the Markdown marker reappears when you move the cursor onto the line. Enter continues the bullet with the same marker; Enter again on an empty bullet ends the list and leaves only one newline in the saved text.

Numbered lists work the same way with markers such as `1. ` or `1) `. Inactive items show an indented number, and Enter continues with the next number. Enter on the empty next item ends the list without adding a blank line to the saved text.

Wrap text in `*single*` or `_single_` markers for italics, and `**double**` or `__double__` markers for bold. The markers hide while the cursor is on another line and reappear for editing when you move onto their line; the saved Markdown retains them.

Single backticks wrap inline code, and triple backticks on separate lines fence a code block. Fenced code appears in a rounded, padded panel. Hover over the panel to reveal the copy icon at the upper right; clicking it copies the code without the fence lines. Inline backticks reappear when you move the cursor onto their line, and both code fences reappear when the cursor is anywhere inside their block. The saved Markdown retains all delimiters.

Type `---` on its own line for a horizontal rule. It appears as a line until you move the cursor onto it, when the editable Markdown source reappears. `***` and `___` work too.

Tables with a header and a delimiter row display as aligned cells with borders. Each delimiter cell needs at least one hyphen; alignment markers such as `:---`, `:-:`, and `--:` control each column. Click a row to edit its Markdown source; the table view returns when you leave the row. Pipes escaped with `\|` or inside inline code stay in their cell. Tab and Shift+Tab move between cells; Tab from the last cell adds a row when needed. Enter at the end of a data row also adds a row. Empty and uneven rows remain editable, and the saved text keeps its original Markdown.

Use **File → Open Recent** to reopen one of your last 10 opened or saved files. The list is remembered across restarts; **Clear Recent** clears it.

Use **File → Reload Document** to reread the current file from disk. If you have unsaved changes, Write asks whether to save, discard, or cancel before reloading.

The toolbar ribbon on the left displays the **Scatchpad** notepad button. Click it to toggle an editable Markdown panel on the left. Scratch notes are saved as metadata in the same Markdown file and stay out of the main document, headings, search, and word count. For example, this block in a Markdown file displays only its contents, starting with `# hi`, in the Scatchpad:

```markdown
---
scratch:# hi
Where are we?
- in
- th
- way
---
```

You can also open the panel and write notes to create the block when saving. Plain text (`.txt`) files display their existing contents literally.

Hover over the **Sort A–Z** ribbon icon to open a menu with **Dictionary**, **Thesaurus**, and **Moby Thesaurus**. Click an item to open its panel on the left; use its close button to dismiss it. Enter a word and press **Enter** or **Search** to look it up in all three sources, then switch panels to compare results. Dictionary shows Merriam-Webster Collegiate definitions, pronunciation, examples, and word history. Thesaurus shows meanings, synonyms, and antonyms. Moby Thesaurus shows its full list of related words without an API key. Click a suggestion or related word to search again.

Choose **Settings → Reference API key files…** (or **API key files…** in a panel) to select the `.txt` files containing your Merriam-Webster Collegiate Dictionary and Thesaurus keys. Only file paths are saved; keys are read when searching. Lookups require an internet connection. Switching back to Scatchpad preserves your scratch notes.

Enable **Settings → Auto-hide toolbar ribbon** to hide it while writing. Move the pointer to the left edge of the document area to reveal it in 0.3 seconds. Like the right heading panel, it waits five seconds after the pointer leaves before sliding closed in about three quarters of a second. Returning to the ribbon cancels the countdown. Disable the option to keep the ribbon visible. Your choice is remembered across restarts.

Markdown notes with two or more `#` headings show a heading panel on the right. Hover over the side panel icon immediately left of Minimize and choose **Hide**, **Narrow**, or **Full**. Narrow shows the first three characters of each heading. Full shows more of each heading and lets you drag the divider to adjust its width. With **Auto Hide** enabled, move the pointer to the right edge of the window to reveal the Narrow or Full panel. After the pointer leaves the panel area, the panel stays open for five seconds before sliding closed. Returning to the panel cancels the countdown. The panel slides open or closed in about three quarters of a second. The same controls are available under **Settings → Heading panel**. Your choices and Full width are remembered across restarts. Click a heading to jump to it in the editor. The icon appears only when there are at least two headings. The list updates as you edit and excludes fenced code. Plain text files do not show the panel.

Spell checking is enabled by default and works offline with an English dictionary.
Misspelled words receive a wavy underline; right-click one for suggestions,
**Ignore for this session**, or **Add to dictionary**. Added words are remembered
across restarts. Corrections can be undone with Ctrl+Z. Markdown code, link
destinations, URLs, and email addresses are skipped. Toggle checking with
**Settings → Spell check (English)**; this preference is also remembered.
Existing installations should rerun `bash install.sh` to install the new dependency.

Use **File → Remove Extra Spaces and ↵** (**Ctrl+\\**) to collapse repeated spaces, remove spaces beside newlines, and collapse consecutive line breaks throughout the note. Empty Markdown headings such as `# ` keep one space after the marker. Tabs are preserved. Undo restores the cleanup in one step.

Use **File → Remove Bullets and Numbering** (**Ctrl+/**) to remove Markdown list markers while keeping each item's text. Fenced code and horizontal rules are preserved. Undo restores the markers in one step.

Each newline displays as a paragraph break with extra space after it. Adjust the gap in **Settings → Paragraph spacing…**. This changes the display only; saved files keep their original newlines.

Use **Settings → Font size…** to choose a text size from 6 to 72 points. **Ctrl++** (or **Ctrl+=**) increases the size by one point; **Ctrl+-** decreases it. Markdown headings scale with the text. Font size, paragraph spacing, and page width are remembered across restarts.

Use **Settings → Max Page Width…** to limit the text page width in pixels (950 px by default). Wider windows add margins on both sides to keep the page centered; narrower windows wrap the text to fit. The setting is remembered across restarts. Set it to **Unlimited** (0) to use the full available width.

Use `Ctrl+N` for a new note, `Ctrl+O` to open a file, `Ctrl+S` to save, and `Ctrl+Shift+S` to save as. Unsaved changes are confirmed before closing or changing files.

The window remembers its size, position, and maximized state when you close it and restores them at the next launch.
On Wayland desktops, Write uses XWayland when available so it can restore the window's position. An explicit `QT_QPA_PLATFORM` setting takes precedence.

## Appearance

Choose **Settings → Themes…** for **Catppuccin Mocha**, **Tokyo Night**,
or **Everforest Dark**. Each option has a miniature color preview and a radio
indicator. Changes apply immediately and save automatically. **System** retains
the previous light/dark appearance based on desktop colors at launch and remains
the default for existing installations.

Themes preserve the document, undo history, cursor, selection, scrolling, and
all typography preferences. Saved colors are applied before the main window is
shown. On KDE, Open uses the desktop portal's native file picker. Other
desktops and Save As use Qt file dialogs. OS-owned window decorations and
file-type icons remain platform controlled.

`themes.py` owns stable identifiers, immutable semantic color maps, the Qt
palette, and application stylesheets. `main.py` uses the same tokens for source
Markdown highlighting and the theme selector. Ordinary prose stays in the body
color; headings, lists, quotes, code, and links receive restrained accents. The
editor remains a source editor: there is no rendered preview, search UI,
tab system, or YAML-specific highlighter. Tokens for these roles are available
without adding those features.

## Validation

Install `requirements.txt` first; no additional test dependencies are needed:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
python3 -m py_compile main.py themes.py spelling.py references.py reference_api.py reference_widgets.py
```

Tests cover token completeness, text contrast, live selection, persistence in a
new process, fallback behavior, source highlighting (including Unicode offsets),
plain text mode, document/undo/selection/scroll preservation, typography, and
BOM/line-ending preservation when saving. Offscreen screenshots of the three
themes and their dialogs are in `artifacts/`; refresh them with
`python3 packaging/capture-screenshots.py`. A real KDE session is still needed
to assess compositor decorations and native desktop interaction.

## Building and releasing an RPM

The packaging scripts build and validate Write RPMs. No GitHub Actions workflow
is included in this checkout; configure CI and release publishing separately.
The updater targets `CytheCy/Write` on GitHub. Create that repository and publish
Write releases there before using in-app updates, or update both release URLs
in `updater.py` and the project links if you choose another repository.

Release tags must match `VERSION` and the version in `packaging/write-app.spec`.
Signing uses `WRITE_SIGNING_KEY`: an ASCII-armored private key matching the
fingerprint of `WRITE-RPM-KEY.asc` (`C9B19CA235736B143AD722578CA2E8B2C40A6C7B`).
The signing script fails if the secret is absent or the key differs. The private
key for this checkout is stored outside the repository in
`~/.local/share/write-release`. Back up that directory securely. Export the key
to a protected file with `gpg --homedir ~/.local/share/write-release --armor
--export-secret-keys`; supply it to `packaging/sign-release.sh` through the
`WRITE_SIGNING_KEY` environment variable or a CI secret. Keep private keys out
of the repository.

Before the key expires, publish an RPM signed by the current key that contains
the replacement public key and an updater that trusts it; then switch the
release secret. Existing installations need this transition to trust updates
signed by a replacement key.

To build and test locally with Podman:

```bash
podman run --rm -v "$PWD:/src:Z" -w /src \
  registry.fedoraproject.org/fedora:44 bash packaging/ci.sh
```

The container checks installation, preservation of settings and notes during
reinstallation, desktop metadata, icon rendering, and the test suite.
Output is written to `dist/`; local builds are unsigned and cannot be used by
the updater until signed with the release key. For a future release, update
`VERSION`, the spec version/changelog, and `CHANGELOG.md`, commit, then push the
commit and its tag. Run `bash packaging/sign-release.sh` with the signing key
configured, then publish the signed RPMs and checksums manually or through CI.
Publish only stable, non-draft GitHub Releases; keep the RPM
name `write-app` and attach the signed architecture RPM plus `SHA256SUMS`. The API
checks `releases/latest` and accepts a matching `noarch`, `x86_64`, or `aarch64`
asset. Existing XDG settings/data/state formats must be read compatibly; if a
format changes, back up user files and apply a versioned migration.

```bash
git tag -a v1.0.7 -m "Write v1.0.7"
git push --atomic origin main v1.0.7
```

The project has not declared a license; RPM metadata records this as
`LicenseRef-Not-Specified` without granting additional rights.
