import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from n0te_events import EventEngine
from n0te_notebook import NoteArea, NotePrivacy, Notebook


class EventNotebookTests(unittest.TestCase):
    def test_mark_is_durable_song_and_workspace_attributed(self):
        with tempfile.TemporaryDirectory() as td:
            events = EventEngine(Path(td))
            mark = events.mark("song-1", "ableton-set-1", "chorus payoff", transport={"beat": 65.0})
            loaded = EventEngine(Path(td)).recent("song-1")[-1]
            self.assertEqual(loaded["id"], mark["id"])
            self.assertEqual(loaded["workspace_id"], "ableton-set-1")
            self.assertEqual(loaded["data"]["transport"]["beat"], 65.0)

    def test_event_history_is_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            events = EventEngine(Path(td), max_events_per_song=10)
            for index in range(15): events.append("decision", "song", data={"index": index})
            self.assertEqual(len(events.recent("song", 100)), 10)

    def test_private_vault_never_becomes_context_sync_or_share(self):
        with tempfile.TemporaryDirectory() as td:
            book = Notebook(Path(td)); note = book.create("private lyric", NoteArea.PRIVATE_VAULT)
            note.use_as_context = note.sync_approved = note.share_approved = True; book.save(note)
            loaded = book.get(note.id)
            self.assertEqual(loaded.privacy, NotePrivacy.PRIVATE_VAULT)
            self.assertFalse(loaded.use_as_context or loaded.sync_approved or loaded.share_approved)
            with self.assertRaises(PermissionError): book.use_as_context(note.id)
            self.assertEqual(book.context_notes(), [])

    def test_context_is_explicit_and_song_scoped(self):
        with tempfile.TemporaryDirectory() as td:
            book = Notebook(Path(td)); note = book.create("bass should stay simple")
            self.assertEqual(book.context_notes(), [])
            book.attach_to_song(note.id, "song-a"); book.use_as_context(note.id)
            self.assertEqual([n.text for n in book.context_notes("song-a")], ["bass should stay simple"])
            self.assertEqual(book.context_notes("song-b"), [])


if __name__ == "__main__": unittest.main()
