"""
Atomic batch dispatcher for Alkmaar regulations ingestion.

Usage:
    python dispatch.py claim 3                           # claim next 3 unclaimed regs, print JSON
    python dispatch.py release CVDR123                   # release a single claimed reg back to pool
    python dispatch.py release-batch batch_123           # release ALL unfetched in a batch
    python dispatch.py release-batch batch_123 CVDR456   # release batch EXCEPT CVDR456 (agent keeps that one)
    python dispatch.py status                            # show claim/fetch stats
    python dispatch.py reset-stale 30                    # release claims older than 30 min (stuck agents)
"""
import sqlite3
import sys
import json
import os
import time

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alkmaar_laws.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def ensure_columns():
    """Add dispatch columns if they don't exist yet."""
    conn = get_conn()
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(regulations)").fetchall()]
    if "claimed" not in cols:
        conn.execute("ALTER TABLE regulations ADD COLUMN claimed INTEGER DEFAULT 0")
    if "claimed_at" not in cols:
        conn.execute("ALTER TABLE regulations ADD COLUMN claimed_at REAL")
    if "batch_id" not in cols:
        conn.execute("ALTER TABLE regulations ADD COLUMN batch_id TEXT")
    conn.commit()
    conn.close()


def claim_batch(n, batch_id=None):
    """Atomically claim the next n unclaimed, unfetched regulations."""
    if batch_id is None:
        batch_id = f"batch_{int(time.time())}"

    conn = get_conn()
    # Select unclaimed, unfetched rows
    rows = conn.execute("""
        SELECT id, cvdr_id, version, title, url
        FROM regulations
        WHERE fetched = 0 AND claimed = 0
        ORDER BY id
        LIMIT ?
    """, (n,)).fetchall()

    if not rows:
        conn.close()
        return [], batch_id

    ids = [r["id"] for r in rows]
    placeholders = ",".join("?" * len(ids))
    conn.execute(f"""
        UPDATE regulations
        SET claimed = 1, claimed_at = ?, batch_id = ?
        WHERE id IN ({placeholders})
    """, [time.time(), batch_id] + ids)
    conn.commit()

    result = [{"id": r["id"], "cvdr_id": r["cvdr_id"], "version": r["version"],
               "title": r["title"], "url": r["url"]} for r in rows]
    conn.close()
    return result, batch_id


def release(cvdr_id):
    """Release a single claimed regulation back to the pool."""
    conn = get_conn()
    conn.execute("""
        UPDATE regulations SET claimed = 0, claimed_at = NULL, batch_id = NULL
        WHERE cvdr_id = ? AND fetched = 0
    """, (cvdr_id,))
    n = conn.total_changes
    conn.commit()
    conn.close()
    return n


def release_batch_remainder(batch_id, keep_cvdr_ids=None):
    """Release all unfetched items in a batch EXCEPT the ones the agent is keeping.
    Used when an agent hits a large doc and wants to drop the rest of its batch.

    Usage:
        python dispatch.py release-batch batch_123456              # release all unfetched in batch
        python dispatch.py release-batch batch_123456 CVDR123 CVDR456  # release all EXCEPT these
    """
    if keep_cvdr_ids is None:
        keep_cvdr_ids = []
    conn = get_conn()
    if keep_cvdr_ids:
        placeholders = ",".join("?" * len(keep_cvdr_ids))
        conn.execute(f"""
            UPDATE regulations SET claimed = 0, claimed_at = NULL, batch_id = NULL
            WHERE batch_id = ? AND fetched = 0 AND cvdr_id NOT IN ({placeholders})
        """, [batch_id] + keep_cvdr_ids)
    else:
        conn.execute("""
            UPDATE regulations SET claimed = 0, claimed_at = NULL, batch_id = NULL
            WHERE batch_id = ? AND fetched = 0
        """, (batch_id,))
    n = conn.total_changes
    conn.commit()
    conn.close()
    return n


def reset_stale(minutes=30):
    """Release claims older than N minutes (for stuck/failed agents)."""
    cutoff = time.time() - (minutes * 60)
    conn = get_conn()
    conn.execute("""
        UPDATE regulations SET claimed = 0, claimed_at = NULL, batch_id = NULL
        WHERE claimed = 1 AND fetched = 0 AND claimed_at < ?
    """, (cutoff,))
    n = conn.total_changes
    conn.commit()
    conn.close()
    return n


def status():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM regulations").fetchone()[0]
    fetched = conn.execute("SELECT COUNT(*) FROM regulations WHERE fetched = 1").fetchone()[0]
    claimed = conn.execute("SELECT COUNT(*) FROM regulations WHERE claimed = 1 AND fetched = 0").fetchone()[0]
    unclaimed = conn.execute("SELECT COUNT(*) FROM regulations WHERE claimed = 0 AND fetched = 0").fetchone()[0]

    # Active batches
    batches = conn.execute("""
        SELECT batch_id, COUNT(*) as cnt, MIN(claimed_at) as started
        FROM regulations
        WHERE claimed = 1 AND fetched = 0 AND batch_id IS NOT NULL
        GROUP BY batch_id
    """).fetchall()

    conn.close()
    return {
        "total": total,
        "fetched": fetched,
        "claimed": claimed,
        "unclaimed": unclaimed,
        "batches": [{"batch_id": b["batch_id"], "count": b["cnt"],
                      "age_min": round((time.time() - b["started"]) / 60, 1) if b["started"] else 0}
                     for b in batches],
    }


ensure_columns()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "claim":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
        batch_id = sys.argv[3] if len(sys.argv) > 3 else None
        items, bid = claim_batch(n, batch_id)
        if not items:
            print("No unclaimed regulations left.")
        else:
            print(json.dumps({"batch_id": bid, "items": items}, indent=2, ensure_ascii=False))

    elif cmd == "claim-multi":
        # claim-multi <num_batches> <batch_size>
        # Example: dispatch.py claim-multi 5 3  → claims 5 batches of 3
        num_batches = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        batch_size = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        all_batches = []
        for i in range(num_batches):
            letter = chr(ord('a') + i)
            bid = f"batch_{int(time.time())}_{letter}"
            items, bid = claim_batch(batch_size, bid)
            if not items:
                break
            all_batches.append({"batch_id": bid, "items": items})
        print(json.dumps(all_batches, indent=2, ensure_ascii=False))

    elif cmd == "release":
        n = release(sys.argv[2])
        print(f"Released {n} row(s)")

    elif cmd == "release-batch":
        if len(sys.argv) < 3:
            print("Usage: dispatch.py release-batch <batch_id> [CVDR_to_keep ...]")
            sys.exit(1)
        bid = sys.argv[2]
        keep = sys.argv[3:] if len(sys.argv) > 3 else []
        n = release_batch_remainder(bid, keep)
        print(f"Released {n} unclaimed reg(s) from {bid}" + (f", keeping {keep}" if keep else ""))

    elif cmd == "reset-stale":
        minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        n = reset_stale(minutes)
        print(f"Released {n} stale claim(s)")

    elif cmd == "status":
        s = status()
        print(f"Total:     {s['total']}")
        print(f"Fetched:   {s['fetched']}")
        print(f"Claimed:   {s['claimed']} (in-flight)")
        print(f"Unclaimed: {s['unclaimed']} (available)")
        if s["batches"]:
            print(f"\nActive batches:")
            for b in s["batches"]:
                print(f"  {b['batch_id']}: {b['count']} regs, {b['age_min']} min old")
    else:
        print(f"Unknown command: {cmd}")
