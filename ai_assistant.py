"""
ai_assistant.py

Enhanced Vex assistant core.

Public API:
- process_command_return(text:str) -> str
    Use from a web UI or any caller that expects a string reply.
    Non-interactive: destructive actions (shutdown/delete) require explicit confirmation phrase.

- process_command(text:str) -> None
    Interactive/CLI or voice use: speaks via TTS (if available) and will prompt for confirmation
    for destructive operations when running as an interactive session.

CONFIG:
- Configure endpoints, confirmation tokens, feature flags in CONFIG below.

Security & Safety:
- Dangerous actions (shutdown, restart, delete) require explicit confirmation.
- AI endpoint and keys are configurable via env vars.
- This module will attempt to import optional libs and degrade gracefully if missing.
"""

import os
import re
import sys
import shlex
import json
import math
import time
import threading
import platform
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

import requests

# Optional libs (not required)
try:
    import pyttsx3
except Exception:
    pyttsx3 = None

try:
    import pyperclip
except Exception:
    pyperclip = None

try:
    import pyautogui
except Exception:
    pyautogui = None

# ---------------------------
# CONFIG - edit or use env vars
# ---------------------------
CONFIG = {
    "AI_ENDPOINT": os.environ.get("JARVIS_AI_ENDPOINT", "http://localhost:11434/api/generate"),
    "AI_MODEL": os.environ.get("JARVIS_AI_MODEL", "mistral"),
    "CONFIRM_TOKEN": os.environ.get("JARVIS_CONFIRM_TOKEN", "CONFIRM"),  # must include this for destructive web calls
    "ALLOW_SYSTEM_COMMANDS": os.environ.get("JARVIS_ALLOW_SYSTEM_COMMANDS", "false").lower() == "true",
    "MUSIC_FOLDER": str(Path.home() / "Music"),
    "LOCAL_MUSIC_MAP": {},  # optional map name->path
    "TTS_ENABLED": pyttsx3 is not None,
    "WIKI_FALLBACK": True,
}

# ---------------------------
# TTS setup (optional)
# ---------------------------
VOICE_LOCK = threading.Lock()
if pyttsx3 and CONFIG["TTS_ENABLED"]:
    _engine = pyttsx3.init()
    try:
        _engine.setProperty("rate", 160)
    except Exception:
        pass
else:
    _engine = None


def speak(text: str, block: bool = True) -> None:
    """Speak text (if TTS available) and print to console."""
    if not text:
        return
    print("Vex:", text)
    if _engine:
        with VOICE_LOCK:
            _engine.say(text)
            if block:
                _engine.runAndWait()


# ---------------------------
# Helpers
# ---------------------------
def open_website(url: str) -> str:
    """Open a URL in the default browser. If plain text, treat as search."""
    import webbrowser
    url = url.strip()
    if not url:
        return "No URL provided."
    # If it looks like a search phrase (no dot, spaces), perform Google search
    if " " in url or (("." not in url) and ("/" not in url)):
        query = requests.utils.requote_uri(url)
        search_url = f"https://www.google.com/search?q={query}"
        webbrowser.open(search_url)
        return f"Searching web for: {url}"
    # Ensure scheme
    if not re.match(r"^[a-zA-Z]+://", url):
        url = "https://" + url
    try:
        webbrowser.open(url)
        return f"Opening {url}"
    except Exception as e:
        return f"Failed to open {url}: {e}"


def open_local(path_or_app: str) -> str:
    """Try to open a local file or application. Returns status string."""
    path_or_app = path_or_app.strip()
    if not path_or_app:
        return "No file or application specified."

    # If it's a path that exists, open it
    p = Path(path_or_app).expanduser()
    if p.exists():
        try:
            if platform.system() == "Windows":
                os.startfile(str(p))
            elif platform.system() == "Darwin":
                subprocess.call(["open", str(p)])
            else:
                subprocess.call(["xdg-open", str(p)])
            return f"Opened {p}"
        except Exception as e:
            return f"Failed to open {p}: {e}"

    # Otherwise, attempt to run as app/command
    try:
        if platform.system() == "Windows":
            subprocess.Popen(shlex.split(path_or_app), shell=True)
        else:
            subprocess.Popen(shlex.split(path_or_app))
        return f"Launching {path_or_app}"
    except Exception as e:
        return f"Failed to launch {path_or_app}: {e}"


