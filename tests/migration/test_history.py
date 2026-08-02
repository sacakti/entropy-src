from lib.migrations.history import MigrationHistory


def test_empty_history(history):

    assert history.applied() == []


def test_record(history):

    history.record(
        1,
        "Initial migration",
    )

    assert history.exists(1)


def test_latest(history):

    history.record(
        1,
        "Migration 1",
    )

    history.record(
        2,
        "Migration 2",
    )

    assert history.latest() == 2


def test_clear(history):

    history.record(
        1,
        "Migration",
    )

    history.clear()

    assert history.applied() == []
