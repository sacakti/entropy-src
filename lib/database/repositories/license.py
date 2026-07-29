"""
License repository.
"""

from lib.models.database import License

from ..repository import Repository


class LicenseRepository(Repository):

    def get(self):

        cursor = self.execute(
            """
            SELECT *
            FROM licenses
            LIMIT 1
            """
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return License(
            key=row["license_key"],
            edition=row["edition"],
            customer=row["customer"],
            email=row["email"],
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            activated_at=row["activated_at"],
            status=row["status"],
            signature=row["signature"],
        )

    def save(
        self,
        license,
    ):

        self.execute(
            """
            INSERT OR REPLACE
            INTO licenses
            (
                id,
                license_key,
                edition,
                customer,
                email,
                issued_at,
                expires_at,
                activated_at,
                status,
                signature
            )
            VALUES
            (
                1,
                ?,?,?,?,?,?,?,?,?
            )
            """,
            (
                license.key,
                license.edition,
                license.customer,
                license.email,
                license.issued_at,
                license.expires_at,
                license.activated_at,
                license.status,
                license.signature,
            ),
        )

        self.commit()

    def exists(self):

        return self.get() is not None

    def delete(self):

        self.execute(
            "DELETE FROM licenses"
        )

        self.commit()
