"""Ingest all completed nl_batch_*_output.json files that haven't been ingested yet."""
import sqlite3, json, os, glob

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alkmaar_laws.db")
TRACKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nl_ingested.json")

def load_tracker():
    if os.path.exists(TRACKER):
        with open(TRACKER) as f:
            return set(json.load(f))
    return set()

def save_tracker(ingested):
    with open(TRACKER, "w") as f:
        json.dump(sorted(ingested), f)

def store(conn, results):
    c = conn.cursor()
    stored = 0
    for r in results:
        cvdr_id = r.get("cvdr_id")
        if not cvdr_id:
            continue
        if r.get("summary_nl"):
            c.execute("UPDATE regulations SET summary = ? WHERE cvdr_id = ?",
                      (r["summary_nl"], cvdr_id))
        if r.get("full_text"):
            c.execute("UPDATE regulations SET full_text = ? WHERE cvdr_id = ?",
                      (r["full_text"], cvdr_id))
        if r.get("articles"):
            reg_id = c.execute("SELECT id FROM regulations WHERE cvdr_id = ?", (cvdr_id,)).fetchone()
            if reg_id:
                reg_id = reg_id[0]
                c.execute("DELETE FROM articles WHERE regulation_id = ?", (reg_id,))
                for i, art in enumerate(r["articles"]):
                    c.execute("""INSERT INTO articles (regulation_id, article_number, article_title, body, sort_order)
                        VALUES (?, ?, ?, ?, ?)""",
                        (reg_id, art.get("number", str(i+1)), art.get("title", ""),
                         art.get("body", ""), i))
        stored += 1
    return stored

def main():
    ingested = load_tracker()
    conn = sqlite3.connect(DB)

    output_files = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "nl_batch_*_output.json")))

    total = 0
    new_files = 0
    for fpath in output_files:
        fname = os.path.basename(fpath)
        if fname in ingested:
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            n = store(conn, data)
            ingested.add(fname)
            total += n
            new_files += 1
            print(f"  {fname}: {n} regulations")
        except Exception as e:
            print(f"  ERROR {fname}: {e}")

    conn.commit()
    conn.close()
    save_tracker(ingested)

    print(f"\nIngested {new_files} new files ({total} regulations)")
    print(f"Total files ingested: {len(ingested)}/{len(output_files)} output files exist")

if __name__ == "__main__":
    main()