def play_music(query: str) -> str:
    """Play a song: if local mapping or path exists, open it, otherwise YouTube search."""
    q = query.strip()
    if not q:
        return "No song specified."
    # Exact local mapping
    if q in CONFIG["LOCAL_MUSIC_MAP"]:
        path = CONFIG["LOCAL_MUSIC_MAP"][q]
        return open_local(path)
    # if given path
    p = Path(q).expanduser()
    if p.exists():
        return open_local(str(p))
    # search YouTube
    query = requests.utils.requote_uri(q)
    url = f"https://www.youtube.com/results?search_query={query}"
    return open_website(url)


def take_screenshot() -> str:
    if not pyautogui:
        return "Screenshot not available (pyautogui missing)."
    path = Path.home() / "Pictures"
    path.mkdir(parents=True, exist_ok=True)
    filename = path / f"jarvis_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    try:
        img = pyautogui.screenshot()
        img.save(filename)
        return f"Saved screenshot to {filename}"
    except Exception as e:
        return f"Screenshot failed: {e}"


def clipboard_copy(text: str) -> str:
    if not pyperclip:
        return "Clipboard support not available (pyperclip missing)."
    try:
        pyperclip.copy(text)
        return "Text copied to clipboard."
    except Exception as e:
        return f"Failed to copy: {e}"


def clipboard_paste() -> str:
    if not pyperclip:
        return "Clipboard support not available (pyperclip missing)."
    try:
        return pyperclip.paste()
    except Exception as e:
        return f"Failed to paste: {e}"


# ---------------------------
# Safe math evaluator using AST
# ---------------------------
import ast

_ALLOWED_NAMES = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
_ALLOWED_NAMES.update({"abs": abs, "round": round, "min": min, "max": max})

_ALLOWED_NODE_TYPES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Num,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.FloorDiv,
    ast.USub,
    ast.UAdd,
    ast.Tuple,
    ast.List,
)


def safe_eval(expr: str):
    """Evaluate a math expression safely. Supports math functions."""
    expr = expr.strip()
    if not expr:
        raise ValueError("Empty expression")
    node = ast.parse(expr, mode="eval")

    # Walk and validate nodes
    for n in ast.walk(node):
        if not isinstance(n, _ALLOWED_NODE_TYPES):
            raise ValueError(f"Invalid expression: contains {type(n).__name__}")

        # If function call, ensure name allowed
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                if n.func.id not in _ALLOWED_NAMES:
                    raise ValueError(f"Use of function '{n.func.id}' not allowed")
            else:
                raise ValueError("Only named functions are allowed")

        if isinstance(n, ast.Name):
            if n.id not in _ALLOWED_NAMES:
                raise ValueError(f"Use of name '{n.id}' not allowed")

    compiled = compile(node, "<string>", "eval")
    return eval(compiled, {"__builtins__": {}}, _ALLOWED_NAMES)


# ---------------------------
# AI fallback & GK via Wikipedia
# ---------------------------
def ai_fallback(prompt: str) -> str:
    """Try configured AI endpoint; if not available, fallback to wiki or simple echo."""
    # Try HTTP AI endpoint
    try:
        resp = requests.post(
            CONFIG["AI_ENDPOINT"],
            json={"model": CONFIG["AI_MODEL"], "prompt": prompt, "stream": False},
            timeout=10,
        )
        if resp.ok:
            try:
                j = resp.json()
                # Common endpoints may return {"response": "..."} or {"text": "..."}
                for k in ("response", "text", "output"):
                    if k in j:
                        return j[k]
                return json.dumps(j)
            except Exception:
                return resp.text or "(empty AI response)"
    except Exception:
        pass

    # Wikipedia fallback (good for GK)
    if CONFIG["WIKI_FALLBACK"]:
        try:
            q = prompt.lower().strip()
            q = re.sub(r"^(who is|what is|define|tell me about)\s+", "", q)
            url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + requests.utils.requote_uri(q)
            r = requests.get(url, timeout=6)
            if r.ok:
                j = r.json()
                extract = j.get("extract")
                if extract:
                    return extract
        except Exception:
            pass

    return "Sorry — I couldn't reach the AI, and have no quick answer."


