"""Legacy script shim for the canonical MT5 pipeline TUI.

TODO: remove this compatibility wrapper after callers switch to
`mt5pipe-super` or `python -m mt5pipe.tools.super_pipeline_tui`.
"""

from mt5pipe.tools.super_pipeline_tui import main


if __name__ == "__main__":
    raise SystemExit(main())
