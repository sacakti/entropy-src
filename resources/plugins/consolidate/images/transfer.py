"""
Read the Docker commands of image_transfer.sh and write one script for all releases.

Scripts are read, never run. Only `docker pull`, `tag` and `push` count; anything else
in a script (variables, loops, its login credentials) is not carried over.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

SEPARATORS = {"&&", "||", ";", "|", "&"}

# docker options that take a separate value argument.
VALUE_OPTIONS = {"--platform"}


@dataclass(frozen=True)
class TransferImage:
    """An image a release pushes, and the source it is tagged from."""

    image: str
    source: Optional[str]
    pulled: bool


def image_repository(image: str) -> str:
    """An image reference without its tag or digest."""

    repository = image.strip().split("@", 1)[0]

    if ":" in repository.rsplit("/", 1)[-1]:
        return repository.rsplit(":", 1)[0]

    return repository


def image_path(repository: str) -> str:
    """An image repository without its registry host."""

    first, _, rest = repository.partition("/")

    if rest and ("." in first or ":" in first or first == "localhost"):
        return rest

    return repository


def image_registry(image: str) -> Optional[str]:
    """The registry host of an image, if it names one."""

    first, _, rest = image.partition("/")

    if rest and ("." in first or ":" in first or first == "localhost"):
        return first

    return None


def _logical_lines(content: str) -> Iterable[str]:
    """Lines of a script, with backslash continuations joined."""

    pending = ""

    for line in content.splitlines():

        if line.rstrip().endswith("\\"):
            pending += line.rstrip()[:-1] + " "
            continue

        yield pending + line
        pending = ""

    if pending:
        yield pending


def _commands(line: str) -> List[List[str]]:
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"

    commands: List[List[str]] = [[]]

    for token in lexer:

        if token in SEPARATORS:
            commands.append([])
        else:
            commands[-1].append(token)

    return commands


def _docker_operation(command: List[str]) -> Optional[Tuple[str, List[str]]]:
    """The operation and its positional arguments, for a docker pull/tag/push."""

    if command[:1] == ["sudo"]:
        command = command[1:]

        while command and command[0].startswith("-"):
            command = command[1:]

    if command[:2] == ["docker", "image"]:
        command = ["docker"] + command[2:]

    if len(command) < 2 or command[0] != "docker" or command[1] not in ("pull", "tag", "push"):
        return None

    positional: List[str] = []
    skip_value = False

    for argument in command[2:]:

        if skip_value:
            skip_value = False

        elif argument in VALUE_OPTIONS:
            skip_value = True

        elif not argument.startswith("-"):
            positional.append(argument)

    return command[1], positional


def parse_transfer_script(content: str, warnings: List[str], label: str) -> List[TransferImage]:
    """The images a script pushes, in order; lines it cannot use are reported."""

    pulled = set()
    sources: Dict[str, str] = {}
    pushed: List[str] = []

    for line in _logical_lines(content):

        if "docker" not in line:
            continue

        try:
            commands = _commands(line)

        except ValueError as exc:
            warnings.append(f"{label}: skipped a line that cannot be read: {exc}.")
            continue

        for command in commands:

            parsed = _docker_operation(command)

            if parsed is None:
                continue

            operation, arguments = parsed

            if operation == "pull" and arguments:
                pulled.add(arguments[0])

            elif operation == "tag" and len(arguments) >= 2:
                sources[arguments[1]] = arguments[0]

            elif operation == "push" and arguments and arguments[0] not in pushed:
                pushed.append(arguments[0])

    images: List[TransferImage] = []

    for image in pushed:

        if "$" in image:
            warnings.append(f"{label}: skipped '{image}', which uses a shell variable.")
            continue

        if "@" in image or image_repository(image) == image:
            warnings.append(f"{label}: skipped '{image}', which has no tag.")
            continue

        source = sources.get(image)

        if source is not None and "$" in source:
            warnings.append(f"{label}: skipped '{image}', whose source uses a shell variable.")
            continue

        images.append(TransferImage(image, source, source in pulled))

    return images


def render_transfer_script(images: Iterable[TransferImage]) -> str:
    """
    One script for the images to transfer. With none it does nothing and succeeds, so a
    workflow step can always run it.
    """

    images = list(images)

    logins: List[str] = []
    pulls: List[str] = []
    tags: List[List[str]] = []

    for item in images:

        for reference in (item.source if item.pulled else None, item.image):

            registry = image_registry(reference) if reference else None

            if registry and registry not in logins:
                logins.append(registry)

        if item.source is not None and item.pulled and item.source not in pulls:
            pulls.append(item.source)

        if item.source is not None:
            tags.append([item.source, item.image])

    lines = [
        "#!/bin/bash",
        "# Generated by consolidate.images: the latest image of each repository.",
        "# Logs in with the credentials Docker already holds for each registry.",
        "set -e",
        "",
    ]

    lines += [f"docker login {shlex.quote(registry)}" for registry in logins]
    lines += [f"docker pull {shlex.quote(image)}" for image in pulls]
    lines += [f"docker tag {shlex.quote(source)} {shlex.quote(target)}" for source, target in tags]
    lines += [f"docker push {shlex.quote(item.image)}" for item in images]

    if not images:
        lines.append("echo 'No images to transfer.'")

    return "\n".join(lines) + "\n"
