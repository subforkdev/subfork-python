"""Command-line graph authoring and execution with JSON input and output."""

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from . import AuthenticationError, ExecutionTimeout, Subfork, SubforkError, __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the public command tree without opening a connection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--base-url", default=os.getenv("SUBFORK_BASE_URL", "https://subfork.com"))
    parser.add_argument("--timeout", type=float, default=30, help="HTTP timeout in seconds")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List account graphs")
    commands.add_parser("published", help="List published building blocks")
    for command in ("get", "versions", "interface", "export", "publish", "execute"):
        child = commands.add_parser(command)
        child.add_argument("graph_id")
        if command == "export":
            child.add_argument(
                "--output", default="-", help="Definition JSON path, or - for stdout"
            )
        elif command == "publish":
            child.add_argument("--version", required=True, help="New immutable version, e.g. v1")
            child.add_argument("--interface", help="Optional interface JSON file")
            child.add_argument("--comment", default="")
        elif command == "execute":
            child.add_argument("--version", default="draft")
            child.add_argument(
                "--no-wait", action="store_true", help="Return submission status immediately"
            )
            child.add_argument(
                "--raw", action="store_true", help="Print the full execution snapshot"
            )
            child.add_argument(
                "--wait-timeout",
                type=float,
                default=120,
                help="Maximum wait in seconds (default: 120)",
            )
            child.add_argument(
                "--poll-interval",
                type=float,
                default=2,
                help="Seconds between status checks (default: 2)",
            )
            child.add_argument("--inputs", help="Inputs JSON file, or - for stdin")
    for command in ("validate", "create"):
        child = commands.add_parser(command)
        child.add_argument("file", help="Graph definition JSON file, or - for stdin")
        child.add_argument("--name", help="Override the definition's name")
        if command == "create":
            child.add_argument("--description", default="")
            child.add_argument("--tag", action="append", default=[])
    return parser


def read_object(filename: str) -> Dict[str, Any]:
    """Read a JSON object from a UTF-8 file or standard input."""
    try:
        content = (
            sys.stdin.read() if filename == "-" else Path(filename).read_text(encoding="utf-8")
        )
        value = json.loads(content)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Input must contain valid UTF-8 JSON.") from exc
    if not isinstance(value, dict):
        raise ValueError("Input JSON must be an object.")
    return value


def graph_command(client: Subfork, args: argparse.Namespace) -> Any:
    """Dispatch graph operations through the same SDK used by Python callers."""
    graphs = client.graphs
    if args.command == "list":
        return graphs.list()
    if args.command == "published":
        return graphs.published()
    if args.command in {"create", "validate"}:
        definition = read_object(args.file)
        name = args.name if args.name is not None else definition.get("name", "Untitled Graph")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Graph name must be a nonempty string.")
        if args.command == "validate":
            return graphs.validate(definition, name=name)
        return graphs.create(
            name=name, definition=definition, description=args.description, tags=args.tag
        )
    if args.command == "get":
        return graphs.get(args.graph_id)
    if args.command == "export":
        graph = graphs.get(args.graph_id)
        exported = graph.get("definition")
        if not isinstance(exported, dict):
            raise ValueError("Graph response does not contain a definition object.")
        return exported
    if args.command == "versions":
        return graphs.versions(args.graph_id)
    if args.command == "interface":
        return graphs.interface(args.graph_id)
    if args.command == "publish":
        interface = read_object(args.interface) if args.interface else None
        return graphs.publish(
            args.graph_id, version=args.version, interface=interface, comment=args.comment
        )
    inputs = read_object(args.inputs) if args.inputs else None
    if any(
        not math.isfinite(value) or value <= 0 for value in (args.wait_timeout, args.poll_interval)
    ):
        raise ValueError("Wait timeout and poll interval must be positive finite numbers.")
    result = graphs.execute(args.graph_id, version=args.version, inputs=inputs)
    if not args.no_wait and result.get("status") not in {
        "completed",
        "failed",
        "canceled",
        "cancelled",
        "outcome_unknown",
    }:
        execution_id = result.get("id") or result.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            raise ValueError(
                "Submission returned no execution ID; inspect remote state before retrying."
            )
        print("subfork: waiting for execution {}".format(execution_id), file=sys.stderr)
        result = client.executions.wait(
            execution_id, timeout=args.wait_timeout, poll_interval=args.poll_interval
        )
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI; return zero on success and one on operational failure.

    Argparse reports usage errors with exit code two. Failed validation returns
    one, retaining its JSON diagnostics on stdout.
    """
    args = build_parser().parse_args(argv)
    try:
        with Subfork(base_url=args.base_url, timeout=args.timeout) as client:
            result = graph_command(client, args)
        failed = args.command == "execute" and result.get("status") in {
            "failed",
            "canceled",
            "cancelled",
            "outcome_unknown",
        }
        display = result
        if args.command == "execute" and not args.raw:
            if args.no_wait or failed:
                display = {
                    "execution_id": result.get("id") or result.get("execution_id"),
                    "status": result.get("status"),
                }
            else:
                display = result.get("outputs", {})
        rendered = json.dumps(display, indent=2, ensure_ascii=False) + "\n"
        output = getattr(args, "output", "-")
        if output == "-":
            sys.stdout.write(rendered)
        else:
            # Exclusive creation avoids silently overwriting a local definition.
            with Path(output).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(rendered)
        if failed:
            print(
                "subfork: execution did not complete successfully; use --raw for details",
                file=sys.stderr,
            )
            return 1
        if args.command == "validate" and result.get("valid") is False:
            return 1
        return 0
    except ExecutionTimeout as exc:
        print(
            "subfork: execution {} timed out while waiting; the remote run is not canceled".format(
                exc.execution_id
            ),
            file=sys.stderr,
        )
        return 1
    except AuthenticationError:
        print(
            "subfork: authentication failed (HTTP 401). Check that SUBFORK_API_KEY "
            "is an active key issued by the service selected with --base-url or "
            "SUBFORK_BASE_URL (default: https://subfork.com). "
            "The CLI reads exported environment variables; it does not load .env files.",
            file=sys.stderr,
        )
        return 1
    except (SubforkError, ValueError, OSError) as exc:
        print("subfork: {}".format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "subfork: interrupted; remote execution is not canceled automatically", file=sys.stderr
        )
        return 130
