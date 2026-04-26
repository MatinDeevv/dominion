#!/usr/bin/env python3
"""Legacy root launcher shim for the canonical demo launcher.

TODO: remove this compatibility wrapper after callers switch to
`aphelion-demo`.
"""

from aphelion.paper.launchers import run_demo_main


if __name__ == "__main__":
    run_demo_main()
