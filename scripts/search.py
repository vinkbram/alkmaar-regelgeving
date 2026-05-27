"""
Search and query tool for Alkmaar local regulations database.

Usage:
    python search.py "parkeren"                  # full-text search across everything
    python search.py --tag horeca                # find regulations by tag
    python search.py --tags                      # list all tags with counts
    python search.py --type verordening          # filter by doc_type
    python search.py --article "samenscholing"   # search within articles only
    python search.py --section "openbare orde"   # search within sections only
    python search.py --tree CVDR659124           # show section/article tree for a regulation
    python search.py --stats                     # database stats
    python search.py --unfetched [N]             # show entries without full text
    python search.py --id CVDR19478              # lookup by CVDR ID
    python search.py --list                      # list all regulations
    python search.py --export regulations.json   # export full DB as JSON
"""
import sqlite3
import sys
import json
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alkmaar_laws.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def search(query, limit=50):
    """Full-text search across regulations, articles, and sections."""
    conn = get_conn()
    results = []

    # Search regulations (title + full_text + summary)
    rows = conn.execute("""
        SELECT r.id, r.cvdr_id, r.version, r.title, r.url, r.doc_type, r.fetched,
               snippet(regulations_fts, 0, '>>>', '<<<', '...', 40) as title_match,
               snippet(regulations_fts, 1, '>>>', '<<<', '...', 60) as text_match,
               'regulation' as match_type
        FROM regulations_fts
        JOIN regulations r ON r.id = regulations_fts.rowid
        WHERE regulations_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit)).fetchall()
    results.extend(rows)

    # Search articles
    art_rows = conn.execute("""
        SELECT a.id, a.article_number, a.article_title,
               r.cvdr_id, r.version, r.title as reg_title, r.url,
               snippet(articles_fts, 1, '>>>', '<<<', '...', 60) as body_match,
               'article' as match_type
        FROM articles_fts
        JOIN articles a ON a.id = articles_fts.rowid
        JOIN regulations r ON r.id = a.regulation_id
        WHERE articles_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit)).fetchall()
    results.extend(art_rows)

    # Search sections
    sec_rows = conn.execute("""
        SELECT s.id, s.section_type, s.number, s.title as sec_title,
               r.cvdr_id, r.version, r.title as reg_title, r.url,
               snippet(sections_fts, 1, '>>>', '<<<', '...', 60) as body_match,
               'section' as match_type
        FROM sections_fts
        JOIN sections s ON s.id = sections_fts.rowid
        JOIN regulations r ON r.id = s.regulation_id
        WHERE sections_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit)).fetchall()
    results.extend(sec_rows)

    conn.close()
    return results


def search_by_tag(tag_name):
    conn = get_conn()
    rows = conn.execute("""
        SELECT r.id, r.cvdr_id, r.version, r.title, r.url, r.doc_type, r.fetched
        FROM regulations r
        JOIN regulation_tags rt ON rt.regulation_id = r.id
        JOIN tags t ON t.id = rt.tag_id
        WHERE t.name = ?
        ORDER BY r.title
    """, (tag_name.lower(),)).fetchall()
    conn.close()
    return rows


def list_tags():
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.name, COUNT(rt.regulation_id) as cnt
        FROM tags t
        JOIN regulation_tags rt ON rt.tag_id = t.id
        GROUP BY t.id
        ORDER BY cnt DESC, t.name
    """).fetchall()
    conn.close()
    return rows


def search_articles(query, limit=30):
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.article_number, a.article_title,
               r.cvdr_id, r.version, r.title as reg_title,
               snippet(articles_fts, 1, '>>>', '<<<', '...', 80) as body_match
        FROM articles_fts
        JOIN articles a ON a.id = articles_fts.rowid
        JOIN regulations r ON r.id = a.regulation_id
        WHERE articles_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit)).fetchall()
    conn.close()
    return rows