# ---------------------------
# File operations (safe-ish)
# ---------------------------
def list_dir(path: str = ".") -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"Path not found: {p}"
    try:
        items = list(p.iterdir())
        lines = []
        for it in items:
            lines.append(f"{it.name}/" if it.is_dir() else it.name)
        return "\n".join(lines) or "(empty)"
    except Exception as e:
        return f"Failed listing: {e}"


def make_file(path: str, content: str = "") -> str:
    p = Path(path).expanduser()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Created file: {p}"
    except Exception as e:
        return f"Failed to create file: {e}"


def move_file(src: str, dst: str) -> str:
    s = Path(src).expanduser()
    d = Path(dst).expanduser()
    if not s.exists():
        return f"Source not found: {s}"
    try:
        d.parent.mkdir(parents=True, exist_ok=True)
        s.rename(d)
        return f"Moved {s} -> {d}"
    except Exception as e:
        return f"Move failed: {e}"


def delete_path(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"Path not found: {p}"
    try:
        if p.is_dir():
            import shutil
            shutil.rmtree(p)
        else:
            p.unlink()
        return f"Deleted {p}"
    except Exception as e:
        return f"Delete failed: {e}"


# ---------------------------
# System commands (safe gating)
# ---------------------------
def _do_system_shutdown() -> str:
    try:
        if platform.system() == "Windows":
            subprocess.Popen(["shutdown", "/s", "/t", "5"])
        elif platform.system() == "Darwin":
            subprocess.Popen(["sudo", "shutdown", "-h", "now"])
        else:
            subprocess.Popen(["shutdown", "-h", "now"])
        return "Shutdown initiated."
    except Exception as e:
        return f"Shutdown failed: {e}"


def _do_system_restart() -> str:
    try:
        if platform.system() == "Windows":
            subprocess.Popen(["shutdown", "/r", "/t", "5"])
        elif platform.system() == "Darwin":
            subprocess.Popen(["sudo", "shutdown", "-r", "now"])
        else:
            subprocess.Popen(["reboot"])
        return "Restart initiated."
    except Exception as e:
        return f"Restart failed: {e}"


def require_confirm_for_web(command: str, text: str) -> Optional[str]:
    """
    For non-interactive callers, require the CONFIRM_TOKEN in the text to allow destructive ops.
    Returns None if allowed, otherwise a message explaining how to confirm.
    """
    token = CONFIG["CONFIRM_TOKEN"]
    if token and token in text:
        return None
    return f"Action requires confirmation. Append the confirmation token '{token}' to your command to proceed."


# ---------------------------
# Main command parser
# ---------------------------
def process_command_return(text: str) -> str:
    """
    Non-interactive command handler (suitable for web UI).
    Returns a string reply. Destructive/system actions require CONFIRM_TOKEN to be present.
    """
    if not text:
        return "No command provided."
    c = text.strip()

    # Lower for pattern matching
    lc = c.lower()

    # 1) Open URL, search or app
    m = re.match(r"^(open|launch|start)\s+(.+)$", lc)
    if m:
        target = c.split(" ", 1)[1].strip()
        # if looks like a URL or contains dot/slash -> open as is
        return open_website(target) if (("." in target) or ("/" in target) or (" " not in target and not target.isalpha())) else open_local(target)

    # 2) Play music
    if lc.startswith("play "):
        song = c[5:].strip()
        return play_music(song)

    # 3) Clipboard operations
    if lc.startswith("copy "):
        content = c[5:].strip()
        return clipboard_copy(content)
    if lc in ("paste", "paste clipboard"):
        return clipboard_paste()

    # 4) Screenshot
    if "screenshot" in lc or "take screenshot" in lc:
        return take_screenshot()

    # 5) File operations
    if lc.startswith("list "):
        arg = c.split(" ", 1)[1].strip()
        return list_dir(arg)
    if lc.startswith("create file "):
        parts = c.split(" ", 2)
        if len(parts) >= 3:
            path = parts[2]
            return make_file(path)
        return "Usage: create file <path> [content]"
    if lc.startswith("move "):
        # move <src> to <dst>
        m = re.match(r"move\s+(.+?)\s+to\s+(.+)", c, flags=re.I)
        if m:
            return move_file(m.group(1), m.group(2))
        return "Usage: move <src> to <dst>"
    if lc.startswith("delete "):
        target = c.split(" ", 1)[1].strip()
        # require confirmation token for web
        confirm = require_confirm_for_web("delete", c)
        if confirm:
            return confirm
        return delete_path(target)

    # 6) Time / Date
    if "time" in lc and "date" not in lc:
        return datetime.now().strftime("The time is %I:%M %p")
    if "date" in lc:
        return datetime.now().strftime("Today is %A, %B %d, %Y")

    # 7) System commands (dangerous)
    if "shutdown" in lc:
        if not CONFIG["ALLOW_SYSTEM_COMMANDS"]:
            return "System command disabled in config."
        confirm = require_confirm_for_web("shutdown", c)
        if confirm:
            return confirm
        return _do_system_shutdown()
    if "restart" in lc:
        if not CONFIG["ALLOW_SYSTEM_COMMANDS"]:
            return "System command disabled in config."
        confirm = require_confirm_for_web("restart", c)
        if confirm:
            return confirm
        return _do_system_restart()

    # 8) Calculator: explicit command
    if lc.startswith("calc ") or lc.startswith("calculate "):
        expr = c.split(" ", 1)[1]
        try:
            res = safe_eval(expr)
            return f"{expr} = {res}"
        except Exception as e:
            return f"Calculation error: {e}"

    # 9) Direct math expression
    if re.match(r"^[0-9\.\+\-\*\/\%\(\)\s\^e]+$", lc) or re.search(r"\b(sin|cos|tan|log|sqrt|pi|e)\b", lc):
        try:
            res = safe_eval(c)
            return f"{c} = {res}"
        except Exception:
            pass  # fall through to AI

    # 10) Small GK / question-like requests -> AI fallback
    if any(k in lc for k in ("who", "what", "when", "where", "how", "define", "explain", "?")):
        return ai_fallback(c)

    # 11) If nothing matched, try AI fallback
    return ai_fallback(c)


# Interactive version that can ask confirm for dangerous ops
def process_command(text: str) -> None:
    """
    Interactive command: performs actions and speaks replies. This will prompt for confirmations
    for destructive commands when running in terminal/CLI.
    """
    reply = process_command_return(text)

    # If the return indicates confirmation required, and we're interactive, prompt the user
    if isinstance(reply, str) and "requires confirmation" in reply.lower():
        # ask user explicitly
        speak(reply)
        speak("Do you want to proceed? Type 'yes' to confirm.")
        try:
            ans = input("Confirm (yes/no): ").strip().lower()
        except Exception:
            ans = "no"
        if ans == "yes":
            # re-run but this time allow by inserting token
            token = CONFIG["CONFIRM_TOKEN"]
            new_text = text + " " + token
            final_reply = process_command_return(new_text)
            speak(final_reply)
            return
        else:
            speak("Cancelled.")
            return

    # Otherwise speak the reply
    speak(reply)


# For testing when executed directly
if __name__ == "__main__":
    speak("Vex initialized.")
    while True:
        try:
            cmd = input("Vex> ").strip()
        except (KeyboardInterrupt, EOFError):
            speak("Goodbye.")
            break
        if not cmd:
            continue
        if cmd.lower() in ("exit", "quit"):
            speak("Goodbye.")
            break
        process_command(cmd)
