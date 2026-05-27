"""
Store Dutch summary + article re-extraction results.
Usage: python store_nl_results.py results_batch_NNN.json
"""
import sqlite3, json, sys, os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alkmaar_laws.db")

def store(results):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    stored = 0
    for r in results:
        cvdr_id = r.get("cvdr_id")
        if not cvdr_id:
            continue
        # Update summary
        if r.get("summary_nl"):
            c.execute("UPDATE regulations SET summary = ? WHERE cvdr_id = ?",
                      (r["summary_nl"], cvdr_id))
        # Update full_text if we fetched it
        if r.get("full_text"):
            c.execute("UPDATE regulations SET full_text = ? WHERE cvdr_id = ?",
                      (r["full_text"], cvdr_id))
        # Replace articles if provided
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
    conn.commit()
    conn.close()
    return stored

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python store_nl_results.py <json_file>")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)
    n = store(data)
    print(f"Stored {n} results from {sys.argv[1]}")
