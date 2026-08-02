"""允许 python -m pdf_to_md 调用。"""

from .cli import main


raise SystemExit(main())
