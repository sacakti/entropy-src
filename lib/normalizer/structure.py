"""
Structure-based document normalizer.
"""

from __future__ import annotations

from typing import Any

from lib.normalizer.base import BaseNormalizer


class StructureNormalizer(
    BaseNormalizer,
):
    """
    Normalize documents using a structure definition.
    """

    def normalize(
        self,
        document: Any,
        structure: dict[str, Any],
    ) -> Any:
        """
        Normalize a document using a structure definition.

        If the structure contains kind-specific rules, the rules
        matching the document's Kubernetes resource kind are used.
        """

        selected_structure = self._select_structure(
            document,
            structure,
        )

        return self._normalize(
            document,
            selected_structure,
        )

    # ------------------------------------------------------------------
    # Structure Selection
    # ------------------------------------------------------------------

    @staticmethod
    def _select_structure(
        document: Any,
        structure: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Select the structure applicable to the document.

        Structures may optionally contain:

            kinds:
              Deployment:
                ...

        If no matching kind exists, the supplied structure itself
        is used.
        """

        if not isinstance(
            document,
            dict,
        ):

            return structure

        kinds = structure.get(
            "kinds",
        )

        if not isinstance(
            kinds,
            dict,
        ):

            return structure

        kind = document.get(
            "kind",
        )

        if not isinstance(
            kind,
            str,
        ):

            return structure

        kind_structure = kinds.get(
            kind,
        )

        if not isinstance(
            kind_structure,
            dict,
        ):

            return structure

        return kind_structure

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize(
        self,
        value: Any,
        structure: dict[str, Any],
    ) -> Any:
        """
        Normalize a value using a structure definition.
        """

        if isinstance(
            value,
            dict,
        ):

            result = dict(
                value,
            )

            remove = structure.get(
                "remove",
            )

            #
            # Remove fields from the current object.
            #

            if isinstance(
                remove,
                list,
            ):

                for key in remove:

                    if isinstance(
                        key,
                        str,
                    ):

                        result.pop(
                            key,
                            None,
                        )

            #
            # Process child fields.
            #

            for key, rule in structure.items():

                if key == "remove":
                    continue

                if key not in result:
                    continue

                #
                # "field: {remove: true}"
                #

                if (
                    isinstance(
                        rule,
                        dict,
                    )
                    and rule.get("remove") is True
                ):

                    result.pop(
                        key,
                        None,
                    )

                    continue

                #
                # Nested structure.
                #

                if isinstance(
                    rule,
                    dict,
                ):

                    result[key] = self._normalize(
                        result[key],
                        rule,
                    )

            return result

        #
        # Apply the same structure to every
        # object inside a list.
        #

        if isinstance(
            value,
            list,
        ):

            return [
                (
                    self._normalize(
                        item,
                        structure,
                    )
                    if isinstance(
                        item,
                        (dict, list),
                    )
                    else item
                )
                for item in value
            ]

        return value
