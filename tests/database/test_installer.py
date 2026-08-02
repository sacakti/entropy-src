from lib.database.installer import DatabaseInstaller


def test_install(connection):

    installer = DatabaseInstaller()

    installer.install(
        connection,
    )

    assert connection.table_exists(
        "schema_migrations"
    )

    assert connection.table_exists(
        "settings"
    )

    assert connection.table_exists(
        "licenses"
    )

    assert connection.table_exists(
        "plugin_registry"
    )

    assert connection.table_exists(
        "users"
    )

    assert connection.table_exists(
        "workflows"
    )
