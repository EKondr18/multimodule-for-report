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


def test_write_without_sha_overwrites_file_created_concurrently(fake_repo):
    # FLAG (for human review): если sha не передан (файл не существовал на
    # момент чтения), write_file заново читает sha и пишет поверх. Условной
    # проверки содержимого нет — если другой писатель успел СОЗДАТЬ файл
    # между нашим чтением и записью, его данные молча перезаписываются
    # без 409, и механизм повтора в baggage_norm не срабатывает.
    fake_repo.put("data/x.csv", "created by other writer")
    github_storage.write_file("data/x.csv", "ours, computed from empty state", "msg", None)
    assert fake_repo.text("data/x.csv") == "ours, computed from empty state"
