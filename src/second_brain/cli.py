import argparse
import json
import os
import sys
from pathlib import Path

from second_brain.core import Brain, load_config
from second_brain.catalog import Catalog

MANAGED_COMMANDS = (
    "serve",
    "viewer",
    "status",
    "doctor",
    "search",
    "context",
    "journal",
    "project-resume",
    "read",
    "capture",
    "classify",
    "note",
    "pending",
    "pause",
    "resume",
    "catalog",
    "backup",
    "export-memory",
    "import-memory",
    "learn",
)


def default_config():
    if os.environ.get("SECOND_BRAIN_CONFIG"):
        return Path(os.environ["SECOND_BRAIN_CONFIG"])
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SecondBrain/personal/config.json"


def create_parser(managed=False):
    parser = argparse.ArgumentParser(
        prog="shiori.cmd run" if managed else None,
        description="Shiori: Markdown memory and journal",
    )
    if not managed:
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
    capture.add_argument(
        "--event-file",
        type=Path,
        required=True,
        help="Candidate JSON file, or - for UTF-8 stdin; retain original for retries",
    )
    classify = sub.add_parser("classify", help="Preview capture quality without writing")
    classify.add_argument(
        "--request-file",
        type=Path,
        required=True,
        help="Candidate + assessment JSON file, or - for UTF-8 stdin",
    )
    note = sub.add_parser("note", help="Search and classify a candidate; capture only with --apply")
    note.add_argument(
        "--request-file", type=Path, required=True, help="UTF-8 JSON file, or - for stdin"
    )
    note.add_argument("--apply", action="store_true")
    note.add_argument("--expect-revision", help="Refuse a changed preview base (SHA256 or absent)")
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
        search.add_argument("query", **({"nargs": "?", "default": ""} if name == "search" else {}))
        if name == "search":
            search.add_argument(
                "--id", dest="note_id", help="Exact canonical ID; cannot combine with text/filters"
            )
        search.add_argument(
            "--tag",
            action="append",
            dest="tags",
            help="Exact normalized tag; repeated tags require all matches (AND)",
        )
        search.add_argument("--project")
        search.add_argument("--type")
        search.add_argument("--status")
        search.add_argument("--source-agent")
        if name == "context":
            search.add_argument("--max-chars", type=int, default=8000)
    read = sub.add_parser("read")
    read.add_argument("id")
    read.add_argument("--format", choices=["json", "text"], default="json")
    pending = sub.add_parser("pending", help="List pending capture identifiers without bodies")
    pending.add_argument("--offset", type=int, default=0)
    pending.add_argument("--limit", type=int, default=25)
    journal = sub.add_parser("journal", help="Read daily progress without changing memory")
    journal.add_argument("--start-date")
    journal.add_argument("--end-date")
    journal.add_argument("--project")
    journal.add_argument("--offset", type=int, default=0)
    journal.add_argument("--max-chars", type=int, default=8000)
    journal.add_argument("--view", choices=["entries", "tasks"], default="entries")
    project_resume = sub.add_parser(
        "project-resume", help="Resume an exact project's recorded work"
    )
    project_resume.add_argument("project")
    project_resume.add_argument("--max-chars", type=int, default=8000)
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
    learn = sub.add_parser(
        "learn", help="Propose and maintain reviewed skills from canonical memory"
    )
    learning = learn.add_subparsers(dest="learning_action", required=True)
    proposal = learning.add_parser("propose")
    proposal.add_argument("--request-file", type=Path, required=True)
    proposal.add_argument(
        "--apply", action="store_true", help="Save a private proposal; does not activate it"
    )
    learning.add_parser("list")
    learning.add_parser("guide")
    for name in ["show", "check", "activate", "refresh", "archive"]:
        action = learning.add_parser(name)
        action.add_argument("--id", required=True)
        if name == "check":
            action.add_argument("--expect-deployment")
            action.add_argument("--expect-revision", type=int)
        if name in {"activate", "refresh", "archive"}:
            action.add_argument("--apply", action="store_true")
        if name == "activate":
            action.add_argument("--host", choices=["codex", "augment"], required=True)
            action.add_argument("--skills-dir", type=Path, required=True)
    if managed:
        for name in list(sub.choices):
            if name not in MANAGED_COMMANDS:
                del sub.choices[name]
        sub._choices_actions[:] = [
            action for action in sub._choices_actions if action.dest in MANAGED_COMMANDS
        ]
    return parser


