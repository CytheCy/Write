"""Reference lookups use the WordDesk services without blocking the editor."""
import json
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, QSettings, QUrlQuery, Signal
from PySide6.QtNetwork import QNetworkReply
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from reference_api import Entry, clean_markup, parse_response, parse_moby_response
from reference_widgets import WordButton
from references import ReferenceTools


class Reply(QObject):
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.payload = b''
        self.status = 200
        self.failure = QNetworkReply.NetworkError.NoError
        self.aborted = False

    def abort(self):
        self.aborted = True

    def attribute(self, attribute):
        return self.status

    def error(self):
        return self.failure

    def readAll(self):
        return self.payload


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = QSettings(str(Path(self.temp.name) / 'settings.ini'), QSettings.Format.IniFormat)
        self.parent = QWidget()
        self.tools = ReferenceTools(self.settings, self.parent)
        self.requests = []
        def get(request):
            reply = Reply()
            self.requests.append((request, reply))
            return reply
        self.mock = patch.object(self.tools.network, 'get', side_effect=get)
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        self.tools.cancel()
        for panel in self.tools.panels.values():
            panel.close()
            panel.deleteLater()
        self.parent.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def configure_keys(self):
        for name in ('dictionary', 'thesaurus'):
            path = Path(self.temp.name) / (name + '.txt')
            path.write_text('\ufeff' + name + '-key\n', encoding='utf-8')
            self.settings.setValue(f'keys/{name}_path', str(path))

    def labels(self, name):
        view = self.tools.panels[name].view
        def active(label):
            widget = label
            while widget is not view:
                if widget.isHidden():
                    return False
                widget = widget.parentWidget()
            return True
        return ' '.join(label.text() for label in view.findChildren(QLabel) if active(label))

    def finish(self, index, payload, status=200):
        reply = self.requests[index][1]
        reply.payload = payload.encode('utf-8')
        reply.status = status
        if status != 200:
            reply.failure = QNetworkReply.NetworkError.AuthenticationRequiredError
        reply.finished.emit()

    def test_missing_keys_still_searches_moby(self):
        self.tools.search('  calm  ')
        self.assertEqual(len(self.requests), 1)
        query = QUrlQuery(self.requests[0][0].url())
        self.assertEqual(query.queryItemValue('Database'), 'moby-thesaurus')
        self.assertEqual(query.queryItemValue('Query'), 'calm')
        self.assertIn('Dictionary key is not set', self.labels('Dictionary'))
        self.finish(0, '<pre>3 Moby Thesaurus words for "calm": calm, quiet, peaceful</pre>')
        buttons = self.tools.panels['Moby Thesaurus'].view.findChildren(WordButton)
        self.assertEqual([b.text() for b in buttons], ['quiet', 'peaceful'])
        buttons[0].click()
        self.assertEqual(len(self.requests), 2)
        self.assertTrue(all(p.search_input.text() == 'quiet' for p in self.tools.panels.values()))

    def test_keys_urls_and_dictionary_rendering(self):
        self.configure_keys()
        self.tools.search('café /?')
        self.assertEqual(len(self.requests), 3)
        request = self.requests[0][0]
        self.assertIn('caf%C3%A9%20%2F%3F', request.url().toEncoded().data().decode())
        self.assertEqual(QUrlQuery(request.url()).queryItemValue('key'), 'dictionary-key')
        self.assertEqual(QUrlQuery(self.requests[1][0].url()).queryItemValue('key'), 'thesaurus-key')
        self.assertFalse(QUrlQuery(self.requests[2][0].url()).hasQueryItem('key'))
        payload = [{'hwi': {'hw': 'calm', 'prs': [{'mw': 'käm'}]}, 'fl': 'adjective',
                    'def': [{'sseq': [[["sense", {'sn': '1', 'dt': [
                        ['text', '{bc}free from agitation'], ['vis', [{'t': 'a {it}calm{/it} day'}]]]}]]]}],
                    'et': [['text', 'Middle English']]}]
        self.finish(0, json.dumps(payload))
        text = self.labels('Dictionary')
        for value in ('calm', 'käm', ': free from agitation', 'a calm day', 'WORD HISTORY', 'Middle English'):
            self.assertIn(value, text)
        self.assertNotIn('Looking up', text)

    def test_suggestions_are_clickable(self):
        self.configure_keys()
        self.tools.search('clma')
        self.finish(0, '["calm", "clam"]')
        button = next(b for b in self.tools.panels['Dictionary'].view.findChildren(QPushButton)
                      if b.text() == 'calm')
        button.click()
        self.assertEqual(len(self.requests), 6)
        self.assertTrue(self.requests[1][1].aborted)

    def test_old_response_cannot_replace_new_search(self):
        self.tools.search('old')
        self.tools.search('new')
        self.finish(0, '<pre>1 Moby Thesaurus words for "old": stale</pre>')
        self.assertIn('Looking up “new”', self.labels('Moby Thesaurus'))
        self.finish(1, '<pre>1 Moby Thesaurus words for "new": fresh</pre>')
        self.assertEqual([b.text() for b in self.tools.panels['Moby Thesaurus'].view.findChildren(WordButton)], ['fresh'])

    def test_invalid_keys_and_responses_are_recoverable(self):
        self.configure_keys()
        self.tools.search('calm')
        self.finish(0, '', 403)
        self.finish(1, '', 429)
        self.finish(2, '<html>No results</html>')
        self.assertIn('API key was rejected', self.labels('Dictionary'))
        self.assertIn('Request limit reached', self.labels('Thesaurus'))
        self.assertIn('No results', self.labels('Moby Thesaurus'))
        self.tools.search('calm')
        self.finish(3, '{broken json')
        self.assertIn('Could not read the response', self.labels('Dictionary'))

    def test_bad_key_file_does_not_block_other_sources(self):
        self.configure_keys()
        path = Path(self.settings.value('keys/dictionary_path'))
        for content in (b'', b'\xff'):
            path.write_bytes(content)
            self.tools.search('calm')
        self.assertEqual(len(self.requests), 4)
        self.assertIn('Could not read', self.labels('Dictionary'))

    def test_moby_shows_all_words_and_reflows_at_panel_width(self):
        panel = self.tools.panels['Moby Thesaurus']
        words = [f'related word {i}' for i in range(80)]
        panel.view.show_entries([Entry('calm', synonyms=words)], thesaurus=True,
                                word_limit=None, word_label='RELATED WORDS')
        panel.resize(280, 600)
        panel.show()
        self.app.processEvents()
        self.assertEqual(len(panel.view.findChildren(WordButton)), 80)
        self.assertLessEqual(panel.minimumSizeHint().width(), 280)
        self.assertLessEqual(panel.view.widget().width(), panel.view.viewport().width())

    def test_parser_preserves_synonyms_and_antonyms(self):
        entries, _ = parse_response([{'meta': {'id': 'calm', 'syns': [['quiet', 'still']],
                                              'ants': [['agitated']]}}])
        self.assertEqual(entries[0].synonyms, ['quiet', 'still'])
        self.assertEqual(entries[0].antonyms, ['agitated'])
        self.assertEqual(parse_moby_response('<pre>unrelated</pre>', 'calm'), ([], []))
        self.assertEqual(clean_markup('{bc}a {it}calm{/it} day'), ': a calm day')
