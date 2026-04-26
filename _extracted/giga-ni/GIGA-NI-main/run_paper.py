#!/usr/bin/env python3
"""Legacy root launcher shim for the canonical paper launcher.

TODO: remove this compatibility wrapper after callers switch to
`aphelion-paper` or `aphelion paper`.
"""

from aphelion.paper.launchers import run_paper_main


if __name__ == "__main__":
    run_paper_main()
