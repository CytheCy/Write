#!/usr/bin/env bash
# Fedora container integration test: preserve user files during a Write RPM reinstall.
set -euo pipefail
cd "$(dirname "$0")/.."
test_home="$(mktemp -d)"
trap 'rm -rf "$test_home"' EXIT
package=(dist/write-app-"$(cat VERSION)"-*.noarch.rpm)
[[ "${#package[@]}" == 1 && -f "${package[0]}" ]] || { echo 'Expected one current Write RPM' >&2; exit 1; }
dnf5 install -y "${package[0]}"
export XDG_CONFIG_HOME="$test_home/config"
export XDG_DATA_HOME="$test_home/data"
export XDG_STATE_HOME="$test_home/state"
export WRITE_TEST_PROJECT_ROOT="$test_home"
mkdir -p "$XDG_DATA_HOME/Write" "$XDG_STATE_HOME/Write"
printf 'database fixture\n' > "$XDG_DATA_HOME/Write/notes.db"
printf 'state fixture\n' > "$XDG_STATE_HOME/Write/session"
printf '# Saved note\n' > "$test_home/note.md"
python3 - <<'PY'
import os
from PySide6.QtCore import QSettings
s = QSettings('Write', 'Write')
s.setValue('project_tree_path', os.environ['WRITE_TEST_PROJECT_ROOT'])
s.setValue('theme', 'tokyo-night')
s.setValue('recent_files', ['note.md'])
s.setValue('font_size', 18)
s.sync()
assert s.status() == QSettings.Status.NoError
PY
before="$(sha256sum "$XDG_CONFIG_HOME/Write/Write.conf" "$XDG_DATA_HOME/Write/notes.db" "$XDG_STATE_HOME/Write/session" "$test_home/note.md")"
dnf5 reinstall -y "${package[0]}"
test "$(write-app --version)" = "Write $(cat VERSION)"
test "$(rpm -q --qf '%{VERSION}' write-app)" = "$(cat VERSION)"
test "$before" = "$(sha256sum "$XDG_CONFIG_HOME/Write/Write.conf" "$XDG_DATA_HOME/Write/notes.db" "$XDG_STATE_HOME/Write/session" "$test_home/note.md")"
QT_QPA_PLATFORM=offscreen python3 - <<'PY'
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
import sys
sys.path.insert(0, '/usr/share/write-app')
from main import MainWindow
app = QApplication([])
window = MainWindow()
assert window.theme_id == 'tokyo-night'
assert window.font_size == 18
assert window.settings.value('recent_files', [], type=list) == ['note.md']
assert QSettings('Write', 'Write').allKeys() == ['project_tree_path']
window.show()
app.processEvents()
window.close()
PY
rpm -V write-app
