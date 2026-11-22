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

Once installed from an RPM, open **Settings → Updates** to check GitHub Releases.
Write downloads the matching RPM only when you select **Install Update**, verifies
its SHA-256 checksum and RPM signature against the bundled release key, then asks
Polkit for authorization to run a DNF5 upgrade. Save or discard any unsaved note
when prompted. A separate installer shows the transaction result and offers to
restart Write. If the release is unsigned, its key is wrong, or its RPM is older,
the update is refused. Source installations do not support in-app RPM updates.

Write saves all preferences in `.app/settings.ini` inside the folder selected
as the **Project tree location**. This includes themes, recent files, personal
spelling words, API key file paths, and window layout. Changing that location
copies the active preferences to the new folder; the previous copy remains there.
Only the project folder locator stays in `~/.config/Write/Write.conf` so Write can
find the settings at startup. Existing preferences are migrated automatically,
with a backup in `.app/legacy-settings-v0.ini` and storage version 1 recorded in
the new settings file. Existing notes are preserved. Future settings format
changes must use a versioned migration, back up affected files first, and
continue to read older values.

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

Use **File → Open…** to open a note, or drag files onto the editor. Each note opens in a tab on the top row between File and the window controls. Click a tab to switch documents; each keeps its edits, undo history, selection, scroll position, and scratchpad. Opening an already open file selects its tab. Close a tab with its × button or **Ctrl+W**; unsaved changes prompt you to save, discard, or cancel. **Ctrl+Tab** and **Ctrl+Shift+Tab** cycle through tabs.

Markdown source stays directly editable while headings, emphasis, code, links, lists, and quotes receive visual styling. Heading `#` markers stay hidden until you click or move the cursor onto that line, and hide again when you leave it. Empty headings keep their `#` visible.

On launch, Write reopens the last file you opened or saved. Opening a note through your file manager opens that note instead.

Click a Markdown link's label or a web address in the text to open it in your system's default browser. Drag to select text, or hold Shift while clicking to place the cursor without opening the link. Addresses inside code spans and fenced code blocks stay as editable code.

Start a bullet with `- `, `* `, or `+ ` at the beginning of a line. Inactive bullet lines show an indented dot; the Markdown marker reappears when you move the cursor onto the line. Enter continues the bullet with the same marker; Enter again on an empty bullet ends the list and leaves only one newline in the saved text.

Numbered lists work the same way with markers such as `1. ` or `1) `. Inactive items show an indented number, and Enter continues with the next number. Enter on the empty next item ends the list without adding a blank line to the saved text.

Wrap text in `*single*` or `_single_` markers for italics, and `**double**` or `__double__` markers for bold. The markers hide while the cursor is on another line and reappear for editing when you move onto their line; the saved Markdown retains them.

Single backticks wrap inline code, and triple backticks on separate lines fence a code block. Fenced code appears in a rounded, padded panel. Hover over the panel to reveal the copy icon at the upper right; clicking it copies the code without the fence lines. Inline backticks reappear when you move the cursor onto their line, and both code fences reappear when the cursor is anywhere inside their block. The saved Markdown retains all delimiters.

Type `---` on its own line for a horizontal rule. It appears as a line until you move the cursor onto it, when the editable Markdown source reappears. `***` and `___` work too.

Tables with a header and a delimiter row display as aligned cells with borders. Each delimiter cell needs at least one hyphen; alignment markers such as `:---`, `:-:`, and `--:` control each column. Click a row to edit its Markdown source; the table view returns when you leave the row. Pipes escaped with `\|` or inside inline code stay in their cell. Tab and Shift+Tab move between cells; Tab from the last cell adds a row when needed. Enter at the end of a data row also adds a row. Empty and uneven rows remain editable, and the saved text keeps its original Markdown.

Use **File → Open Recent** to reopen one of your last 10 opened or saved files. The list is remembered across restarts; **Clear Recent** clears it.

Use **Tools → Reload Document** to reread the current file from disk. If you have unsaved changes, Write asks whether to save, discard, or cancel before reloading.

The folder icon at the top of the left ribbon toggles the **Project tree** panel. Choose its root folder in **Settings → General → Project tree location**; your choice is saved across restarts. Expand folders and click a file (or press Enter) to replace the current document. Unsaved changes prompt you to save, discard, or cancel. **Ctrl+click** a file to open it in a new tab, keeping the current document open.

Click the **Search project** magnifying glass below the Project tree icon to search text throughout that folder and its subfolders. Results show collapsible file groups, match counts, and highlighted excerpts. Click an excerpt to open and select its match; use the sort menu to reverse filename order. Search includes unsaved edits in open files, ignores case, and treats the query as literal text. Binary files, symbolic links, and `.git`/`.app` internals are skipped. Broad searches show the first 2,000 matches; refine the query to find more.