def main():
    # JSON consumers and MCP expect UTF-8 even when Windows redirects stdout as cp1252.
    for stream in [sys.stdout, sys.stderr]:
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", newline="\n")
    parser = create_parser()
    args = parser.parse_args()
    try:
        input_request = None
        if args.command in {"classify", "capture", "note"}:
            from second_brain.intake import read_json, classification_request

            input_request = read_json(
                args.event_file if args.command == "capture" else args.request_file
            )
            if args.command != "capture":
                classification_request(input_request)
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

            try:
                serve(config)
            except Exception:
                from second_brain.diagnostics import mcp_fallback

                print(
                    "Shiori: MCP startup/transport failed.\n" + mcp_fallback(config=args.config),
                    file=sys.stderr,
                )
                raise SystemExit(1) from None
            return
        if args.command == "learn":
            from second_brain.learning import Learning

            learner = Learning(brain)
            if args.learning_action == "guide":
                result = learner.guide()
            elif args.learning_action == "propose":
                if args.request_file.stat().st_size > 12000:
                    raise ValueError("Learning request exceeds 12 KB")
                result = learner.propose(
                    json.loads(args.request_file.read_text(encoding="utf-8-sig")), args.apply
                )
            elif args.learning_action == "list":
                result = {
                    "scope": brain.scope,
                    "items": [
                        {
                            key: row[key]
                            for key in ["id", "project", "description", "revision", "archived"]
                        }
                        for row in learner.rows()
                    ],
                }
            elif args.learning_action == "show":
                result = learner.read(args.id)
            elif args.learning_action == "check":
                result = learner.check(args.id, args.expect_deployment, args.expect_revision)
                if result["status"] != "ready":
                    print(json.dumps(result))
                    raise SystemExit(1)
            elif args.learning_action == "archive":
                result = learner.archive(args.id, args.apply)
            else:
                result = learner.export(
                    args.id,
                    getattr(args, "host", None),
                    getattr(args, "skills_dir", None),
                    apply=args.apply,
                    refresh=args.learning_action == "refresh",
                )
        elif args.command in {"backup", "export-memory"}:
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
        elif args.command in {"classify", "note"}:
            from second_brain.quality import classify_capture
            from second_brain.intake import read_json, classification_request, note_flow

            request = input_request
            if args.command == "note":
                result = note_flow(
                    brain, request, apply=args.apply, expect_revision=args.expect_revision
                )
            else:
                result = classify_capture(brain, *classification_request(request))
        elif args.command == "capture":
            result = brain.capture(input_request)
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
                if args.note_id is not None:
                    if args.query or filters:
                        raise ValueError("--id cannot be combined with text or filters")
                    result = brain.find(args.note_id)
                else:
                    result = brain.search(args.query, filters=filters)
        elif args.command == "read":
            result = brain.read(args.id)
            if args.format == "text":
                sys.stdout.write(result)
                return
        elif args.command == "pending":
            result = brain.pending_captures(args.offset, args.limit)
        elif args.command == "journal":
            from second_brain.journal import read_journal

            result = read_journal(
                brain,
                args.start_date,
                args.end_date,
                args.project,
                args.offset,
                args.max_chars,
                args.view,
            )
        elif args.command == "project-resume":
            from second_brain.workflow import resume_project

            result = resume_project(brain, args.project, args.max_chars)
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
            json.dumps(
                result,
                ensure_ascii=False,
                indent=None if args.command in {"context", "journal", "project-resume"} else 2,
            )
        )
        if args.command == "import-memory" and result["status"] == "blocked":
            raise SystemExit(1)
        if args.command == "note" and (
            result["decision"] == "deny"
            or result.get("capture", {}).get("status") in {"blocked", "failed", "skipped"}
        ):
            raise SystemExit(1)
        if (
            args.command == "doctor"
            and args.provider
            and result["provider_check"]["status"] != "available"
        ):
            raise SystemExit(1)
    except (ValueError, OSError, KeyError) as error:
        print(f"Shiori: {error}", file=sys.stderr)
        if args.command == "serve":
            from second_brain.diagnostics import mcp_fallback

            print(mcp_fallback(config=args.config), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
