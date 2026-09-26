from pathlib import Path

from resources.plugins.sqlplus.analyse.parser import AnalyseParser


script = Path(
    "/Users/aravinthselvaraj/Desktop/releases/H004/DBScripts/App1/test_script.sql",
)

statements = AnalyseParser().parse(
    script,
)

for statement in statements:

    print(
        f"\nSTATEMENT {statement.line}:{statement.column}",
    )

    print(statement.text)

    for token in statement.tokens:

        print(
            f"  {token.line}:{token.column} "
            f"{token.token_type!r} "
            f"{token.value!r}",
        )
