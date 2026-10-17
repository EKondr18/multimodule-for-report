"""Тесты записи в app/core/github_storage.py поверх FakeRepo."""

from app.core import github_storage


def test_write_without_sha_creates_missing_file(fake_repo):
    github_storage.write_file("data/x.csv", "a,b\n1,2\n", "msg", None)
    assert fake_repo.text("data/x.csv") == "a,b\n1,2\n"


def test_write_with_stale_sha_raises_409(fake_repo):
    fake_repo.put("data/x.csv", "old")
    stale_sha = fake_repo.shas["data/x.csv"]
    fake_repo.put("data/x.csv", "someone else")  # другой писатель
    from github import GithubException

    try:
        github_storage.write_file("data/x.csv", "mine", "msg", stale_sha)
    except GithubException as exc:
        assert exc.status == 409
    else:  # pragma: no cover - документируем, что исключение обязательно
        raise AssertionError("ожидался GithubException 409")
    assert fake_repo.text("data/x.csv") == "someone else"


def test_write_without_sha_raises_422_if_file_created_concurrently(fake_repo):
    # Если sha не передан (вызывающий код прочитал файл и решил, что его ещё
    # нет), write_file больше не подглядывает заново сам — create_file()
    # кидает GithubException(422), если файл уже существует, вместо того
    # чтобы молча перезаписать чужие данные нашим content, посчитанным без
    # их учёта. Это подключает сценарий «файл создан конкурентным писателем»
    # к тому же retry-циклу, что уже ловит протухший sha при update_file.
    fake_repo.put("data/x.csv", "created by other writer")
    from github import GithubException

    try:
        github_storage.write_file("data/x.csv", "ours, computed from empty state", "msg", None)
    except GithubException as exc:
        assert exc.status == 422
    else:  # pragma: no cover - документируем, что исключение обязательно
        raise AssertionError("ожидался GithubException 422")
    assert fake_repo.text("data/x.csv") == "created by other writer"
