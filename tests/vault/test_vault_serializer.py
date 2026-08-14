from lib.vault import (
    VaultSerializationError,
    VaultSerializer,
    VaultValueType,
)


def main() -> None:

    serializer = VaultSerializer()

    # ---------------------------------------------------------
    # String
    # ---------------------------------------------------------

    value = "hello entropy"

    encoded = serializer.serialize(
        value,
        VaultValueType.STRING,
    )

    decoded = serializer.deserialize(
        encoded,
        VaultValueType.STRING,
    )

    assert decoded == value

    print("String: PASS")

    # ---------------------------------------------------------
    # Number
    # ---------------------------------------------------------

    value = 1521

    encoded = serializer.serialize(
        value,
        VaultValueType.NUMBER,
    )

    decoded = serializer.deserialize(
        encoded,
        VaultValueType.NUMBER,
    )

    assert decoded == value
    assert isinstance(decoded, int)

    print("Number: PASS")

    # ---------------------------------------------------------
    # Boolean
    # ---------------------------------------------------------

    value = True

    encoded = serializer.serialize(
        value,
        VaultValueType.BOOLEAN,
    )

    decoded = serializer.deserialize(
        encoded,
        VaultValueType.BOOLEAN,
    )

    assert decoded is True

    print("Boolean: PASS")

    # ---------------------------------------------------------
    # Array
    # ---------------------------------------------------------

    value = [
        "DEV",
        "QA",
        "PROD",
    ]

    encoded = serializer.serialize(
        value,
        VaultValueType.ARRAY,
    )

    decoded = serializer.deserialize(
        encoded,
        VaultValueType.ARRAY,
    )

    assert decoded == value
    assert isinstance(decoded, list)

    print("Array: PASS")

    # ---------------------------------------------------------
    # Object
    # ---------------------------------------------------------

    value = {
        "host": "10.10.10.20",
        "port": 1521,
        "sid": "ORCL",
        "enabled": True,
    }

    encoded = serializer.serialize(
        value,
        VaultValueType.OBJECT,
    )

    decoded = serializer.deserialize(
        encoded,
        VaultValueType.OBJECT,
    )

    assert decoded == value
    assert isinstance(decoded, dict)

    print("Object: PASS")

    # ---------------------------------------------------------
    # JSON
    # ---------------------------------------------------------

    value = [
        {
            "name": "schema1",
            "port": 1521,
        },
        {
            "name": "schema2",
            "port": 1522,
        },
    ]

    encoded = serializer.serialize(
        value,
        VaultValueType.JSON,
    )

    decoded = serializer.deserialize(
        encoded,
        VaultValueType.JSON,
    )

    assert decoded == value

    print("JSON: PASS")

    # ---------------------------------------------------------
    # Type validation
    # ---------------------------------------------------------

    try:

        serializer.serialize(
            "1521",
            VaultValueType.NUMBER,
        )

    except VaultSerializationError:

        print("Type validation: PASS")

    else:

        raise AssertionError("Invalid number value was accepted.")

    # ---------------------------------------------------------
    # Boolean must not be accepted as number
    # ---------------------------------------------------------

    try:

        serializer.serialize(
            True,
            VaultValueType.NUMBER,
        )

    except VaultSerializationError:

        print("Boolean/number validation: PASS")

    else:

        raise AssertionError("Boolean was incorrectly accepted as number.")

    print("All Vault serializer tests passed.")


if __name__ == "__main__":
    main()
