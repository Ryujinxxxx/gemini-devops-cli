#!/usr/bin/env python3
"""Gemini DevOps CLI.

A terminal-first Gemini assistant for AWS, Kubernetes, Linux, and config review.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-2.5-flash"
HISTORY_FILE = Path.home() / ".gemini_cli_history.json"
MAX_HISTORY_TURNS = 12
MAX_LOCAL_FILE_SIZE = 5 * 1024 * 1024
MAX_FETCH_CHARS = 120_000

BASE_SYSTEM_PROMPT = """
You are an elite senior cloud, Kubernetes, Linux, networking, AWS, and DevOps assistant.

Rules:
- Be practical, production-oriented, and concise.
- Prefer exact commands when useful.
- Explain risks before destructive actions.
- Never claim a fixed knowledge cutoff year.
- If live grounding is enabled, use grounded evidence first.
- If live grounding is not enabled, do not pretend to have real-time knowledge.

Troubleshooting format:
1. Problem summary
2. Most likely root cause
3. Evidence / reasoning
4. Exact fix steps
5. Verification commands
6. Risk / rollback note

Design format:
1. Goal
2. Recommended design
3. Why this design
4. Security considerations
5. Cost considerations
6. Production improvements
""".strip()

MODE_PROMPTS: Dict[str, str] = {
    "default": BASE_SYSTEM_PROMPT,
    "k8s": BASE_SYSTEM_PROMPT + "\nExtra focus: Kubernetes workloads, services, ingress, probes, scheduling, manifest review.",
    "aws": BASE_SYSTEM_PROMPT + "\nExtra focus: AWS architecture, IAM, VPC, EC2, S3, RDS, EKS, Lambda, CloudFront, cost and security.",
    "linux": BASE_SYSTEM_PROMPT + "\nExtra focus: Linux CLI, systemd, networking, permissions, disk, memory, processes.",
    "review": BASE_SYSTEM_PROMPT + "\nExtra focus: strict technical review for correctness, security, performance, maintainability.",
}

USER_CONTEXT = """
User profile:
- network and cloud engineer
- works mainly with AWS, Kubernetes, Linux, Docker, networking
- prefers practical, engineer-level answers
- values copy-paste-ready commands
""".strip()

BOLD = "\033[1m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"


def colored(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"


def load_history() -> List[Dict[str, str]]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_history(history: List[Dict[str, str]]) -> None:
    try:
        trimmed = history[-(MAX_HISTORY_TURNS * 2) :]
        HISTORY_FILE.write_text(json.dumps(trimmed, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def clear_history() -> None:
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()


def get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print(colored("Error: GEMINI_API_KEY is not set.", RED), file=sys.stderr)
        print('Run: export GEMINI_API_KEY="your_actual_key"', file=sys.stderr)
        sys.exit(1)
    return genai.Client(api_key=api_key)


def get_system_prompt(mode: str) -> str:
    return MODE_PROMPTS[mode] + "\n" + USER_CONTEXT


def read_stdin_text() -> Optional[str]:
    if sys.stdin.isatty():
        return None
    data = sys.stdin.read()
    if not data:
        return None
    data = data.strip()
    return data or None


def read_file_text(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    p = Path(path).expanduser()
    if not p.exists():
        print(colored(f"Error: file not found: {p}", RED), file=sys.stderr)
        sys.exit(1)
    if p.stat().st_size > MAX_LOCAL_FILE_SIZE:
        print(colored("Error: local file is too large (>5MB).", RED), file=sys.stderr)
        sys.exit(1)
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        print(colored(f"Error reading file: {exc}", RED), file=sys.stderr)
        sys.exit(1)


def run_shell_command(command: Optional[str]) -> Optional[str]:
    if not command:
        return None
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=25)
        parts = [f"$ {command}"]
        if result.stdout:
            parts.append("STDOUT:\n" + result.stdout.strip())
        if result.stderr:
            parts.append("STDERR:\n" + result.stderr.strip())
        parts.append(f"EXIT_CODE: {result.returncode}")
        return "\n\n".join(parts).strip()
    except subprocess.TimeoutExpired:
        return f"$ {command}\n\nERROR: command timed out after 25 seconds"


def fetch_url_text(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        result = subprocess.run(["curl", "-L", "-s", "--max-time", "20", url], capture_output=True, text=True, timeout=25)
        if result.returncode != 0:
            return f"Failed to fetch URL: {url}\n{result.stderr.strip()}"
        text = result.stdout.strip()
        if len(text) > MAX_FETCH_CHARS:
            text = text[:MAX_FETCH_CHARS] + "\n\n[truncated]"
        return text
    except Exception as exc:
        return f"Failed to fetch URL: {url}\n{exc}"


def build_prompt(
    user_prompt: str,
    stdin_text: Optional[str],
    file_text: Optional[str],
    file_path: Optional[str],
    web_text: Optional[str],
    web_url: Optional[str],
    cmd_text: Optional[str],
) -> str:
    blocks: List[str] = []
    if user_prompt:
        blocks.append(f"User request:\n{user_prompt}")
    if file_text is not None:
        blocks.append(f"Attached file content ({file_path}):\n{file_text}")
    if stdin_text is not None:
        blocks.append(f"Piped terminal input:\n{stdin_text}")
    if cmd_text is not None:
        blocks.append(f"Local command result:\n{cmd_text}")
    if web_text is not None:
        blocks.append(f"Fetched web content ({web_url}):\n{web_text}")
    return "\n\n".join(blocks).strip()


def friendly_error_message(exc: Exception) -> str:
    text = str(exc)
    if "API key not valid" in text or "API_KEY_INVALID" in text:
        return "Your GEMINI_API_KEY is invalid. Generate a fresh key in Google AI Studio and update your shell."
    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        return "Rate limit or quota hit. Wait and retry, or use fewer requests."
    if "404" in text or "NOT_FOUND" in text:
        return "Model or endpoint not found. Check the model name."
    if "PERMISSION_DENIED" in text or "403" in text:
        return "Permission denied. Check API access or billing tier."
    return text


def make_config(system_prompt: str, ground: bool) -> types.GenerateContentConfig:
    if ground:
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        return types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.25, tools=[grounding_tool])
    return types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.25)


def extract_grounding(response: object) -> str:
    try:
        chunks: List[str] = []
        candidates = getattr(response, "candidates", None) or []
        for cand in candidates:
            meta = getattr(cand, "grounding_metadata", None) or getattr(cand, "groundingMetadata", None)
            if not meta:
                continue
            grounding_chunks = getattr(meta, "grounding_chunks", None) or getattr(meta, "groundingChunks", None) or []
            for item in grounding_chunks:
                web = getattr(item, "web", None)
                if web:
                    title = getattr(web, "title", "") or "source"
                    uri = getattr(web, "uri", "") or ""
                    if uri:
                        chunks.append(f"- {title}: {uri}")
        deduped: List[str] = []
        for chunk in chunks:
            if chunk not in deduped:
                deduped.append(chunk)
        return "\n".join(deduped[:8]) if deduped else ""
    except Exception:
        return ""


def generate_once(client: genai.Client, model: str, system_prompt: str, prompt: str, ground: bool) -> str:
    response = client.models.generate_content(model=model, contents=prompt, config=make_config(system_prompt, ground))
    text = response.text or "[No text returned]"
    sources = extract_grounding(response) if ground else ""
    if sources:
        text += "\n\nSources:\n" + sources
    return text


def generate_stream(client: genai.Client, model: str, system_prompt: str, prompt: str, ground: bool) -> str:
    stream = client.models.generate_content_stream(model=model, contents=prompt, config=make_config(system_prompt, ground))
    full: List[str] = []
    print()
    for chunk in stream:
        txt = getattr(chunk, "text", None)
        if txt:
            print(colored(txt, GREEN), end="", flush=True)
            full.append(txt)
    print("\n")
    return "".join(full).strip()


def refine_answer(client: genai.Client, model: str, system_prompt: str, answer: str) -> str:
    review_prompt = f"""
