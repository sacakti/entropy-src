#!/usr/bin/env python3

from core.bootstrap import bootstrap

bootstrap()

from core.application import Application


def main():

    app = Application()

    global_args, argv = app.parse()

    app.bootstrap()

    app.initialize(
        global_args,
    )

    app.run(argv)


if __name__ == "__main__":

    main()
