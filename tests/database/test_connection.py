def test_open(connection):

    assert connection.connection is not None


def test_execute(connection):

    connection.execute(
        """
        CREATE TABLE test
        (
            id INTEGER
        )
        """
    )

    assert connection.table_exists("test")


def test_fetchone(connection):

    connection.execute("CREATE TABLE test(id INTEGER)")

    connection.execute("INSERT INTO test VALUES (1)")

    row = connection.fetchone("SELECT * FROM test")

    assert row["id"] == 1


def test_fetchall(connection):

    connection.execute("CREATE TABLE test(id INTEGER)")

    connection.execute("INSERT INTO test VALUES (1)")

    connection.execute("INSERT INTO test VALUES (2)")

    rows = connection.fetchall("SELECT * FROM test")

    assert len(rows) == 2


def test_transaction_commit(connection):

    with connection.transaction():

        connection.execute("CREATE TABLE test(id INTEGER)")

    assert connection.table_exists("test")


def test_transaction_rollback(connection):

    connection.execute(
        """
        CREATE TABLE test
        (
            id INTEGER
        )
        """
    )

    try:

        with connection.transaction():

            connection.execute("INSERT INTO test VALUES (1)")

            raise RuntimeError()

    except RuntimeError:
        pass

    rows = connection.fetchall("SELECT * FROM test")

    assert len(rows) == 0
