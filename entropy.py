#!/usr/bin/env python3

from core.application import Application
from test import test_console

import sys


def main():

    app = Application()

    app.initialize()


if __name__ == "__main__":

    if sys.argv[1:] and sys.argv[1] == "test":

        test_console()

    else:
        main()