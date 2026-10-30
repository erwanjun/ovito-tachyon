import multiprocessing
import sys

from ovito_tachyon.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
