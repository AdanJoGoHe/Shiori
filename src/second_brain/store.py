"""Work stores require a new, explicitly paired vault and state directory."""

import json
import uuid

MARKER = ".shiori-work-store.json"
SCOPES = {"personal", "work"}


def check_store(scope, vault, state):
    from second_brain.core import scoped_path

    markers = [scoped_path(root, MARKER) for root in (vault, state)]
    if scope == "personal":
        if any(path.exists() for path in markers):
            raise ValueError("Work store cannot be opened as personal")
        return
    if vault.is_relative_to(state) or state.is_relative_to(vault):
        raise ValueError("Work vault and state must be separate")
    try:
        records = []
        for path in markers:
            if path.stat().st_size > 4096:
                raise ValueError("Oversized store marker")
            records.append(json.loads(path.read_text(encoding="utf-8")))
        record = records[0]
        if (
            records[1] != record
            or set(record) != {"schema_version", "scope", "store_id", "vault", "state"}
            or record["schema_version"] != 1
            or record["scope"] != "work"
            or uuid.UUID(record["store_id"]).hex != record["store_id"]
            or record["vault"] != str(vault)
            or record["state"] != str(state)
        ):
            raise ValueError("Mismatched store markers")
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("Work store identity is missing or mismatched; inspect paths") from None


def initialize_work(vault, state):
    from second_brain.core import initialize_root

    if vault.exists() or state.exists():
        check_store("work", vault, state)
        return vault, state
    if vault.is_relative_to(state) or state.is_relative_to(vault):
        raise ValueError("Work vault and state must be separate")
    vault, state = initialize_root(vault), initialize_root(state)
    record = {
        "schema_version": 1,
        "scope": "work",
        "store_id": uuid.uuid4().hex,
        "vault": str(vault),
        "state": str(state),
    }
    for root in (vault, state):
        with (root / MARKER).open("x", encoding="utf-8") as stream:
            json.dump(record, stream)
    return vault, state