The toolbar ribbon on the left displays the **Scatchpad** notepad button. Click it to toggle an editable Markdown panel on the left. Scratch notes are saved as metadata in the same Markdown file and stay out of the main document, headings, in-document search, and word count. For example, this block in a Markdown file displays only its contents, starting with `# hi`, in the Scatchpad:

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

Click the **Dictionary** (A–Z), **Thesaurus**, or **Moby Thesaurus** (whale) ribbon icon to open its panel on the left. Click the same icon again to close the panel, or click another reference icon to switch panels. You can also use the panel’s close button. If text is selected in your document, opening a panel automatically searches for that text in all three sources. You can also enter a word and press **Enter** or **Search** to look it up in all three sources, then switch panels to compare results. Dictionary shows Merriam-Webster Collegiate definitions, pronunciation, examples, and word history. Thesaurus shows meanings, synonyms, and antonyms. Moby Thesaurus shows its full list of related words without an API key. Click a suggestion or related word to search again.

Hover over a word in the document and press **Ctrl+L** to open Dictionary and search for that word. Your text selection and caret stay in place. Hovering over empty space does nothing.

Click the **Tools** icon above Settings for **Find** (**Ctrl+F**), **Replace** (**Ctrl+R**), **Reload Document**, and the text cleanup commands.

Click the **Settings** gear at the bottom of the left ribbon to open a settings window with **Themes**, **Appearance**, **Shortcut Keys**, **Updates**, and **General** tabs. Appearance includes font size, paragraph spacing, page width, and panel visibility. Shortcut Keys lists the available keyboard shortcuts.

Open **Settings → General** to select the `.txt` files containing your Merriam-Webster Collegiate Dictionary and Thesaurus keys directly on the tab. Each file selector shows the saved location and whether the file exists. You can also use **API key files…** in a reference panel. Both locations are saved in the project's `.app/settings.ini` as `keys/dictionary_path` and `keys/thesaurus_path` (empty until selected), and follow your settings when changing the project tree folder. Only file paths are saved; keys are read when searching. Lookups require an internet connection. Switching back to Scatchpad preserves your scratch notes.

Enable **Settings → Appearance → Auto-hide toolbar ribbon** to hide it while writing. Move the pointer to the left edge of the document area to reveal it in 0.3 seconds. Like the right heading panel, it waits five seconds after the pointer leaves before sliding closed in about three quarters of a second. Returning to the ribbon cancels the countdown. Disable the option to keep the ribbon visible. Your choice is remembered across restarts.

Markdown notes with two or more `#` headings show a heading panel on the right. Hover over the side panel icon immediately left of Minimize and choose **Hide**, **Narrow**, or **Full**. Narrow shows the first three characters of each heading. Full shows more of each heading and lets you drag the divider to adjust its width. With **Auto Hide** enabled, move the pointer to the right edge of the window to reveal the Narrow or Full panel. After the pointer leaves the panel area, the panel stays open for five seconds before sliding closed. Returning to the panel cancels the countdown. The panel slides open or closed in about three quarters of a second. The same controls are available under **Settings → Appearance → Heading panel**. Your choices and Full width are remembered across restarts. Click a heading to jump to it in the editor. The icon appears only when there are at least two headings. The list updates as you edit and excludes fenced code. Plain text files do not show the panel.

Spell checking is enabled by default and works offline with an English dictionary.
Misspelled words receive a wavy underline; right-click one for suggestions,
**Ignore for this session**, or **Add to dictionary**. Added words are remembered
across restarts. Corrections can be undone with Ctrl+Z. Markdown code, link
destinations, URLs, and email addresses are skipped. Toggle checking with
**Settings → General → Spell check (English)**; this preference is also remembered.
Existing installations should rerun `bash install.sh` to install the new dependency.

Use **Tools → Remove Extra Spaces and ↵** (**Ctrl+\\**) to collapse repeated spaces, remove spaces beside newlines, and collapse consecutive line breaks throughout the note. Empty Markdown headings such as `# ` keep one space after the marker. Tabs are preserved. Undo restores the cleanup in one step.

