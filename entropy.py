#!/usr/bin/env python3

from core.bootstrap import bootstrap

bootstrap()

from core.application import Application

def main():

    app = Application()

    args = app.parse()

    app.bootstrap()

    app.initialize(args)

    app.run()


if __name__ == "__main__":

    main()
