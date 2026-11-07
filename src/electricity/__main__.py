"""``python -m electricity`` 入口（等价于 ``bdfetch``）。"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
