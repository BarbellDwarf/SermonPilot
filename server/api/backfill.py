"""One-time ownership backfill: assign unowned sermons/jobs to the admin user.

Usage: ``python -m server.api.backfill``. Safe to re-run: only rows with
``user_id IS NULL`` are touched. Historical sermons (including the operator's)
become admin-owned so they stay visible to admins and hidden from
non-admin users (NULL = unowned/legacy = admin-visible only).
"""

from __future__ import annotations

from server.api.accounts import _ensure_columns, writable_conn


def backfill() -> dict[str, int]:
    with writable_conn() as conn:
        _ensure_columns(conn)
        admin = conn.execute(
            "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at, id LIMIT 1"
        ).fetchone()
        if admin is None:
            raise SystemExit("backfill: no admin user found; bootstrap first")
        admin_id = admin["id"]
        out: dict[str, int] = {}
        for table in ("sermons", "background_jobs"):
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).fetchone()
            if not exists:
                out[table] = 0
                continue
            cur = conn.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (admin_id,))
            out[table] = cur.rowcount
        return out


def main() -> None:
    try:
        counts = backfill()
    except SystemExit as e:
        print(str(e))
        raise
    except Exception as e:
        print(f"backfill: cannot open database ({e}); set SERMONPILOT_DB")
        raise SystemExit(1) from e
    total = sum(counts.values())
    print(
        f"backfill: reassigned {counts.get('sermons', 0)} sermons,"
        f" {counts.get('background_jobs', 0)} jobs to admin"
    )
    print(f"backfill: {total} rows total; historical sermons now admin-owned; re-run is safe")


if __name__ == "__main__":
    main()
