#!/usr/bin/env python3

from core.bootstrap import bootstrap

bootstrap()

from core.application import Application

# from test import test_console

# import sys


def main():

    app = Application()

    app.bootstrap()

    app.initialize()

    app.run()


if __name__ == "__main__":

    main()