def search_sections(query, limit=30):
    conn = get_conn()
    rows = conn.execute("""
        SELECT s.section_type, s.number, s.title as sec_title,
               r.cvdr_id, r.version, r.title as reg_title,
               snippet(sections_fts, 1, '>>>', '<<<', '...', 80) as body_match
        FROM sections_fts
        JOIN sections s ON s.id = sections_fts.rowid
        JOIN regulations r ON r.id = s.regulation_id
        WHERE sections_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, limit)).fetchall()
    conn.close()
    return rows


def show_tree(cvdr_id):
    """Show the section/article tree for a regulation."""
    conn = get_conn()
    reg = conn.execute(
        "SELECT id, title, doc_type FROM regulations WHERE cvdr_id = ? ORDER BY version DESC LIMIT 1",
        (cvdr_id,),
    ).fetchone()
    if not reg:
        return None, [], []

    sections = conn.execute("""
        SELECT id, parent_id, section_type, number, title, depth, sort_order
        FROM sections WHERE regulation_id = ? ORDER BY sort_order
    """, (reg["id"],)).fetchall()

    articles = conn.execute("""
        SELECT article_number, article_title, section_id, sort_order
        FROM articles WHERE regulation_id = ? ORDER BY sort_order
    """, (reg["id"],)).fetchall()

    conn.close()
    return reg, sections, articles


def filter_by_type(doc_type):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, cvdr_id, version, title, url, doc_type FROM regulations WHERE doc_type = ? ORDER BY title",
        (doc_type,),
    ).fetchall()
    conn.close()
    return rows


def stats():
    conn = get_conn()
    s = {}
    s["total"] = conn.execute("SELECT COUNT(*) FROM regulations").fetchone()[0]
    s["fetched"] = conn.execute("SELECT COUNT(*) FROM regulations WHERE fetched = 1").fetchone()[0]
    s["with_text"] = conn.execute("SELECT COUNT(*) FROM regulations WHERE full_text IS NOT NULL AND full_text != ''").fetchone()[0]
    s["sections"] = conn.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    s["articles"] = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    s["references"] = conn.execute("SELECT COUNT(*) FROM law_references").fetchone()[0]
    s["tags"] = conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
    s["tagged_regs"] = conn.execute("SELECT COUNT(DISTINCT regulation_id) FROM regulation_tags").fetchone()[0]
    s["pending"] = s["total"] - s["fetched"]

    # doc_type breakdown
    types = conn.execute(
        "SELECT doc_type, COUNT(*) as cnt FROM regulations WHERE doc_type IS NOT NULL GROUP BY doc_type ORDER BY cnt DESC"
    ).fetchall()
    s["types"] = [(r["doc_type"], r["cnt"]) for r in types]
    conn.close()
    return s


def unfetched(limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, cvdr_id, version, title, url FROM regulations WHERE fetched = 0 ORDER BY id LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


def lookup(cvdr_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM regulations WHERE cvdr_id = ? ORDER BY version DESC",
        (cvdr_id,),
    ).fetchall()
    # Also get tags
    tags_by_reg = {}
    for r in rows:
        t = conn.execute("""
            SELECT t.name FROM tags t
            JOIN regulation_tags rt ON rt.tag_id = t.id
            WHERE rt.regulation_id = ?
        """, (r["id"],)).fetchall()
        tags_by_reg[r["id"]] = [x["name"] for x in t]
    conn.close()
    return rows, tags_by_reg


def list_all():
    conn = get_conn()
    rows = conn.execute("SELECT id, cvdr_id, version, title, url, doc_type, fetched FROM regulations ORDER BY id").fetchall()
    conn.close()
    return rows


def export_json(path):
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM regulations ORDER BY id").fetchall()
    data = []
    for r in rows:
        d = dict(r)
        # Add tags
        tags = conn.execute("""
            SELECT t.name FROM tags t
            JOIN regulation_tags rt ON rt.tag_id = t.id
            WHERE rt.regulation_id = ?
        """, (r["id"],)).fetchall()
        d["tags"] = [t["name"] for t in tags]
        data.append(d)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    conn.close()
    return len(data)


# ── CLI ──

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "--stats":
        s = stats()
        print(f"Regulations:  {s['total']} total, {s['fetched']} fetched, {s['pending']} pending")
        print(f"Sections:     {s['sections']}")
        print(f"Articles:     {s['articles']}")
        print(f"References:   {s['references']}")
        print(f"Tags:         {s['tags']} unique, {s['tagged_regs']} regulations tagged")
        if s["types"]:
            print(f"\nDoc types:")
            for t, n in s["types"]:
                print(f"  {t:30s} {n}")

    elif cmd == "--tags":
        tags = list_tags()
        if not tags:
            print("No tags yet.")
        else:
            for t in tags:
                print(f"  {t['cnt']:3d}  {t['name']}")

    elif cmd == "--tag":
        if len(sys.argv) < 3:
            print("Usage: search.py --tag horeca")
            sys.exit(1)
        tag = sys.argv[2]
        rows = search_by_tag(tag)
        if not rows:
            print(f"No regulations tagged '{tag}'")
        else:
            print(f"Regulations tagged '{tag}' ({len(rows)}):\n")
            for r in rows:
                dtype = f"[{r['doc_type']}]" if r["doc_type"] else ""
                print(f"  {r['cvdr_id']}/{r['version']}  {r['title']}  {dtype}")

    elif cmd == "--type":
        if len(sys.argv) < 3:
            print("Usage: search.py --type verordening")
            sys.exit(1)
        rows = filter_by_type(sys.argv[2])
        print(f"Found {len(rows)} regulations of type '{sys.argv[2]}':\n")
        for r in rows:
            print(f"  {r['cvdr_id']}/{r['version']}  {r['title']}")

    elif cmd == "--article":
        query = " ".join(sys.argv[2:])
        rows = search_articles(query)
        if not rows:
            print(f"No article matches for: {query}")
        else:
            print(f"Article matches for '{query}' ({len(rows)}):\n")
            for r in rows:
                print(f"  Art. {r['article_number']}  {r['article_title'] or ''}")
                print(f"  in: {r['reg_title']} ({r['cvdr_id']}/{r['version']})")
                if r["body_match"]:
                    print(f"  ...{r['body_match']}...")
                print()

    elif cmd == "--section":
        query = " ".join(sys.argv[2:])
        rows = search_sections(query)
        if not rows:
            print(f"No section matches for: {query}")
        else:
            print(f"Section matches for '{query}' ({len(rows)}):\n")
            for r in rows:
                print(f"  {r['section_type']} {r['number']}  {r['sec_title']}")
                print(f"  in: {r['reg_title']} ({r['cvdr_id']}/{r['version']})")
                if r["body_match"]:
                    print(f"  ...{r['body_match']}...")
                print()

    elif cmd == "--tree":
        if len(sys.argv) < 3:
            print("Usage: search.py --tree CVDR659124")
            sys.exit(1)
        reg, sections, articles = show_tree(sys.argv[2])
        if not reg:
            print("Not found.")
            sys.exit(1)
        print(f"{reg['title']}  [{reg['doc_type'] or '?'}]\n")

        # Build section tree
        sec_map = {s["id"]: s for s in sections}
        art_by_sec = {}
        orphan_arts = []
        for a in articles:
            sid = a["section_id"]
            if sid:
                art_by_sec.setdefault(sid, []).append(a)
            else:
                orphan_arts.append(a)

        def print_section(sec, indent=0):
            prefix = "  " * indent
            print(f"{prefix}{sec['section_type']} {sec['number'] or ''}: {sec['title']}")
            for a in art_by_sec.get(sec["id"], []):
                print(f"{prefix}  Art. {a['article_number']}  {a['article_title'] or ''}")

        # Print top-level sections, then recurse
        top = [s for s in sections if s["parent_id"] is None]
        children_of = {}
        for s in sections:
            if s["parent_id"]:
                children_of.setdefault(s["parent_id"], []).append(s)

        def print_tree(sec, indent=0):
            print_section(sec, indent)
            for child in children_of.get(sec["id"], []):
                print_tree(child, indent + 1)

        for s in top:
            print_tree(s)

        if orphan_arts:
            print(f"\n  (articles not in a section:)")
            for a in orphan_arts:
                print(f"  Art. {a['article_number']}  {a['article_title'] or ''}")

    elif cmd == "--list":
        for r in list_all():
            status = "[OK]" if r["fetched"] else "[  ]"
            dtype = f"[{r['doc_type']}]" if r["doc_type"] else ""
            print(f"{status} {r['id']:3d}  {r['cvdr_id']}/{r['version']}  {r['title']}  {dtype}")

    elif cmd == "--unfetched":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        rows = unfetched(limit)
        print(f"Showing {len(rows)} unfetched regulations:")
        for r in rows:
            print(f"  {r['id']:3d}  {r['url']}  {r['title']}")

    elif cmd == "--id":
        if len(sys.argv) < 3:
            print("Usage: search.py --id CVDR19478")
            sys.exit(1)
        rows, tags_map = lookup(sys.argv[2])
        if not rows:
            print("Not found.")
        for r in rows:
            print(f"ID:        {r['cvdr_id']}/{r['version']}")
            print(f"Title:     {r['title']}")
            print(f"URL:       {r['url']}")
            print(f"Type:      {r['doc_type'] or '-'}")
            print(f"Authority: {r['authority'] or '-'}")
            print(f"Effective: {r['effective_from'] or '?'} — {r['effective_to'] or 'heden'}")
            print(f"Category:  {r['category'] or '-'}")
            print(f"Fetched:   {'Yes' if r['fetched'] else 'No'}")
            tags = tags_map.get(r["id"], [])
            if tags:
                print(f"Tags:      {', '.join(tags)}")
            if r["summary"]:
                print(f"Summary:   {r['summary'][:200]}...")
            if r["full_text"]:
                print(f"Text:      {len(r['full_text'])} chars")
            print()

    elif cmd == "--export":
        path = sys.argv[2] if len(sys.argv) > 2 else "regulations.json"
        n = export_json(path)
        print(f"Exported {n} regulations to {path}")

    else:
        # Default: full-text search
        query = " ".join(sys.argv[1:])
        results = search(query)
        if not results:
            # Fallback to LIKE on title
            conn = get_conn()
            rows = conn.execute(
                "SELECT id, cvdr_id, version, title, url, doc_type, fetched FROM regulations WHERE title LIKE ? ORDER BY title LIMIT 20",
                (f"%{query}%",),
            ).fetchall()
            conn.close()
            if rows:
                print(f"Title matches for '{query}' ({len(rows)}):\n")
                for r in rows:
                    dtype = f"[{r['doc_type']}]" if r["doc_type"] else ""
                    print(f"  {r['cvdr_id']}/{r['version']}  {r['title']}  {dtype}")
            else:
                print(f"No results for: {query}")
        else:
            reg_results = [r for r in results if r["match_type"] == "regulation"]
            art_results = [r for r in results if r["match_type"] == "article"]
            sec_results = [r for r in results if r["match_type"] == "section"]

            if reg_results:
                print(f"=== Regulations ({len(reg_results)}) ===\n")
                for r in reg_results:
                    dtype = f"[{r['doc_type']}]" if r["doc_type"] else ""
                    print(f"  {r['cvdr_id']}/{r['version']}  {r['title']}  {dtype}")
                    if r["text_match"]:
                        print(f"    ...{r['text_match']}...")
                    print()

            if art_results:
                print(f"=== Articles ({len(art_results)}) ===\n")
                for r in art_results:
                    print(f"  Art. {r['article_number']}  {r['article_title'] or ''}")
                    print(f"  in: {r['reg_title']} ({r['cvdr_id']}/{r['version']})")
                    if r["body_match"]:
                        print(f"    ...{r['body_match']}...")
                    print()

            if sec_results:
                print(f"=== Sections ({len(sec_results)}) ===\n")
                for r in sec_results:
                    print(f"  {r['section_type']} {r['number']}  {r['sec_title']}")
                    print(f"  in: {r['reg_title']} ({r['cvdr_id']}/{r['version']})")
                    if r["body_match"]:
                        print(f"    ...{r['body_match']}...")
                    print()
