"""Фейковый GitHub-репозиторий для тестов слоя хранения.

Имитирует Contents API в той части, которой пользуется app/core/github_storage.py:
get_contents (файл и листинг директории), create_file, update_file.
update_file с устаревшим sha отвечает 409 — как настоящий GitHub.
Хук on_update позволяет сымитировать параллельного писателя, который
меняет файл между нашим чтением и записью.
"""

from types import SimpleNamespace
from typing import Callable, Optional

from github import GithubException


class FakeRepo:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.shas: dict[str, str] = {}
        self._counter = 0
        self.on_update: Optional[Callable[["FakeRepo", str], None]] = None
        self.update_calls: list[tuple[str, str]] = []  # (path, sha, как его передал клиент)

    def new_sha(self) -> str:
        self._counter += 1
        return f"sha{self._counter}"

    def put(self, path: str, content: str) -> None:
        self.files[path] = content.encode("utf-8")
        self.shas[path] = self.new_sha()

    def text(self, path: str) -> str:
        return self.files[path].decode("utf-8")

    def get_contents(self, path, ref=None):
        if path in self.files:
            return SimpleNamespace(
                type="file",
                path=path,
                sha=self.shas[path],
                content="base64-placeholder",  # непустой -> storage берёт decoded_content
                decoded_content=self.files[path],
            )
        children = sorted(p for p in self.files if p.startswith(path.rstrip("/") + "/"))
        direct = [p for p in children if "/" not in p[len(path.rstrip("/")) + 1:]]
        if direct:
            return [SimpleNamespace(type="file", path=p) for p in direct]
        raise GithubException(404, {"message": "Not Found"}, None)

    def create_file(self, path, message, content, branch=None):
        if path in self.files:
            raise GithubException(422, {"message": "sha wasn't supplied"}, None)
        self.files[path] = content
        self.shas[path] = self.new_sha()

    def update_file(self, path, message, content, sha, branch=None):
        self.update_calls.append((path, sha))
        if self.on_update is not None:
            self.on_update(self, path)
        if path not in self.shas or self.shas[path] != sha:
            raise GithubException(409, {"message": "is at a different sha"}, None)
        self.files[path] = content
        self.shas[path] = self.new_sha()
