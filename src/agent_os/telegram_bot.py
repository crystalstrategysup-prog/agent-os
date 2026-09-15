"""Owner-only Telegram Bot API adapter for the local Codex Session Hub."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AgentOSPaths
from .session_hub import CodexRunner, discover_screens, discover_sessions
from .speech import capabilities as speech_capabilities
from .speech import transcribe

_SECRET = re.compile(r"(?i)(sk-[A-Za-z0-9_-]{12,}|(?:token|password|api[_-]?key)\s*[=:]\s*\S+)")


@dataclass(slots=True)
class ChatState:
    mode: str = "idle"
    target: str | None = None


class TelegramAPI:
    def __init__(self, token: str) -> None:
        self.base = f"https://api.telegram.org/bot{token}/"
        self.file_base = f"https://api.telegram.org/file/bot{token}/"

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        encoded: dict[str, str] = {}
        for key, value in params.items():
            encoded[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        request = urllib.request.Request(
            self.base + method,
            data=urllib.parse.urlencode(encoded).encode(),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=40) as response:
            payload = json.loads(response.read())
        if not payload.get("ok"):
            raise RuntimeError(f"telegram_{method}_failed")
        return payload["result"]

    def download(self, file_id: str, target: Path) -> Path:
        metadata = self.call("getFile", file_id=file_id)
        remote = str(metadata.get("file_path", ""))
        if not remote or remote.startswith("/") or ".." in Path(remote).parts:
            raise RuntimeError("telegram_file_path_invalid")
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with urllib.request.urlopen(self.file_base + remote, timeout=60) as response:
            body = response.read(20 * 1024 * 1024 + 1)
        if len(body) > 20 * 1024 * 1024:
            raise RuntimeError("telegram_file_too_large")
        target.write_bytes(body)
        target.chmod(0o600)
        return target


class SessionBot:
    def __init__(self, paths: AgentOSPaths, config: dict[str, Any], api: TelegramAPI) -> None:
        self.paths = paths
        self.config = config
        self.api = api
        self.runner = CodexRunner(config)
        self.states: dict[int, ChatState] = {}
        self.owner_ids = {int(item) for item in config["telegram_session_hub"]["owner_ids"]}

    def handle(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            self._callback(update["callback_query"])
        elif "message" in update:
            self._message(update["message"])

    def _authorized(self, actor_id: int, chat_id: int) -> bool:
        if actor_id in self.owner_ids:
            return True
        self.api.call("sendMessage", chat_id=chat_id, text="Access denied: owner allowlist required.")
        return False

    def _message(self, message: dict[str, Any]) -> None:
        chat_id = int(message["chat"]["id"])
        actor_id = int(message.get("from", {}).get("id", 0))
        if not self._authorized(actor_id, chat_id):
            return
        text = str(message.get("text", "")).strip()
        if text.startswith("/start"):
            self.states[chat_id] = ChatState()
            self._menu(chat_id)
            return
        commands = {
            "/sessions": "hub:sessions",
            "/screens": "hub:screens",
            "/new": "hub:new",
            "/newscreen": "hub:newscreen",
            "/capabilities": "hub:capabilities",
        }
        if text.split(maxsplit=1)[0] in commands:
            self._action(chat_id, commands[text.split(maxsplit=1)[0]])
            return
        if any(key in message for key in ("voice", "audio", "document", "photo", "video")):
            self._media(chat_id, message)
            return
        self._consume_text(chat_id, text)

    def _callback(self, query: dict[str, Any]) -> None:
        actor_id = int(query.get("from", {}).get("id", 0))
        message = query.get("message", {})
        chat_id = int(message.get("chat", {}).get("id", 0))
        if not self._authorized(actor_id, chat_id):
            return
        self.api.call("answerCallbackQuery", callback_query_id=query["id"])
        self._action(chat_id, str(query.get("data", "")))

    def _action(self, chat_id: int, action: str) -> None:
        if action == "hub:sessions":
            sessions = discover_sessions(self.config)
            buttons = [
                [{"text": _session_label(item), "callback_data": f"sess:{item.session_id}"}]
                for item in sessions
            ]
            self._send(chat_id, "Choose a Codex session:", buttons or None)
        elif action == "hub:screens":
            screens = discover_screens()
            buttons = [
                [
                    {
                        "text": f"{item.name} · {item.state} · {_short(item.codex_session_id)}",
                        "callback_data": f"scr:{item.socket}",
                    }
                ]
                for item in screens
            ]
            self._send(chat_id, "Choose a GNU Screen session:", buttons or None)
        elif action == "hub:new":
            self.states[chat_id] = ChatState(mode="new_session")
            self._send(chat_id, "Send the first task. AgentOS will create a persisted Codex session in the configured default workspace.")
        elif action == "hub:newscreen":
            self.states[chat_id] = ChatState(mode="new_screen")
            self._send(chat_id, "Send: screen-name | first task\nExample: research | Inspect the repository")
        elif action == "hub:capabilities":
            self._capabilities(chat_id)
        elif action.startswith("sess:"):
            session_id = action.removeprefix("sess:")
            known = {item.session_id for item in discover_sessions(self.config, limit=500)}
            if session_id not in known:
                self._send(chat_id, "Session is no longer available. Refresh the list.")
                return
            self.states[chat_id] = ChatState(mode="target_session", target=session_id)
            self._send(chat_id, f"Selected session {_short(session_id)}. Send text, voice or a file.")
        elif action.startswith("scr:"):
            socket = action.removeprefix("scr:")
            screen = next((item for item in discover_screens() if item.socket == socket), None)
            if not screen:
                self._send(chat_id, "Screen is no longer available. Refresh the list.")
                return
            if not screen.codex_session_id:
                self._send(chat_id, "This Screen has no provable Codex UUID, so Telegram injection is disabled.")
                return
            self.states[chat_id] = ChatState(mode="target_screen", target=socket)
            self._send(chat_id, f"Selected Screen {screen.name}. Send text, voice or a file.")

    def _consume_text(self, chat_id: int, text: str) -> None:
        if not text:
            self._send(chat_id, "Send text or use /start.")
            return
        state = self.states.get(chat_id, ChatState())
        try:
            if state.mode == "new_session":
                result = self.runner.create_session(text)
                self.states[chat_id] = ChatState("target_session", result.session_id)
                self._send(chat_id, f"New session: {_short(result.session_id)} · {result.status}")
            elif state.mode == "new_screen":
                if "|" not in text:
                    raise ValueError("screen_format_invalid")
                name, prompt = (part.strip() for part in text.split("|", 1))
                result = self.runner.create_screen(name, prompt)
                self.states[chat_id] = ChatState()
                self._send(chat_id, f"Screen {name}: {result.status}; session {_short(result.session_id)}")
            elif state.mode == "target_session" and state.target:
                result = self.runner.continue_session(state.target, text)
                self._send(chat_id, _dispatch_message(result.status, result.output))
            elif state.mode == "target_screen" and state.target:
                screen = next((item for item in discover_screens() if item.socket == state.target), None)
                if not screen:
                    raise RuntimeError("screen_disappeared")
                result = self.runner.continue_screen(screen, text)
                self._send(chat_id, f"Screen delivery: {result.status}")
            else:
                self._menu(chat_id)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            self._send(chat_id, f"AgentOS stopped safely: {type(exc).__name__}: {exc}")

    def _media(self, chat_id: int, message: dict[str, Any]) -> None:
        state = self.states.get(chat_id, ChatState())
        if state.mode not in {"target_session", "target_screen"}:
            self._send(chat_id, "Choose a session or Screen first, then send the file or voice message.")
            return
        item, kind = _telegram_file(message)
        extension = _extension(item, kind)
        target = self.paths.state / "telegram-inbox" / str(chat_id) / f"{message['message_id']}{extension}"
        try:
            self.api.download(str(item["file_id"]), target)
            if kind in {"voice", "audio", "video"}:
                prompt = transcribe(target, self.config)
                if not prompt:
                    raise RuntimeError("empty_transcription")
            else:
                caption = str(message.get("caption", "Please inspect this attachment."))
                prompt = f"{caption}\nLocal attachment: {target}"
            self._consume_text(chat_id, prompt)
        except RuntimeError as exc:
            if str(exc) == "speech_not_configured":
                self._send(chat_id, _speech_setup_text(self.config))
            else:
                self._send(chat_id, f"Media processing stopped safely: {exc}")

    def _capabilities(self, chat_id: int) -> None:
        runtime = self.runner.capabilities()
        speech = speech_capabilities(self.config)
        text = (
            f"Codex: {'ready' if runtime['codex'] else 'missing'}\n"
            f"Sessions: {len(discover_sessions(self.config))}\n"
            f"GNU Screen: {'ready' if runtime['screen'] else 'unsupported/missing'}\n"
            f"Local Whisper: {'ready' if speech['local_whisper'] else 'not configured'}\n"
            f"OpenAI transcription: {'ready' if speech['openai_sdk'] and speech['openai_key_configured'] else 'not configured'}\n\n"
            + _speech_setup_text(self.config)
        )
        self._send(chat_id, text)

    def _menu(self, chat_id: int) -> None:
        buttons = [
            [
                {"text": "Codex sessions", "callback_data": "hub:sessions"},
                {"text": "GNU Screen", "callback_data": "hub:screens"},
            ],
            [
                {"text": "New session", "callback_data": "hub:new"},
                {"text": "New Screen", "callback_data": "hub:newscreen"},
            ],
            [{"text": "Voice and files", "callback_data": "hub:capabilities"}],
        ]
        self._send(
            chat_id,
            "AgentOS Session Hub\nChoose an existing Codex/Screen session or create a new one.",
            buttons,
        )

    def _send(self, chat_id: int, text: str, buttons: list[list[dict[str, str]]] | None = None) -> None:
        params: dict[str, Any] = {"chat_id": chat_id, "text": text[:4000]}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        self.api.call("sendMessage", **params)


def run(paths: AgentOSPaths, config: dict[str, Any]) -> None:
    section = config.get("telegram_session_hub", {})
    if not section.get("enabled"):
        raise RuntimeError("telegram_session_hub_disabled")
    if not section.get("owner_ids"):
        raise RuntimeError("telegram_owner_allowlist_empty")
    token_env = str(section.get("bot_token_env", "TELEGRAM_BOT_TOKEN"))
    token = os.environ.get(token_env)
    if not token:
        raise RuntimeError("telegram_bot_token_missing")
    paths.initialize()
    api = TelegramAPI(token)
    bot = SessionBot(paths, config, api)
    offset = 0
    running = True

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while running:
        try:
            updates = api.call(
                "getUpdates",
                offset=offset,
                timeout=int(section.get("poll_timeout_seconds", 25)),
                allowed_updates=["message", "callback_query"],
            )
        except (OSError, RuntimeError, urllib.error.URLError):
            time.sleep(2)
            continue
        for update in updates:
            offset = max(offset, int(update["update_id"]) + 1)
            bot.handle(update)


def _telegram_file(message: dict[str, Any]) -> tuple[dict[str, Any], str]:
    for key in ("voice", "audio", "document", "video"):
        if key in message:
            return message[key], key
    if message.get("photo"):
        return message["photo"][-1], "photo"
    raise RuntimeError("telegram_media_unsupported")


def _extension(item: dict[str, Any], kind: str) -> str:
    filename = str(item.get("file_name", ""))
    if filename and Path(filename).suffix:
        return Path(filename).suffix[:12]
    mime = str(item.get("mime_type", ""))
    guessed = mimetypes.guess_extension(mime) if mime else None
    return guessed or {"voice": ".ogg", "photo": ".jpg", "video": ".mp4"}.get(kind, ".bin")


def _session_label(session: Any) -> str:
    workspace = Path(session.workspace).name if session.workspace else "unknown folder"
    return f"{workspace} · {_short(session.session_id)}"


def _short(value: str | None) -> str:
    return value[:8] if value else "unmapped"


def _dispatch_message(status: str, output: str) -> str:
    cleaned = _SECRET.sub("[REDACTED]", output).strip()
    tail = cleaned[-1200:] if cleaned else "No textual final output."
    return f"Codex: {status}\n\n{tail}"


def _speech_setup_text(config: dict[str, Any]) -> str:
    section = config.get("telegram_session_hub", {}).get("speech", {})
    key_env = section.get("openai_api_key_env", "OPENAI_API_KEY")
    return (
        "Voice recognition is not automatic without a configured engine.\n"
        "Option 1: install local Whisper + FFmpeg (no external API).\n"
        "Option 2: install crystal-agent-os[speech] and store an OpenAI key in "
        f"the {key_env} environment variable outside Telegram."
    )
