import json
import os
import re
from filelock import FileLock
from typing import Optional, List


class JsonStore:
    GENERIC_TITLES = {"new chat", "untitled", ""}

    def __init__(self, path: str):
        self.path = path
        self.lock_path = path + ".lock"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(self.path):
            self._write({"chats": []})
        self._cleanup_empty_chats()
        self._cleanup_generic_titles()

    def _cleanup_empty_chats(self):
        data = self._read()
        chats = [c for c in data.get("chats", []) if c.get("messages")]
        if len(chats) != len(data.get("chats", [])):
            data["chats"] = chats
            self._write(data)

    def _is_generic_title(self, title: Optional[str]) -> bool:
        return not title or title.strip().lower() in self.GENERIC_TITLES

    def _make_title_from_text(self, text: str) -> Optional[str]:
        source = text.strip()
        if not source:
            return None

        source = re.sub(r"[^A-Za-z0-9 ]+", " ", source)
        source = re.sub(
            r"\b(plan|please|a|an|the|to|for|in|make|me|help|need|travel|trip|book|plan)\b",
            " ",
            source,
            flags=re.IGNORECASE,
        )
        source = re.sub(r"\s+", " ", source).strip()
        if not source:
            return None

        if len(source) > 40:
            source = source[:40].rsplit(" ", 1)[0]
        title = source.title()
        if not re.search(r"\b(Trip|Plan|Itinerary)\b", title, flags=re.IGNORECASE):
            title = f"{title} Plan"
        return title
