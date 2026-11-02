"""Local protocol experiment: real isolated Codex, fake model, harmless real shell tool.

This establishes CLI/tool transport behavior only, NOT real DeepSeek or cross-provider native subagents.
No global config/auth files are read by this script. No secrets or network API are used.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-provider-test", action="store_true")
    options = parser.parse_args()
    observations = {
        "request_count": 0,
        "offered_tool_names": [],
        "tool_output_seen": False,
        "requested_models": [],
        "native_spawn_result": None,
    }
    root_requests = 0

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"data":[]}')

        def do_POST(self):
            nonlocal root_requests
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            observations["request_count"] += 1
            observations["requested_models"].append(body.get("model"))
            if body.get("model") == "publishing-parent-probe":
                root_requests += 1
            names = []
            for tool in body.get("tools", []):
                if tool.get("name"):
                    names.append(tool["name"])
                names.extend(t.get("name") for t in tool.get("tools", []) if t.get("name"))
            observations["offered_tool_names"] = names
            observations["tool_types"] = [
                {"type": t.get("type"), "name": t.get("name")} for t in body.get("tools", [])
            ]
            for tool in body.get("tools", []):
                for candidate in [tool, *tool.get("tools", [])]:
                    if candidate.get("name") == "spawn_agent":
                        observations["spawn_parameters"] = candidate.get("parameters")
            content = body.get("input", [])
            tool_output = [item for item in content if item.get("type") == "function_call_output"]
            observations["tool_output_seen"] = bool(tool_output)
            if options.native_provider_test and tool_output:
                observations["native_spawn_result"] = tool_output[-1].get("output")
            if (
                options.native_provider_test
                and body.get("model") == "publishing-parent-probe"
                and root_requests == 1
            ):
                item = {
                    "id": "fc_spawn",
                    "call_id": "call_spawn",
                    "type": "function_call",
                    "name": "spawn_agent",
                    "arguments": json.dumps(
                        {
                            "message": "Synthetic local probe. Reply OK, no tools or other work.",
                            "model": "deepseek-flash",
                            "fork_context": False,
                        }
                    ),
                    "status": "completed",
                }
            elif not options.native_provider_test and observations["request_count"] == 1:
                name = next((n for n in names if n.endswith("exec_command")), "exec_command")
                item = {
                    "id": "fc_probe",
                    "call_id": "call_probe",
                    "type": "function_call",
                    "name": name,
                    "arguments": json.dumps(
                        {"cmd": "printf probe-tool-ok", "max_output_tokens": 100}
                    ),
                    "status": "completed",
                }
            else:
                item = {
                    "id": "msg_probe",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "Local protocol probe complete."}],
                }
            response = {
                "id": f"resp_probe_{observations['request_count']}",
                "object": "response",
                "status": "completed",
                "model": "deepseek-flash",
                "output": [item],
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }
            events = [
                (
                    "response.created",
                    {
                        "type": "response.created",
                        "response": {**response, "status": "in_progress", "output": []},
                    },
                ),
                (
                    "response.output_item.added",
                    {"type": "response.output_item.added", "output_index": 0, "item": item},
                ),
                (
                    "response.output_item.done",
                    {"type": "response.output_item.done", "output_index": 0, "item": item},
                ),
                ("response.completed", {"type": "response.completed", "response": response}),
            ]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for sequence, (name, event) in enumerate(events):
                event["sequence_number"] = sequence
                self.wfile.write(f"event: {name}\ndata: {json.dumps(event)}\n\n".encode())
            self.wfile.flush()

    with tempfile.TemporaryDirectory(prefix="publishing-codex-probe-") as task_dir:
        root = Path(task_dir)
        codex_home = root / "codex-home"
        codex_home.mkdir()
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        env = {
            key: value
            for key, value in os.environ.items()
            if not any(secret in key.upper() for secret in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
        }
        env["CODEX_HOME"] = str(codex_home)
        args = [
            "codex",
            "exec",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--json",
            "-C",
            str(root),
            "-m",
            "publishing-parent-probe" if options.native_provider_test else "deepseek-flash",
            "-c",
            'model_provider="deepseek_probe"',
            "-c",
            'model_providers.deepseek_probe.name="Local protocol probe"',
            "-c",
            f'model_providers.deepseek_probe.base_url="http://127.0.0.1:{server.server_port}"',
            "-c",
            'model_providers.deepseek_probe.wire_api="responses"',
            "-c",
            "model_providers.deepseek_probe.requires_openai_auth=false",
            "-c",
            'web_search="disabled"',
            "Run only the requested harmless printf tool and report success. No other actions.",
        ]
        try:
            completed = subprocess.run(args, env=env, capture_output=True, text=True, timeout=50)
            parsed_events = []
            for line in completed.stdout.splitlines():
                try:
                    parsed_events.append(json.loads(line))
                except ValueError:
                    pass
            result = {
                "cli_version": subprocess.run(
                    ["codex", "--version"], env=env, capture_output=True, text=True
                ).stdout.strip(),
                "exit_code": completed.returncode,
                "isolated_home": True,
                "real_provider_called": False,
                "fresh_key_available": bool(os.environ.get("DEEPSEEK_API_KEY")),
                "shell_marker_seen": "probe-tool-ok" in completed.stdout,
                "event_types": [item.get("type") for item in parsed_events],
                "protocol_tool_roundtrip_verified": bool(
                    observations["tool_output_seen"] and "probe-tool-ok" in completed.stdout
                ),
                "native_cross_provider_verified": False,
                "native_probe_limitation": "Fake function_call for spawn_agent rejected by this CLI; cannot establish native provider switching"
                if options.native_provider_test
                else None,
                "errors": [
                    item for item in parsed_events if item.get("type") in {"error", "turn.failed"}
                ],
                **observations,
            }
        except subprocess.TimeoutExpired:
            result = {"exit_code": None, "error": "probe_timeout", **observations}
        finally:
            server.shutdown()
    report = Path(__file__).with_name(
        "model_native_probe_result.json"
        if options.native_provider_test
        else "model_probe_result.json"
    )
    report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
