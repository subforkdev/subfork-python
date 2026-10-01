"""Command-line graph authoring and execution with JSON input and output."""

import argparse
import json
import math
import os
import shutil
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional, Sequence

from . import APIError, AuthenticationError, ExecutionTimeout, Subfork, SubforkError, __version__


def print_api_error(status_code: int, message: str) -> None:
    """Write a concise API diagnostic, coloring only the status code on terminals."""
    code = str(status_code)
    if sys.stderr.isatty() and os.environ.get("TERM") != "dumb" and not os.environ.get("NO_COLOR"):
        code = "\033[33m" + code + "\033[0m"
    print("{}: {}".format(code, message), file=sys.stderr)


@contextmanager
def execution_status(graph_name: str) -> Iterator[Callable[[Dict[str, Any]], None]]:
    """Animate the active nodes on terminal stderr while preserving JSON stdout."""
    stream = sys.stderr
    terminal = stream.isatty() and os.environ.get("TERM") != "dumb"
    lock = threading.Lock()
    label = "Graph " + graph_name
    status = "Running"
    titles: Dict[str, str] = {}
    reported: Dict[str, str] = {}
    name_width = len(label)
    stopped = threading.Event()
    completed_marker = "✓"
    try:
        completed_marker.encode(stream.encoding or "ascii")
    except UnicodeError:
        completed_marker = "+"
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    try:
        frames.encode(stream.encoding or "ascii")
    except UnicodeError:
        frames = "|/-\\"

    def update(snapshot: Dict[str, Any]) -> None:
        """Replace the display state with active node titles from a snapshot."""
        nonlocal label, status, name_width
        definition = snapshot.get("definition") or {}
        for node in definition.get("nodes", []):
            titles[node["node_instance_id"]] = node.get("title") or node["node_instance_id"]
        nodes = snapshot.get("node_executions") or {}
        active = [
            titles.get(key, key) for key, node in nodes.items() if node.get("status") == "running"
        ]
        with lock:
            name_width = max(
                [name_width]
                + [len("Node " + title) for title in titles.values()]
                + [len("Node " + key) for key in nodes if key not in titles]
            )
            for key, node in nodes.items():
                outcome = node.get("status")
                if outcome not in {
                    "completed",
                    "failed",
                    "canceled",
                    "cancelled",
                    "skipped",
                    "outcome_unknown",
                }:
                    continue
                if reported.get(key) == outcome:
                    continue
                reported[key] = outcome
                state = "Canceled" if outcome == "cancelled" else outcome.replace("_", " ").title()
                name = "Node " + titles.get(key, key)
                if terminal:
                    stream.write(
                        "\r\033[2K"
                        + format_line(
                            completed_marker if outcome == "completed" else "-", name, state
                        )
                        + "\n"
                    )
                else:
                    stream.write(
                        format_line(
                            completed_marker if outcome == "completed" else "-", name, state
                        )
                        + "\n"
                    )
                stream.flush()
            label = (
                ("Node " if len(active) == 1 else "Nodes ") + ", ".join(active)
                if active
                else "Graph " + graph_name
            )
            status = (
                "Running"
                if active
                else str(snapshot.get("status", "running")).replace("_", " ").title()
            )

    def format_line(frame: str, name: str, state: str) -> str:
        """Format a width-limited progress row without splitting color escapes."""
        name = "".join(char if char.isprintable() else " " for char in name)
        state = "".join(char if char.isprintable() else " " for char in state)
        width = max(1, shutil.get_terminal_size().columns - 1)
        # Reserve space for the longest status so different outcomes align too.
        status_column = min(name_width + 14, max(7, width - len("Outcome Unknown")))
        name = name[: max(0, status_column - 7)]
        dots = "." * max(3, status_column - len(name) - 4)
        plain = "{} {} {} {}".format(frame, name, dots, state)
        if len(plain) > width:
            return plain[:width]
        if not terminal or os.environ.get("NO_COLOR"):
            return plain
        color = "32" if state in {"Running", "Completed"} else "31" if state == "Failed" else "33"
        colored_state = "\033[" + color + "m" + state + "\033[0m"
        marker_color = "32" if state == "Completed" else "33"
        return "\033[{}m{}\033[0m {} {} {}".format(marker_color, frame, name, dots, colored_state)

    def render(index: int) -> None:
        """Draw the active row without interleaving retained completion lines."""
        with lock:
            stream.write("\r\033[2K" + format_line(frames[index % len(frames)], label, status))
            stream.flush()

    def animate() -> None:
        """Refresh the spinner independently of network requests and polling."""
        index = 1
        while not stopped.wait(0.1):
            try:
                render(index)
            except (OSError, ValueError):
                return
            index += 1

    if not terminal:
        safe_name = "".join(char if char.isprintable() else " " for char in graph_name)
        print("Graph {} .......... Running".format(safe_name), file=stream)
        yield update
        return
    worker = threading.Thread(target=animate, name="subfork-spinner", daemon=True)
    try:
        render(0)
        worker.start()
        yield update
    finally:
        stopped.set()
        if worker.ident is not None:
            worker.join()
        stream.write("\r\033[2K")
        stream.flush()


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
        if command in {"export", "execute"}:
            child.add_argument(
                "-f", "--force", action="store_true", help="Overwrite an existing output file"
            )
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
                "-o",
                "--out",
                help="Write result JSON to a file, or - for stdout (default: no results)",
            )
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
    terminal_statuses = {
        "completed",
        "failed",
        "canceled",
        "cancelled",
        "outcome_unknown",
    }
    if not args.no_wait:
        execution_id = result.get("id") or result.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            raise ValueError(
                "Submission returned no execution ID; inspect remote state before retrying."
            )
        snapshot_definition = result.get("definition")
        graph_name = (
            snapshot_definition.get("name") if isinstance(snapshot_definition, dict) else None
        )
        with execution_status(
            graph_name if isinstance(graph_name, str) else args.graph_id
        ) as update:
            update(result)
            if result.get("status") not in terminal_statuses:
                result = client.executions.wait(
                    execution_id,
                    timeout=args.wait_timeout,
                    poll_interval=args.poll_interval,
                    on_update=update,
                )
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the CLI; return zero on success and one on operational failure.

    Argparse reports usage errors with exit code two. Failed validation returns
    one, retaining its JSON diagnostics on stdout.
    """
    args = build_parser().parse_args(argv)
    try:
        result_file = getattr(args, "out", None)
        force = getattr(args, "force", False)
        export_file = getattr(args, "output", "-")
        destination = (
            result_file
            if result_file is not None
            else (export_file if export_file != "-" else None)
        )
        if (
            destination is not None
            and destination != "-"
            and Path(destination).exists()
            and not force
        ):
            raise ValueError("Output file already exists; use --force to overwrite.")
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
        emit_results = args.command != "execute" or result_file is not None or args.raw
        if emit_results:
            rendered = json.dumps(display, indent=2, ensure_ascii=False) + "\n"
            output = result_file if result_file is not None else getattr(args, "output", "-")
            if output == "-":
                sys.stdout.write(rendered)
            else:
                # Open only after the request and serialization succeed.
                with Path(output).open(
                    "w" if force else "x", encoding="utf-8", newline="\n"
                ) as stream:
                    stream.write(rendered)
        elif args.command == "execute" and args.no_wait:
            print(
                "Execution {}: {}".format(
                    result.get("id") or result.get("execution_id"), result.get("status")
                ),
                file=sys.stderr,
            )
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
        print_api_error(
            401,
            "Authentication failed. Check that SUBFORK_API_KEY "
            "is an active key issued by the service selected with --base-url or "
            "SUBFORK_BASE_URL (default: https://subfork.com). "
            "The CLI reads exported environment variables; it does not load .env files.",
        )
        return 1
    except APIError as exc:
        message = str(exc)
        prefix = "Subfork API returned HTTP {}.".format(exc.status_code)
        if message.startswith(prefix):
            message = message[len(prefix) :].strip() or "API request failed."
        print_api_error(exc.status_code, message)
        return 1
    except (SubforkError, ValueError, OSError) as exc:
        print("subfork: {}".format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "subfork: interrupted; remote execution is not canceled automatically", file=sys.stderr
        )
        return 130
