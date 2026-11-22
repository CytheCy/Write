"""Settings migration, restart discovery, and relocation of live consumers."""
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QByteArray, QRect, QSettings

from app_settings import ProjectSettings


class ProjectSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        self.locator_path = str(Path(self.temp.name) / 'system.ini')
        self.locator = QSettings(self.locator_path, QSettings.Format.IniFormat)
        self.locator.setValue('project_tree_path', str(self.root))

    def test_migration_preserves_types_and_backs_up_legacy_preferences(self):
        values = {'font_size': 19, 'theme': 'dark', 'spell_check': False,
                  'spelling_words': ['Write'], 'keys/dictionary_path': '/keys/api',
                  'recent_files': ['a.md', 'b.md'],
                  'window_normal_geometry': QRect(10, 20, 700, 500),
                  'window_geometry': QByteArray(b'geometry')}
        for key, value in values.items():
            self.locator.setValue(key, value)
        settings = ProjectSettings(self.locator)
        self.assertEqual(Path(settings.fileName()), self.root / '.app/settings.ini')
        backup = QSettings(str(self.root / '.app/legacy-settings-v0.ini'),
                           QSettings.Format.IniFormat)
        restored = ProjectSettings(QSettings(self.locator_path, QSettings.Format.IniFormat))
        for key, value in values.items():
            self.assertEqual(restored.value(key), value)
            self.assertEqual(backup.value(key), value)
        self.assertEqual(self.locator.allKeys(), ['project_tree_path'])
        self.assertEqual(restored.value('settings_storage_version', type=int), 1)

    def test_relocation_keeps_consumers_and_restart_on_new_folder(self):
        settings = ProjectSettings(self.locator)
        consumer = settings
        settings.setValue('theme', 'dark')
        target = Path(self.temp.name) / 'other'
        target.mkdir()
        (target / '.app').mkdir()
        existing = QSettings(str(target / '.app/settings.ini'), QSettings.Format.IniFormat)
        existing.setValue('stale_preference', True)
        existing.sync()
        settings.relocate(target)
        consumer.setValue('spelling_words', ['portable'])
        consumer.sync()
        restored = ProjectSettings(QSettings(self.locator_path, QSettings.Format.IniFormat))
        self.assertEqual(restored.value('theme'), 'dark')
        self.assertFalse(restored.contains('stale_preference'))
        self.assertEqual(restored.value('spelling_words', type=list), ['portable'])
        self.assertEqual(Path(restored.fileName()), target / '.app/settings.ini')
        old = QSettings(str(self.root / '.app/settings.ini'), QSettings.Format.IniFormat)
        self.assertFalse(old.contains('spelling_words'))
        settings.relocate(target)
        self.assertEqual(settings.value('theme'), 'dark')

    def test_failed_relocation_preserves_active_store_and_locator(self):
        settings = ProjectSettings(self.locator)
        old_path = settings.fileName()
        target = Path(self.temp.name) / 'blocked'
        target.mkdir()
        (target / '.app').write_text('not a directory')
        with self.assertRaises(OSError):
            settings.relocate(target)
        self.assertEqual(settings.fileName(), old_path)
        self.assertEqual(self.locator.value('project_tree_path'), str(self.root))

    def test_existing_local_preferences_take_priority_during_migration(self):
        settings = ProjectSettings(self.locator)
        settings.setValue('font_size', 22)
        settings.sync()
        self.locator.setValue('font_size', 12)
        self.assertEqual(ProjectSettings(self.locator).value('font_size', type=int), 22)

    def test_initial_file_supplies_default_project_root(self):
        self.locator.clear()
        settings = ProjectSettings(self.locator, self.root / 'note.md')
        self.assertEqual(Path(settings.fileName()), self.root / '.app/settings.ini')
