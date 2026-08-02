from lib.database.objects.users import UsersTable


def test_create_users_table(connection):

    UsersTable().create(
        connection,
    )

    assert connection.table_exists(
        "users"
    )
