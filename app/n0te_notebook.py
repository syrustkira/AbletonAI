from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
import json
import threading
import time
import uuid

from n0te_state import atomic_write_json


class NotePrivacy(str, Enum):
    PRIVATE_VAULT = "PRIVATE_VAULT"
    PERSONAL = "PERSONAL"
    PROJECT = "PROJECT"
    SHARED = "SHARED"
    PUBLIC_DRAFT = "PUBLIC_DRAFT"


class NoteArea(str, Enum):
    SCRATCHPAD = "SCRATCHPAD"
    SONG_NOTES = "SONG_NOTES"
    LYRICS = "LYRICS"
    PRODUCTION_IDEAS = "PRODUCTION_IDEAS"
    ARTIST_IDEAS = "ARTIST_IDEAS"
    CONTENT_IDEAS = "CONTENT_IDEAS"
    COLLABORATOR_NOTES = "COLLABORATOR_NOTES"
    REFERENCES = "REFERENCES"
    PRIVATE_VAULT = "PRIVATE_VAULT"


@dataclass
class Note:
    id: str
    area: NoteArea
    privacy: NotePrivacy
    text: str
    song_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    use_as_context: bool = False
    sync_approved: bool = False
    share_approved: bool = False

    def context_eligible(self) -> bool:
        return self.use_as_context and self.privacy is not NotePrivacy.PRIVATE_VAULT


class Notebook:
    def __init__(self, state: Path):
        self.root = Path(state) / "notebook"
        self._lock = threading.RLock()

    def create(self, text: str, area: NoteArea = NoteArea.SCRATCHPAD,
               privacy: NotePrivacy = NotePrivacy.PERSONAL, song_id: str = "") -> Note:
        if area is NoteArea.PRIVATE_VAULT:
            privacy = NotePrivacy.PRIVATE_VAULT
        now = time.time(); note = Note(uuid.uuid4().hex, area, privacy, str(text), song_id, now, now)
        self.save(note); return note

    def save(self, note: Note) -> None:
        if note.privacy is NotePrivacy.PRIVATE_VAULT:
            note.use_as_context = note.sync_approved = note.share_approved = False
        note.updated_at = time.time()
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            row = asdict(note); row["area"] = note.area.value; row["privacy"] = note.privacy.value
            atomic_write_json(self.root / f"{note.id}.json", row, mode=0o600)

    def get(self, note_id: str) -> Note | None:
        try: row = json.loads((self.root / f"{note_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError): return None
        row["area"] = NoteArea(row["area"]); row["privacy"] = NotePrivacy(row["privacy"])
        return Note(**row)

    def use_as_context(self, note_id: str) -> Note:
        note = self.get(note_id)
        if not note: raise LookupError("Unknown note")
        if note.privacy is NotePrivacy.PRIVATE_VAULT: raise PermissionError("Private Vault notes cannot become AI context")
        note.use_as_context = True; self.save(note); return note

    def attach_to_song(self, note_id: str, song_id: str) -> Note:
        note = self.get(note_id)
        if not note: raise LookupError("Unknown note")
        note.song_id = song_id; self.save(note); return note

    def context_notes(self, song_id: str = "") -> list[Note]:
        with self._lock: paths = sorted(self.root.glob("*.json"))
        notes = [self.get(path.stem) for path in paths]
        return [note for note in notes if note and note.context_eligible() and (not song_id or note.song_id == song_id)]
