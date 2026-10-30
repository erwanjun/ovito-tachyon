import multiprocessing
import os
import sys
import traceback

# A windowed (no-console) build on Windows has no stdout/stderr; print() would raise.
for name in ("stdout", "stderr"):
    if getattr(sys, name) is None:
        setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if sys.argv[1:2] == ["--selftest"]:
        # Never let an error dialog block an unattended self-test: log the traceback and exit.
        out = sys.argv[2] if len(sys.argv) > 2 else "selftest_out"
        try:
            from ovito_tachyon.app import main
            sys.exit(main())
        except Exception:
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, "selftest.log"), "a", encoding="utf-8") as log:
                log.write(traceback.format_exc())
            sys.exit(1)
    from ovito_tachyon.app import main

    sys.exit(main())
