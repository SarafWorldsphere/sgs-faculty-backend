"""
Compare this module's SQLAlchemy models against the tenant kit's schema.

Run this before converting a module, not after. The kit's `src/` defines one
set of tables for every school, and a module's models were written against the
tables that school actually had. Where the two disagree, the app imports fine
and fails later at the first query — so the gap is worth seeing up front.

Three kinds of answer:

  MATCH                 every column the model declares exists in the kit
  TABLE MISSING         the kit has no table of that name at all
  COLUMN MISMATCH       the table exists, but the model wants columns it lacks

A gap is not automatically a bug in either side. It usually means the kit was
built from one school's schema and a feature was added to another school later.
Decide per table whether the kit gains the column or the module drops it.

Usage, against a local database that has had `scripts/apply.sh` run on it:

    DATABASE_URL=postgresql://swais_app_user@localhost/saraswati_sample \
        PYTHONPATH=. python scripts/check_kit_schema.py
"""

import importlib
import os
import pkgutil
import sys

from sqlalchemy import create_engine, inspect


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is required — point it at a kit-applied database.")
        return 2

    # Importing the package alone is not enough: __init__ does not pull in
    # every module, and a model that is never imported is never registered on
    # the metadata, so it silently drops out of the comparison.
    import app.models

    for module in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module(f"app.models.{module.name}")

    from app.db.session import Base

    inspector = inspect(create_engine(url))
    live = {
        table: {col["name"] for col in inspector.get_columns(table)}
        for table in inspector.get_table_names(schema="public")
    }

    matched, missing, mismatched = [], [], []
    for name, table in sorted(Base.metadata.tables.items()):
        if name not in live:
            missing.append(name)
            continue
        gap = {col.name for col in table.columns} - live[name]
        if gap:
            mismatched.append((name, sorted(gap)))
        else:
            matched.append(name)

    total = len(Base.metadata.tables)
    print(f"\nMATCH ({len(matched)}/{total})")
    for name in matched:
        print(f"   {name}")

    print(f"\nTABLE MISSING FROM KIT ({len(missing)})")
    for name in missing:
        print(f"   {name}")

    print(f"\nCOLUMN MISMATCH ({len(mismatched)})")
    for name, gap in mismatched:
        print(f"   {name:28} model wants: {', '.join(gap)}")

    print()
    return 0 if not missing and not mismatched else 1


if __name__ == "__main__":
    sys.exit(main())
