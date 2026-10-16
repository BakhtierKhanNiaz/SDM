"""Run SDM from a source checkout: uv run python app.py"""

import sys

from sdm.app import main

if __name__ == "__main__":
    sys.exit(main())
