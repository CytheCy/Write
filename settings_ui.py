"""Tabbed settings window, sharing the editor's existing settings and actions."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from updater import UpdatesPanel
from references import KeyPathRow, SOURCES


class SettingsDialog(QDialog):
    def __init__(self, window, font_size_range):
        super().__init__(window)
        self.editor_window = window
        self.font_size_range = font_size_range
        self.setWindowTitle('Settings')
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(680, 620)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName('Settings categories')
        layout.addWidget(self.tabs)

        themes = QScrollArea()
        themes.setWidgetResizable(True)
        themes.setFrameShape(QScrollArea.Shape.NoFrame)
        themes.setWidget(window.create_theme_panel())
        self.tabs.addTab(themes, 'Themes')
        self.tabs.addTab(self.appearance_panel(), 'Appearance')
        self.tabs.addTab(self.shortcuts_panel(), 'Shortcut Keys')
        self.updates = UpdatesPanel(window)
        self.updates.close_requested.connect(self.close)
        self.tabs.addTab(self.updates, 'Updates')
        self.tabs.addTab(self.general_panel(), 'General')

        hint = QLabel('Changes apply immediately and are saved automatically.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    @staticmethod
    def action_checkbox(action, label, name):
        checkbox = QCheckBox(label)
        checkbox.setObjectName(name)
        checkbox.setChecked(action.isChecked())
        checkbox.toggled.connect(action.setChecked)
        action.toggled.connect(checkbox.setChecked)
        return checkbox

    def appearance_panel(self):
        window = self.editor_window
        panel = QWidget()
        layout = QVBoxLayout(panel)
        form = QFormLayout()
        self.font_size = QSpinBox()
        self.font_size.setObjectName('settingsFontSize')
        self.font_size.setRange(*self.font_size_range)
        self.font_size.setSuffix(' pt')
        self.font_size.setValue(window.font_size)
        self.font_size.valueChanged.connect(window.set_font_size)
        form.addRow('Font size:', self.font_size)
        self.spacing = QSpinBox()
        self.spacing.setObjectName('settingsParagraphSpacing')
        self.spacing.setRange(0, 48)
        self.spacing.setSuffix(' px')
        self.spacing.setValue(window.paragraph_spacing)
        self.spacing.valueChanged.connect(window.set_paragraph_spacing)
        form.addRow('Paragraph spacing:', self.spacing)
        self.page_width = QSpinBox()
        self.page_width.setObjectName('settingsPageWidth')
        self.page_width.setRange(0, 10000)
        self.page_width.setSingleStep(50)
        self.page_width.setSuffix(' px')
        self.page_width.setSpecialValueText('Unlimited')
        self.page_width.setValue(window.max_page_width)
        self.page_width.valueChanged.connect(window.set_max_page_width)
        form.addRow('Maximum page width:', self.page_width)
        self.heading_state = QComboBox()
        self.heading_state.setObjectName('settingsHeadingPanel')
        for state, label in (('closed', 'Hide'), ('narrow', 'Narrow'), ('full', 'Full')):
            self.heading_state.addItem(label, state)
        self.heading_state.setCurrentIndex(self.heading_state.findData(window.heading_panel_state))
        self.heading_state.currentIndexChanged.connect(
            lambda index: window.heading_state_actions[self.heading_state.itemData(index)].trigger())
        form.addRow('Heading panel:', self.heading_state)
        layout.addLayout(form)
        layout.addWidget(self.action_checkbox(
            window.heading_auto_hide_action, 'Auto-hide heading panel', 'settingsHeadingAutoHide'))
        layout.addWidget(self.action_checkbox(
            window.ribbon_auto_hide_action, 'Auto-hide toolbar ribbon', 'settingsRibbonAutoHide'))
        layout.addStretch(1)
        return panel

    def shortcuts_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel('Keyboard shortcuts available while writing:'))
        rows = []
        for action in self.editor_window.actions():
            shortcuts = action.shortcuts()
            if shortcuts:
                rows.append((action.text().replace('&', '').rstrip('…'),
                             ', '.join(key.toString(QKeySequence.SequenceFormat.NativeText)
                                       for key in shortcuts)))
        for label, key in (
            ('Undo', QKeySequence.StandardKey.Undo),
            ('Redo', QKeySequence.StandardKey.Redo),
            ('Cut', QKeySequence.StandardKey.Cut),
            ('Copy', QKeySequence.StandardKey.Copy),
            ('Paste', QKeySequence.StandardKey.Paste),
            ('Select all', QKeySequence.StandardKey.SelectAll),
        ):
            rows.append((label, QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)))
        rows.extend((('Next table cell / add row', 'Tab'),
                     ('Previous table cell', 'Shift+Tab'),
                     ('Continue list / add table row', 'Enter')))
        table = QTableWidget(len(rows), 2)
        table.setObjectName('settingsShortcuts')
        table.setAccessibleName('Keyboard shortcuts')
        table.setHorizontalHeaderLabels(['Action', 'Shortcut'])
        table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for row, (label, shortcut) in enumerate(rows):
            table.setItem(row, 0, QTableWidgetItem(label))
            table.setItem(row, 1, QTableWidgetItem(shortcut))
        layout.addWidget(table)
        return panel

    def general_panel(self):
        window = self.editor_window
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(self.action_checkbox(
            window.spell_check_action, 'Spell check (English)', 'settingsSpellCheck'))
        layout.addSpacing(12)
        layout.addWidget(QLabel('Project tree location'))
        project_row = QHBoxLayout()
        self.project_path = QLineEdit(str(window.project_tree_path))
        self.project_path.setObjectName('settingsProjectTreePath')
        self.project_path.setAccessibleName('Project tree location')
        self.project_path.setReadOnly(True)
        project_row.addWidget(self.project_path, 1)
        browse = QPushButton('Choose folder…')
        browse.setObjectName('settingsProjectTreeBrowse')
        browse.clicked.connect(self.choose_project_folder)
        project_row.addWidget(browse)
        layout.addLayout(project_row)
        layout.addSpacing(12)
        layout.addWidget(QLabel('Reference API key files'))
        hint = QLabel('Choose the text files containing your dictionary and thesaurus API keys.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        for name, (_, setting_key, _) in SOURCES.items():
            if setting_key:
                layout.addWidget(KeyPathRow(name, setting_key, window.settings))
        layout.addStretch(1)
        return panel

    def choose_project_folder(self):
        window = self.editor_window
        selected = QFileDialog.getExistingDirectory(
            self, 'Choose project tree folder', str(window.project_tree_path))
        if selected and window.set_project_tree_path(selected):
            self.project_path.setText(str(window.project_tree_path))

    def done(self, result):
        if self.updates.stop_worker():
            super().done(result)
