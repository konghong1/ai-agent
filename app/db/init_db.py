"""Database initialization entrypoint.

Run via:  python -m app.db.init_db
The actual logic lives in ``app.db`` (the package ``__init__``).
"""
from . import main

if __name__ == "__main__":
    main()
