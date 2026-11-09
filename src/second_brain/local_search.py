"""Process-local FTS5 index over validated canonical notes."""

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from threading import Lock

from second_brain.core import SLUG, parse_note


@dataclass(frozen=True)
class SearchNote:
    path: str
    content: str
    metadata: dict
    curated: dict
    body: str
    folded_body: str
    searchable: str


def literal_match(row, note_id, query, terms):
    if not terms:
        return 0
    if query == note_id:
        return 3
    title = str(row.metadata["title"]).casefold()
    if query == title or query in row.curated["tags"]:
        return 2
    # Keep the end of a sentence distinct from a longer IP, path or flag.
    pattern = rf"(?<![\w/\\.-]){re.escape(query)}(?![\w/\\-]|\.\w)"
    return int(bool(re.search(pattern, row.folded_body) or re.search(pattern, title)))


def build_index(rows):
    database = sqlite3.connect(":memory:", check_same_thread=False)
    try:
        database.execute("PRAGMA temp_store=MEMORY")
        database.execute(
            "CREATE VIRTUAL TABLE notes USING fts5("
            "id UNINDEXED, title, body, tokenize='unicode61 remove_diacritics 2')"
        )
        database.executemany(
            "INSERT INTO notes VALUES (?, ?, ?)",
            (
                (note_id, str(row.metadata["title"]), row.searchable)
                for note_id, row in rows.items()
            ),
        )
        database.commit()
    except BaseException:
        database.close()
        raise
    return database


class LocalSearch:
    def __init__(self):
        self.rows = {}
        self.index = None
        self.lock = Lock()

    def lookup(self, brain, query, *, index):
        with self.lock:
            rows = {}
            for note_id, relative in brain.ledger()["notes"].items():
                if not SLUG.fullmatch(note_id):
                    raise ValueError("Invalid note ID")
                content = brain.path(relative).read_text(encoding="utf-8")
                cached = self.rows.get(note_id)
                if cached and cached.path == relative and cached.content == content:
                    rows[note_id] = cached
                    continue
                metadata, body, curated = parse_note(content, note_id, brain.scope)
                searchable = " ".join(
                    [
                        str(metadata["title"]),
                        note_id,
                        *curated["tags"],
                        curated["project"] or "",
                        body,
                    ]
                ).casefold()
                rows[note_id] = SearchNote(
                    relative, content, metadata, curated, body, body.casefold(), searchable
                )
            if rows != self.rows:
                if self.index is not None:
                    self.index.close()
                    self.index = None
                self.rows = rows
            terms = query.split()
            if not index or not rows or not terms or (len(terms) == 1 and not query.isalnum()):
                return rows, {}
            tokens = dict.fromkeys(re.findall(r"[^\W_]+", query))
            if not tokens:
                return rows, {}
            try:
                if self.index is None:
                    self.index = build_index(rows)
                match = " OR ".join(f'"{token}"' for token in tokens)
                with closing(
                    self.index.execute(
                        "SELECT id, bm25(notes, 0, 4, 1) FROM notes WHERE notes MATCH ?", (match,)
                    )
                ) as cursor:
                    return rows, dict(cursor)
            except sqlite3.OperationalError:
                # SQLite builds without FTS5 still support literal and lexical search.
                return rows, {}
