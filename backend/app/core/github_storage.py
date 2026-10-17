"""Минимальный слой хранения csv/excel-файлов прямо в GitHub-репозитории.

Каждый модуль хранит свои данные в data/<module>/... и читает/перезаписывает
их через Contents API. SHA файла нужен GitHub'у, чтобы подтвердить, что мы
обновляем именно ту версию, которую только что прочитали (защита от
конфликтов при параллельной записи).
"""

import requests
from github import Github, GithubException

from app.config import GITHUB_BRANCH, GITHUB_REPO, GITHUB_TOKEN


def _repo():
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN не задан в переменных окружения")
    return Github(GITHUB_TOKEN).get_repo(GITHUB_REPO)


def read_file(path: str) -> tuple[str | None, str | None]:
    """Возвращает (содержимое, sha) или (None, None), если файла ещё нет.

    Для файлов больше ~1 МБ обычный Contents API отдаёт поле content пустым.
    Раньше в этом случае содержимое докачивалось через Git Blobs API —
    отдельный запрос, где GitHub всё равно кодирует файл в base64 внутри
    JSON-ответа (для 5+ МБ csv это заметно медленнее, чем raw-скачивание).
    Вместо этого запрашиваем содержимое напрямую с media type
    application/vnd.github.raw+json — GitHub отдаёт сырые байты без base64/JSON,
    без ограничения в ~1 МБ.
    """
    repo = _repo()
    try:
        content_file = repo.get_contents(path, ref=GITHUB_BRANCH)
    except GithubException as exc:
        if exc.status == 404:
            return None, None
        raise
    if content_file.content:
        content = content_file.decoded_content.decode("utf-8")
    else:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}",
            params={"ref": GITHUB_BRANCH},
            headers={
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.raw+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.text
    return content, content_file.sha


def list_files(directory: str) -> list[str]:
    """Возвращает список путей файлов в директории (не рекурсивно), либо
    пустой список, если директории ещё нет."""
    repo = _repo()
    try:
        contents = repo.get_contents(directory, ref=GITHUB_BRANCH)
    except GithubException as exc:
        if exc.status == 404:
            return []
        raise
    if not isinstance(contents, list):
        return []
    return [c.path for c in contents if c.type == "file"]


def write_file(path: str, content: str, message: str, sha: str | None = None) -> None:
    """Создаёт файл, если его не было, либо перезаписывает существующий.

    sha — версия файла, прочитанная непосредственно перед тем, как был
    посчитан content (который может опираться на то, что в файле уже есть).
    Если sha не передан (вызывающий код прочитал файл и решил, что его ещё
    нет), не подглядываем заново сами — раньше это маскировало гонку: если
    другой писатель успевал создать файл между нашим чтением и записью, мы
    тихо перезаписывали его своим content, посчитанным без учёта этих
    данных, и ни одного исключения при этом не бросалось, так что retry-цикл
    на стороне вызывающего кода (см. baggage_norm/router.py
    _process_month_sync) не срабатывал. Теперь create_file() в этой
    ситуации сам кидает GithubException(422) «sha wasn't supplied» — то же
    исключение, что и при протухшем sha у update_file, и retry-цикл его
    перехватывает одинаково в обоих случаях.
    """
    repo = _repo()
    payload = content.encode("utf-8")
    if sha is None:
        repo.create_file(path, message, payload, branch=GITHUB_BRANCH)
    else:
        repo.update_file(path, message, payload, sha, branch=GITHUB_BRANCH)
