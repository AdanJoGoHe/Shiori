import argparse
import json
import os
import sys
from pathlib import Path

from second_brain.core import Brain, load_config
from second_brain.catalog import Catalog


def default_config():
    if os.environ.get("SECOND_BRAIN_CONFIG"):
        return Path(os.environ["SECOND_BRAIN_CONFIG"])
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SecondBrain/personal/config.json"


def main():
    # JSON consumers and MCP expect UTF-8 even when Windows redirects stdout as cp1252.
    for stream in [sys.stdout, sys.stderr]:
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Shiori: Markdown memory and journal")
    parser.add_argument("--config", type=Path, default=default_config())
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["status", "doctor", "pause", "resume", "serve", "install-codex", "uninstall"]:
        command = sub.add_parser(name)
        if name == "doctor":
            checks = command.add_mutually_exclusive_group()
            checks.add_argument(
                "--catalog",
                action="store_true",
                help="Read-only catalog and selected-root diagnosis",
            )
            checks.add_argument(
                "--provider", action="store_true", help="Probe local provider status"
            )
    sub.add_parser("paths", help="Read-only safe path diagnostics; never initializes roots")
    remote = sub.add_parser("serve-http", help="Opt-in authenticated loopback MCP endpoint")
    remote.add_argument("--credentials-file", type=Path, required=True)
    remote.add_argument("--port", type=int, default=8794)
    remote.add_argument(
        "--proxy-host", help="Exact external HTTPS DNS name[:port] forwarded by a private proxy"
    )
    repair_paths = sub.add_parser("repair-paths", help="Preview same-store root normalization")
    repair_paths.add_argument("--vault-path", type=Path)
    repair_paths.add_argument("--state-path", type=Path)
    repair_paths.add_argument("--basic-memory-config-dir", type=Path)
    repair_paths.add_argument("--apply", action="store_true")
    repair_paths.add_argument(
        "--expect-revision", help="Refuse a changed configuration since preview"
    )
    upgrade = sub.add_parser("upgrade-codex", help="Preview an owned Codex integration update")
    upgrade.add_argument("--apply", action="store_true", help="Back up and apply the update")
    capture = sub.add_parser("capture")
    capture.add_argument("--event-file", type=Path, required=True)
    classify = sub.add_parser("classify", help="Preview capture quality without writing")
    classify.add_argument("--request-file", type=Path, required=True)
    backup = sub.add_parser("backup", help="Create a new local recovery bundle")
    backup.add_argument("--output", type=Path, required=True)
    export_memory = sub.add_parser("export-memory", help="Export a portable local recovery bundle")
    export_memory.add_argument("--output", type=Path, required=True)
    import_memory = sub.add_parser(
        "import-memory", help="Preview additive note import; never replace existing notes"
    )
    import_memory.add_argument("--input", type=Path, required=True)
    import_memory.add_argument(
        "--apply", action="store_true", help="Add new notes; skip duplicates/conflicts"
    )
    recovery = sub.add_parser("restore", help="Restore into a new paused deployment")
    recovery.add_argument("--input", type=Path, required=True)
    recovery.add_argument("--destination", type=Path, required=True)
    for name in ["search", "context"]:
        search = sub.add_parser(name)
        search.add_argument("query")
        search.add_argument("--tag", action="append", dest="tags")
        search.add_argument("--project")
        search.add_argument("--type")
        search.add_argument("--status")
        search.add_argument("--source-agent")
        if name == "context":
            search.add_argument("--max-chars", type=int, default=8000)
    read = sub.add_parser("read")
    read.add_argument("id")
    pending = sub.add_parser("pending", help="List pending capture identifiers without bodies")
    pending.add_argument("--offset", type=int, default=0)
    pending.add_argument("--limit", type=int, default=25)
    catalog = sub.add_parser("catalog", help="List authorized read-only content metadata")
    catalog.add_argument("--kind", choices=["documentation", "note", "journal"])
    catalog.add_argument("--source")
    catalog.add_argument("--offset", type=int, default=0)
    catalog.add_argument("--limit", type=int, default=25)
    viewer = sub.add_parser("viewer", help="Start the read-only local knowledge browser")
    viewer.add_argument("--port", type=int, default=0)
    export = sub.add_parser("annotations-export", help="Export the local annotation sidecar")
    export.add_argument("--output", type=Path, required=True)
    restore = sub.add_parser("annotations-restore", help="Restore a validated annotation export")
    restore.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "doctor" and args.catalog:
            from second_brain.paths import diagnose

            paths = diagnose(args.config)
            result = {"status": "unavailable", "paths": paths}
            # Refuse initialization on a diagnostic command, even for a missing empty store.
            if paths["status"] == "ok":
                try:
                    diagnosis = Catalog(Brain(load_config(args.config))).snapshot()["diagnostics"]
                    result.update(status=diagnosis["status"], catalog=diagnosis)
                except (OSError, ValueError, KeyError, TypeError):
                    result["reason"] = "catalog-unavailable"
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result["status"] not in {"ready", "empty"}:
                raise SystemExit(1)
            return
        if args.command in {"paths", "repair-paths"}:
            from second_brain.paths import diagnose, repair

            result = (
                diagnose(args.config)
                if args.command == "paths"
                else repair(
                    args.config,
                    {
                        key: getattr(args, key)
                        for key in ["vault_path", "state_path", "basic_memory_config_dir"]
                    },
                    args.apply,
                    args.expect_revision,
                )
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if result["status"] in {"blocked", "unavailable", "attention"}:
                raise SystemExit(1)
            return
        if args.command == "restore":
            from second_brain.backup import restore

            print(json.dumps(restore(args.input, args.destination), ensure_ascii=False, indent=2))
            return
        if args.command == "upgrade-codex":
            from second_brain.install import upgrade

            print(json.dumps(upgrade(args.config, args.apply), ensure_ascii=False, indent=2))
            return
        config = load_config(args.config)
        if args.command == "serve-http":
            os.environ["FASTMCP_CHECK_FOR_UPDATES"] = "off"
            os.environ["FASTMCP_SHOW_SERVER_BANNER"] = "false"
            os.environ["FASTMCP_TELEMETRY_MODE"] = "off"
            from second_brain.remote import serve_http

            serve_http(config, args.credentials_file, args.port, args.proxy_host)
            return
        brain = Brain(config)
        if args.command == "viewer":
            from second_brain.viewer import serve_viewer

            serve_viewer(brain, args.port)
            return
        if args.command == "serve":
            os.environ["FASTMCP_CHECK_FOR_UPDATES"] = "off"
            os.environ["FASTMCP_SHOW_SERVER_BANNER"] = "false"
            os.environ["FASTMCP_TELEMETRY_MODE"] = "off"
            from second_brain.server import serve

            serve(config)
            return
        if args.command in {"backup", "export-memory"}:
            from second_brain.backup import backup

            result = backup(brain, args.output)
        elif args.command == "import-memory":
            from second_brain.transfer import import_memory

            result = import_memory(brain, args.input, args.apply)
        elif args.command in {"annotations-export", "annotations-restore"}:
            from second_brain.annotations import Annotations, MAX_BYTES

            annotations = Annotations(brain)
            if args.command == "annotations-export":
                data = annotations.export()
                with args.output.open("x", encoding="utf-8") as stream:
                    json.dump(data, stream, ensure_ascii=False, indent=2)
                result = {"status": "exported", "count": len(data["items"])}
            else:
                if args.input.stat().st_size > MAX_BYTES:
                    raise ValueError("Annotation import exceeds size limit")
                result = annotations.restore(args.input.read_text(encoding="utf-8-sig"))
        elif args.command in {"install-codex", "uninstall"}:
            from second_brain.install import install, uninstall

            result = (
                install(args.config) if args.command == "install-codex" else uninstall(args.config)
            )
        elif args.command == "classify":
            from second_brain.quality import classify_capture

            if args.request_file.stat().st_size > 40000:
                raise ValueError("Classification request exceeds 40 KB")
            request = json.loads(args.request_file.read_text(encoding="utf-8-sig"))
            if not isinstance(request, dict) or set(request) != {"candidate", "assessment"}:
                raise ValueError("Request requires only candidate and assessment")
            result = classify_capture(brain, request["candidate"], request["assessment"])
        elif args.command == "capture":
            if args.event_file.stat().st_size > 40000:
                raise ValueError("Event file exceeds 40 KB")
            result = brain.capture(json.loads(args.event_file.read_text(encoding="utf-8-sig")))
        elif args.command in {"search", "context"}:
            filters = {
                key: getattr(args, key)
                for key in ["tags", "project", "type", "status", "source_agent"]
                if getattr(args, key) is not None
            }
            if args.command == "context":
                from second_brain.context import build_context

                result = build_context(brain, args.query, filters, args.max_chars)
            else:
                result = brain.search(args.query, filters=filters)
        elif args.command == "read":
            result = brain.read(args.id)
        elif args.command == "pending":
            result = brain.pending_captures(args.offset, args.limit)
        elif args.command == "catalog":
            result = Catalog(brain).list(args.kind, args.source, args.offset, args.limit)
        elif args.command in {"pause", "resume"}:
            result = brain.pause(args.command == "pause")
        else:
            result = brain.status()
            if args.command == "doctor":
                for note_id in brain.ledger()["notes"]:
                    brain.read(note_id)
                result["note_validation"] = "passed"
                result["host_integration"] = "requires a fresh agent session"
                if args.provider:
                    import asyncio
                    from second_brain.provider import probe_provider

                    result["provider_check"] = asyncio.run(probe_provider(config))
        print(
            json.dumps(result, ensure_ascii=False, indent=None if args.command == "context" else 2)
        )
        if args.command == "import-memory" and result["status"] == "blocked":
            raise SystemExit(1)
        if (
            args.command == "doctor"
            and args.provider
            and result["provider_check"]["status"] != "available"
        ):
            raise SystemExit(1)
    except (ValueError, OSError, KeyError) as error:
        print(f"Shiori: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
