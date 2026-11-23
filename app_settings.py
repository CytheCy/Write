"""Project-local preferences, with a system locator and a v0 migration backup."""
from pathlib import Path

from PySide6.QtCore import QSettings


class ProjectSettings:
    """Keep a stable settings object for controls when the project root changes."""

    def __init__(self, locator, initial_file=None):
        self.locator = locator
        locator.setFallbacksEnabled(False)
        root = locator.value('project_tree_path', '', type=str)
        if not root or not Path(root).is_dir():
            last_file = locator.value('last_open_file', '', type=str)
            candidate = initial_file or (Path(last_file) if last_file else None)
            root = candidate.parent if candidate and candidate.parent.is_dir() else Path.home()
        root = Path(root).expanduser().absolute()
        self._store = self._open(root)
        legacy = {key: locator.value(key) for key in locator.allKeys()
                  if key != 'project_tree_path'}
        if legacy:
            backup = QSettings(str(root / '.app' / 'legacy-settings-v0.ini'),
                               QSettings.Format.IniFormat)
            for key, value in legacy.items():
                if not backup.contains(key):
                    backup.setValue(key, value)
                if not self._store.contains(key):
                    self._store.setValue(key, value)
            self._check_sync(backup)
        for key in ('keys/dictionary_path', 'keys/thesaurus_path'):
            if not self._store.contains(key):
                self._store.setValue(key, '')
        self._store.setValue('settings_storage_version', 1)
        self._store.setValue('project_tree_path', str(root))
        self._check_sync(self._store)
        for key in legacy:
            locator.remove(key)
        locator.setValue('project_tree_path', str(root))
        self._check_sync(locator)

    @staticmethod
    def _open(root):
        directory = root / '.app'
        (directory / 'markup').mkdir(parents=True, exist_ok=True)
        store = QSettings(str(directory / 'settings.ini'), QSettings.Format.IniFormat)
        store.setFallbacksEnabled(False)
        return store

    @staticmethod
    def _check_sync(store):
        store.sync()
        if store.status() != QSettings.Status.NoError:
            raise OSError(f'Could not save settings to {store.fileName()}')

    def relocate(self, root):
        root = Path(root).expanduser().absolute()
        if not root.is_dir():
            raise OSError(f'Project folder does not exist: {root}')
        self._check_sync(self._store)
        values = {key: self._store.value(key) for key in self._store.allKeys()}
        target = self._open(root)
        target.clear()
        for key, value in values.items():
            target.setValue(key, value)
        target.setValue('project_tree_path', str(root))
        self._check_sync(target)
        previous = self.locator.value('project_tree_path')
        self.locator.setValue('project_tree_path', str(root))
        try:
            self._check_sync(self.locator)
        except OSError:
            self.locator.setValue('project_tree_path', previous)
            raise
        self._store = target

    def __getattr__(self, name):
        return getattr(self._store, name)
