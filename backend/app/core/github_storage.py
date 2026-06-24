"""Минимальный слой хранения csv/excel-файлов прямо в GitHub-репозитории.

Каждый модуль хранит свои данные в data/<module>/... и читает/перезаписывает
их через Contents API. SHA файла нужен GitHub'у, чтобы подтвердить, что мы
обновляем именно ту версию, которую только что прочитали (защита от
конфликтов при параллельной записи).
"""

from base64 import b64decode

from github import Github, GithubException

from app.config import GITHUB_BRANCH, GITHUB_REPO, GITHUB_TOKEN


def _repo():
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN не задан в переменных окружения")
    return Github(GITHUB_TOKEN).get_repo(GITHUB_REPO)


def read_file(path: str) -> tuple[str | None, str | None]:
    """Возвращает (содержимое, sha) или (None, None), если файла ещё нет.

    Contents API отдаёт поле content пустым для файлов больше ~1 МБ — в этом
    случае докачиваем содержимое через Git Blobs API (лимит там — 100 МБ).
    """
    repo = _repo()
    try:
        content_file = repo.get_contents(path, ref=GITHUB_BRANCH)
    except GithubException as exc:
        if exc.status == 404:
            return None, None
        raise
    if content_file.content:
        raw = content_file.content
    else:
        raw = repo.get_git_blob(content_file.sha).content
    return b64decode(raw).decode("utf-8"), content_file.sha


def write_file(path: str, content: str, message: str, sha: str | None = None) -> None:
    """Создаёт файл, если его не было, либо перезаписывает существующий.

    sha — версия файла, прочитанная непосредственно перед обработкой; если не
    передана, будет запрошена заново.
    """
    repo = _repo()
    if sha is None:
        _, sha = read_file(path)
    payload = content.encode("utf-8")
    if sha is None:
        repo.create_file(path, message, payload, branch=GITHUB_BRANCH)
    else:
        repo.update_file(path, message, payload, sha, branch=GITHUB_BRANCH)
