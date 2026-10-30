import multiprocessing
import os
import sys

# A windowed (no-console) build on Windows has no stdout/stderr; print() would raise.
for name in ("stdout", "stderr"):
    if getattr(sys, name) is None:
        setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))

from ovito_tachyon.app import main  # noqa: E402

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
