from lib.database.objects.license import LicensesTable


def test_create_users_table(connection):

    LicensesTable().create(
        connection,
    )

    assert connection.table_exists("licenses")
