import pytest

from lib.users.exceptions import UserNotFoundError
from tests.helpers import make_user


def test_create(repository):

    user = make_user()

    created = repository.create(user)

    assert created.id is not None
    assert created.username == "admin"


def test_count(repository):

    assert repository.count() == 0

    repository.create(make_user())

    assert repository.count() == 1


def test_any(repository):

    assert repository.any() is False

    repository.create(make_user())

    assert repository.any() is True


def test_exists(repository):

    repository.create(make_user())

    assert repository.exists("admin") is True
    assert repository.exists("unknown") is False


def test_get(repository):

    created = repository.create(make_user())

    loaded = repository.get(created.id)

    assert loaded.username == created.username


def test_get_by_username(repository):

    repository.create(make_user())

    user = repository.get_by_username("admin")

    assert user.username == "admin"


def test_list(repository):

    repository.create(make_user("charlie"))
    repository.create(make_user("alice"))
    repository.create(make_user("bob"))

    users = repository.list()

    assert [u.username for u in users] == [
        "alice",
        "bob",
        "charlie",
    ]


def test_update(repository):

    user = repository.create(make_user())

    user.full_name = "Updated Name"

    repository.update(user)

    loaded = repository.get(user.id)

    assert loaded.full_name == "Updated Name"


def test_delete(repository):

    user = repository.create(make_user())

    repository.delete(user.id)

    with pytest.raises(UserNotFoundError):
        repository.get(user.id)


def test_get_unknown_user(repository):

    with pytest.raises(UserNotFoundError):
        repository.get(999)


def test_get_unknown_username(repository):

    with pytest.raises(UserNotFoundError):
        repository.get_by_username("unknown")


def test_system_user(repository):

    user = make_user()

    user.system = True

    repository.create(user)

    system = repository.system_user()

    assert system.system is True


def test_system_user_not_found(repository):

    with pytest.raises(UserNotFoundError):
        repository.system_user()