Improve the following answer to make it more accurate, practical, and production-ready.
Keep it concise and high-signal.

Answer to improve:
{answer}
""".strip()
    response = client.models.generate_content(
        model=model,
        contents=review_prompt,
        config=types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.1),
    )
    return response.text or answer


def print_help(model: str, mode: str) -> None:
    print(
        f"""
{colored('Gemini CLI', BOLD)}
Model:  {colored(model, YELLOW)}
Mode:   {colored(mode, CYAN)}

Usage:
  gemini "Explain Kubernetes Service"
  gemini --ground "latest AWS news"
  gemini --mode aws --ground "latest AWS networking announcements"
  gemini --web https://aws.amazon.com/blogs/aws/ "summarize this page"
  gemini --cmd "uname -a && free -h" --mode linux "summarize system status"
  cat app.log | gemini --mode linux "find the root cause"
  gemini --file deployment.yaml --mode k8s "review this manifest"
  gemini --refine "give me a polished answer"
  gemini --chat

Chat commands:
  /help
  /mode default|k8s|aws|linux|review
  /stream
  /ground
  /refine
  /clear
  /save
  /exit
""".strip()
    )


def build_chat_prompt(history: List[Dict[str, str]], user_input: str) -> str:
    recent = history[-(MAX_HISTORY_TURNS * 2) :]
    lines: List[str] = []
    for item in recent:
        role = item.get("role", "user").capitalize()
        content = item.get("content", "")
        lines.append(f"{role}: {content}")
    lines.append(f"User: {user_input}")
    lines.append("Assistant:")
    return "\n".join(lines)


def interactive_chat(client: genai.Client, model: str, mode: str, refine: bool, ground: bool) -> None:
    history = load_history()
    streaming = False
    current_mode = mode
    refine_enabled = refine
    ground_enabled = ground

    print(colored("Gemini Interactive CLI", BOLD + CYAN))
    print(f"Model:  {colored(model, YELLOW)}")
    print(f"Mode:   {colored(current_mode, CYAN)}")
    print(f"Refine: {colored(str(refine_enabled), YELLOW)}")
    print(f"Ground: {colored(str(ground_enabled), YELLOW)}")
    print("Type /help for commands.\n")

    while True:
        try:
            user_input = input(f"{colored('you>', BOLD)} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input == "/exit":
            print("Bye.")
            break
        if user_input == "/help":
            print_help(model, current_mode)
            continue
        if user_input == "/clear":
            history = []
            clear_history()
            print(colored("History cleared.", YELLOW))
            continue
        if user_input == "/save":
            save_history(history)
            print(colored(f"History saved to {HISTORY_FILE}", YELLOW))
            continue
        if user_input == "/stream":
            streaming = not streaming
            print(colored(f"Streaming {'enabled' if streaming else 'disabled'}.", CYAN))
            continue
        if user_input == "/refine":
            refine_enabled = not refine_enabled
            print(colored(f"Refine {'enabled' if refine_enabled else 'disabled'}.", CYAN))
            continue
        if user_input == "/ground":
            ground_enabled = not ground_enabled
            print(colored(f"Ground {'enabled' if ground_enabled else 'disabled'}.", CYAN))
            continue
        if user_input.startswith("/mode"):
            parts = shlex.split(user_input)
            if len(parts) > 1 and parts[1] in MODE_PROMPTS:
                current_mode = parts[1]
                print(colored(f"Mode switched to {current_mode}", CYAN))
            else:
                print(colored("Available modes: default, k8s, aws, linux, review", YELLOW))
            continue

        prompt = build_chat_prompt(history, user_input)
        system_prompt = get_system_prompt(current_mode)

        try:
            print(colored("gemini>", BOLD), end=" ", flush=True)
            if streaming:
                answer = generate_stream(client, model, system_prompt, prompt, ground_enabled)
            else:
                answer = generate_once(client, model, system_prompt, prompt, ground_enabled)
                if refine_enabled:
                    answer = refine_answer(client, model, system_prompt, answer)
                print(colored(answer, GREEN) + "\n")
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": answer})
            save_history(history)
        except Exception as exc:
            print(colored(f"Request failed: {friendly_error_message(exc)}", RED))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("prompt", nargs="*", help="Prompt text")
    parser.add_argument("--chat", action="store_true", help="Interactive chat mode")
    parser.add_argument("--stream", action="store_true", help="Stream output")
    parser.add_argument("--mode", choices=list(MODE_PROMPTS.keys()), default="default", help="Expert mode")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    parser.add_argument("--file", help="Read a local text file into the prompt")
    parser.add_argument("--web", help="Fetch a URL with curl and include its contents")
    parser.add_argument("--cmd", help="Run a local shell command and include its output")
    parser.add_argument("--ground", action="store_true", help="Use Gemini grounding with Google Search")
    parser.add_argument("--refine", action="store_true", help="Enable second-pass answer refinement")
    parser.add_argument("--clear-history", action="store_true", help="Clear saved chat history")
    parser.add_argument("-h", "--help", action="store_true", help="Show help")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.clear_history:
        clear_history()
        print(colored("Saved history cleared.", YELLOW))
        return
    if args.help:
        print_help(args.model, args.mode)
        return

    client = get_client()

    if args.chat:
        interactive_chat(client, args.model, args.mode, refine=args.refine, ground=args.ground)
        return

    user_prompt = " ".join(args.prompt).strip()
    stdin_text = read_stdin_text()
    file_text = read_file_text(args.file)
    web_text = fetch_url_text(args.web)
    cmd_text = run_shell_command(args.cmd)
    prompt = build_prompt(user_prompt, stdin_text, file_text, args.file, web_text, args.web, cmd_text)

    if not prompt:
        print_help(args.model, args.mode)
        return

    system_prompt = get_system_prompt(args.mode)

    try:
        if args.stream:
            _ = generate_stream(client, args.model, system_prompt, prompt, args.ground)
        else:
            answer = generate_once(client, args.model, system_prompt, prompt, args.ground)
            if args.refine:
                answer = refine_answer(client, args.model, system_prompt, answer)
            print("\n" + colored(answer, GREEN) + "\n")
    except Exception as exc:
        print(colored(f"Request failed: {friendly_error_message(exc)}", RED), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
