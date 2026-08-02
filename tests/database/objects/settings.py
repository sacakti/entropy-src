from lib.database.objects.settings import SettingsTable


def test_create_users_table(connection):

    SettingsTable().create(
        connection,
    )

    assert connection.table_exists(
        "settings"
    )