Use **Tools → Remove Bullets and Numbering** (**Ctrl+/**) to remove Markdown list markers while keeping each item's text. Fenced code and horizontal rules are preserved. Undo restores the markers in one step.

Each newline displays as a paragraph break with extra space after it. Adjust the gap in **Settings → Appearance → Paragraph spacing**. This changes the display only; saved files keep their original newlines.

Use **Settings → Appearance → Font size** to choose a text size from 6 to 72 points. **Ctrl++** (or **Ctrl+=**) increases the size by one point; **Ctrl+-** decreases it. Markdown headings scale with the text. Font size, paragraph spacing, and page width are remembered across restarts.

Use **Settings → Appearance → Maximum page width** to limit the text page width in pixels (950 px by default). Wider windows add margins on both sides to keep the page centered; narrower windows wrap the text to fit. The setting is remembered across restarts. Set it to **Unlimited** (0) to use the full available width.

Use `Ctrl+N` for a new note, `Ctrl+O` to open a file, `Ctrl+S` to save, and `Ctrl+Shift+S` to save as. Unsaved changes are confirmed before closing a tab, closing the window, or reloading a document.

The window remembers its size, position, and maximized state when you close it and restores them at the next launch.
On Wayland desktops, Write uses XWayland when available so it can restore the window's position. An explicit `QT_QPA_PLATFORM` setting takes precedence.

## Appearance

Choose **Settings → Themes** for **Catppuccin Mocha**, **Tokyo Night**,
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
editor remains a source editor with document tabs and search; there is no
rendered preview or YAML-specific highlighter.

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

Editor performance can be measured separately from the regression suite:

```bash
QT_QPA_PLATFORM=offscreen python3 tests/benchmark_editor.py --output /tmp/write-performance.json
```

The benchmark reports median milliseconds per operation over five samples after
warmup. It measures status updates, clean/dirty source checks, and typing with an
event-loop flush in 6,000- and 60,000-word notes, plus repainting and rebuilding a
120-row, four-column table. Spell checking is disabled and Find is closed to
isolate these paths. Run before and after on the same machine without other test
processes running; offscreen timings do not measure desktop input or compositor
latency. The recorded comparison is in `artifacts/editor-performance.json`.

File switching has a separate benchmark with the project tree open:

```bash
QT_QPA_PLATFORM=offscreen python3 tests/benchmark_file_switching.py --output /tmp/write-switching.json
```

It activates real temporary files through the tree handler and records the
handler time, first completed editor paint, and completion of deferred loading
work. Each result is the median of five samples after a warmup. Cases cover
100, 500, and 5,000 prose paragraphs, a 120-row table, mixed headings and code,
and a 5,000-paragraph document with Find open. Spelling is disabled to isolate
loading. `--root /path/to/checkout` runs the same fixtures against another
version. Run comparisons without competing tests or benchmarks. Results are
recorded in `artifacts/file-switching-performance.json`.

Opening a file prepares its paragraph spacing before attaching the document,
highlights it once, and reuses that pass's heading and panel information. Table
cells prepare on demand for visible rows, then in short background batches;
column widths settle to their exact measurements when preparation finishes.
For notes over 300 paragraphs, heading rows and search matches populate after
the first editor paint. Switching again cancels the previous note's pending
presentation work.

Word totals and saved-source differences are maintained per paragraph, so
ordinary edits only inspect the changed paragraphs. Adding or deleting newlines
also updates saved comparisons for the shifted paragraphs. Saving takes a new
source baseline; undo and manual restoration compare exact text independently
of Qt's display-related modified flag. Table intrinsic widths are cached until
content or appearance changes, and visible cell layouts are reused until their
width or alignment changes.

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

## Kokoro TTS

Click the speaker icon (**Kokoro TTS**) in the left ribbon. Choose an American
or British voice and click **Start** to read from the cursor in the active
document through its end. Playback begins with the first generated chunk while
the rest generates in the background. **Pause** pauses playback and becomes
**Resume**, which continues from the same position using the existing audio.
Generation continues in the background while paused. **Stop** cancels generation and playback;
closing the footer also stops speech. The voice choice is remembered.

Write includes its own speech worker and manages a private Kokoro environment
in its application data directory. It does not launch or require Kokoro Reader
or another speech application. The first Start installs CPU PyTorch and Kokoro
0.9.4 and downloads the model and voice; allow several minutes and internet
access for this setup. Later runs use the installed dependencies and cached
models. Text synthesis runs locally. For source installations on Fedora, install
`python3.12 espeak-ng libsndfile` with DNF first; the RPM declares
these dependencies. Write itself can continue using the system Python.

The selected Project Tree folder receives an **.app/.kokoro** folder containing
`request.json`, numbered `chunk-*.txt` and `chunk-*.wav` files, and `final.wav`
after successful generation. Formatting is cleaned for speech. The opening
chunk is about 120 characters; later chunks are about 300, preferring sentence
boundaries, with short pauses between chunks. Start snapshots the current text
and voice; editing or switching tabs does not change an ongoing recording.
Both folders are created on the first Start if needed and reused on later runs.
Starting again removes the previous generated chunks and recording from `.app/.kokoro`.
Other files in that folder are preserved. Copy `final.wav` elsewhere to keep it
before starting a new recording. Cancelled runs can leave chunks and a partial
recording, which are cleared on the next Start.
