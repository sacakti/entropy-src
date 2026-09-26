# from pathlib import Path

# from .analyzer import AnalyseAnalyzer
# from .model import AnalysePolicy


# script = Path(
#     "/Users/aravinthselvaraj/Desktop/releases/H004/DBScripts/App1/test_script.sql",
# )

# policy = AnalysePolicy(
#     warning=("insert",),
#     error=(
#         "drop",
#         "truncate",
#         "delete",
#     ),
#     stop=(
#         "hardcoded",
#         "not_endwith_slash",
#         "accept",
#     ),
# )

# result = AnalyseAnalyzer().analyse(
#     path=script.parent,
#     extensions=(".sql",),
#     policy=policy,
# )

# print(
#     f"\nFiles scanned : {result.files_scanned}",
# )

# print(
#     f"Stopped       : {result.stopped}",
# )

# print(
#     f"Findings      : {len(result.findings)}",
# )

# for finding in result.findings:

#     location = (
#         f"{finding.file}:{finding.line}:{finding.column}"
#     )

#     print(
#         f"{finding.severity.upper():7} "
#         f"{finding.rule:20} "
#         f"{location} "
#         f"{finding.message}",
#     )

# from pathlib import Path

# from .parser import AnalyseParser


# script = Path(
#     "/Users/aravinthselvaraj/Desktop/releases/H004/DBScripts/App1/App1_calling_script.sql",
# )

# statements = AnalyseParser().parse(
#     script,
# )

# for index, statement in enumerate(statements, start=1):

#     print(
#         f"\nSTATEMENT {index} "
#         f"{statement.line}:{statement.column}",
#     )

#     print(
#         statement.text,
#     )

#     for token in statement.tokens:

#         print(
#             f"  {token.line}:{token.column} "
#             f"{token.token_type!r} "
#             f"{token.value!r}",
#         )

from pathlib import Path

from .analyzer import AnalyseAnalyzer
from .model import AnalysePolicy


script = Path(
    "/Users/aravinthselvaraj/Desktop/releases/H004/DBScripts/App1",
)

policy = AnalysePolicy(
    warning=(
        "insert",
        "calling_script_semicolon",
        "spool_not_at_end",

    ),
    error=(
        "drop",
        "truncate",
        "delete",
        "referenced_script_not_found",
    ),
    stop=(
        "hardcoded",
        "not_endwith_slash",
        "accept",
    ),
)

result = AnalyseAnalyzer().analyse(
    path=script,
    extensions=(".sql",),
    policy=policy,
)

print(
    f"\nFiles scanned : {result.files_scanned}",
)

print(
    f"Stopped       : {result.stopped}",
)

print(
    f"Findings      : {len(result.findings)}",
)

for finding in result.findings:
    print(
        f"{finding.severity.upper():7} "
        f"{finding.rule:30} "
        f"{finding.file}:{finding.line}:{finding.column} "
        f"{finding.message}",
    )

print(
    f"\nObjects       : {len(result.objects)}",
)

for obj in result.objects:
    print(
        f"{obj.category:5} "
        f"{obj.operation:10} "
        f"{obj.object_type:20} "
        f"{obj.name:30} "
        f"{obj.file}:{obj.line}:{obj.column}",
    )
