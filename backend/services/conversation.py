import time
from typing import Any


MAX_TURNS = 8
TTL_SECONDS = 7200


class ConversationStore:
    def __init__(self):
        self._sessions: dict[str, dict[str, Any]] = {}

    def _cleanup(self):
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now - s["last_active"] > TTL_SECONDS]
        for sid in expired:
            del self._sessions[sid]

    def get_history(self, session_id: str, max_turns: int = 4) -> list[dict]:
        self._cleanup()
        session = self._sessions.get(session_id)
        if not session:
            return []
        return session["turns"][-max_turns:]

    def add_turn(self, session_id: str, user_msg: str, assistant_msg: str):
        self._cleanup()
        if session_id not in self._sessions:
            self._sessions[session_id] = {"turns": [], "last_active": time.time()}
        session = self._sessions[session_id]
        session["turns"].append({"user": user_msg, "assistant": assistant_msg})
        if len(session["turns"]) > MAX_TURNS:
            session["turns"] = session["turns"][-MAX_TURNS:]
        session["last_active"] = time.time()

    def reset_session(self, session_id: str):
        self._sessions.pop(session_id, None)

    def format_history(self, session_id: str) -> str:
        turns = self.get_history(session_id)
        if not turns:
            return ""
        lines = []
        for t in turns:
            lines.append(f"User: {t['user']}")
            lines.append(f"Assistant: {t['assistant']}")
        return "\n".join(lines)


store = ConversationStore()
