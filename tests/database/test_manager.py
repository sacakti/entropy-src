def test_initialize(
    manager,
):

    manager.initialize()

    assert manager.connection.connection is not None


def test_install(
    manager,
):

    manager.install()

    assert manager.connection.table_exists(
        "schema_migrations"
    )


def test_prepare(
    manager,
):

    manager.prepare()

    assert manager.connection.table_exists(
        "users"
    )


def test_close(
    manager,
):

    manager.initialize()

    manager.close()

    assert manager.connection._connection is None
