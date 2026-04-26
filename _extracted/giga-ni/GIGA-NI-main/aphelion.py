#!/usr/bin/env python3
"""Legacy root launcher shim for the package-owned TUI entry point.

TODO: remove this compatibility wrapper after downstream tooling switches to
`aphelion-tui` or `python -m aphelion`.
"""

from aphelion.tui.launcher import main


if __name__ == "__main__":
    main()
