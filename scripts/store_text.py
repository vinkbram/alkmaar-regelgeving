"""
Agent ingestion tool for Alkmaar regulations database.
Accepts structured JSON (stdin or file) to populate all tables at once.

Usage:
    # Store structured data for one regulation via stdin:
    python store_text.py < regulation.json

    # Store from a file:
    python store_text.py regulation.json

    # Batch mode (array of regulations):
    python store_text.py --batch batch.json

    # Quick raw-text-only mode (no structured parsing):
    python store_text.py --raw CVDR19478 1 "full text here..."

Expected JSON schema for a single regulation:

{
    "cvdr_id": "CVDR659124",
    "version": 9,

    // --- metadata (all optional) ---
    "doc_type": "verordening",
    "authority": "raad",
    "effective_from": "2026-01-01",
    "effective_to": null,
    "adoption_date": "2021-04-06",
    "legal_basis": "Gemeentewet art. 149, 151a-d, 154, 154a, 174; Wet openbare manifestaties; Alcoholwet",
    "signatories": "A.M.C.G. Schouten, R.M. Reus",
    "citeertitel": "Algemene plaatselijke verordening gemeente Alkmaar",
    "category": "openbare_orde_en_veiligheid",

    // --- content ---
    "full_text": "raw full text of the entire document...",
    "summary": "Plain-language summary of what this regulation covers...",

    // --- hierarchy (optional, for large docs) ---
    "sections": [
        {
            "type": "hoofdstuk",
            "number": "1",
            "title": "Algemene bepalingen",
            "body": null,
            "children": [
                {
                    "type": "afdeling",
                    "number": "1",
                    "title": "Orde en veiligheid op de weg",
                    "body": null,
                    "children": []
                }
            ]
        }
    ],

    // --- articles (optional, for article-based docs) ---
    "articles": [
        {
            "number": "1:1",
            "title": "Begripsbepalingen",
            "body": "In deze verordening wordt verstaan onder: ...",
            "section_path": "Hoofdstuk 1"
        },
        {
            "number": "2:1",
            "title": "Samenscholing en ongeregeldheden",
            "body": "1. Het is verboden op een openbare plaats ...",
            "section_path": "Hoofdstuk 2 > Afdeling 1"
        }
    ],

    // --- cross-references (optional) ---
    "references": [
        {
            "type": "national_law",
            "name": "Gemeentewet",
            "detail": "artikelen 149, 151a-d, 154, 154a, 174"
        },
        {
            "type": "local_regulation",
            "name": "CVDR429464",
            "detail": "Verordening werkzaamheden kabels en leidingen"
        }
    ],

    // --- tags (optional, for searchability) ---
    // Normalized lowercase keywords. Agents should assign 3-10 relevant tags.
    "tags": [
        "openbare orde", "evenementen", "horeca", "vergunning",
        "prostitutie", "vuurwerk", "drugsoverlast", "cameratoezicht"
    ]
}

doc_type values:   verordening, beleidsregel, aanwijzingsbesluit, nota, regeling,
                   mandaatbesluit, subsidieregeling, besluit, gemeenschappelijke_regeling, overig
authority values:  raad, college, burgemeester
category values:   bestuur_en_recht, financien_en_economie, maatschappelijke_zorg,
                   milieu, onderwijs, openbare_orde_en_veiligheid,
                   ruimtelijke_ordening_verkeer, volkshuisvesting, algemeen
ref_type values:   national_law, local_regulation, eu_directive, case_law, guidance
"""
import sqlite3
import json
import sys
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alkmaar_laws.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def store_regulation(conn, data):
    """Store a single regulation with all its structured data."""
    c = conn.cursor()

    cvdr_id = data["cvdr_id"]
    version = data.get("version", 1)

    # Update the regulation row
    fields = {
        "doc_type": data.get("doc_type"),
        "authority": data.get("authority"),
        "effective_from": data.get("effective_from"),
        "effective_to": data.get("effective_to"),
        "adoption_date": data.get("adoption_date"),
        "legal_basis": data.get("legal_basis"),
        "signatories": data.get("signatories"),
        "citeertitel": data.get("citeertitel"),
        "category": data.get("category"),
        "full_text": data.get("full_text"),
        "summary": data.get("summary"),
        "fetched": 1,
    }

    # Build SET clause from non-None fields
    set_parts = []
    set_vals = []
    for k, v in fields.items():
        if v is not None:
            set_parts.append(f"{k} = ?")
            set_vals.append(v)

    if not set_parts:
        print(f"  WARNING: No data to store for {cvdr_id}/{version}")
        return False

    set_vals.extend([cvdr_id, version])
    c.execute(
        f"UPDATE regulations SET {', '.join(set_parts)} WHERE cvdr_id = ? AND version = ?",
        set_vals,
    )
    if c.rowcount == 0:
        print(f"  WARNING: {cvdr_id}/{version} not found in database")
        return False

    # Get the regulation id
    reg_id = c.execute(
        "SELECT id FROM regulations WHERE cvdr_id = ? AND version = ?",
        (cvdr_id, version),
    ).fetchone()[0]

    # Clear existing child data for re-ingestion
    c.execute("DELETE FROM articles WHERE regulation_id = ?", (reg_id,))
    c.execute("DELETE FROM sections WHERE regulation_id = ?", (reg_id,))
    c.execute("DELETE FROM law_references WHERE regulation_id = ?", (reg_id,))
    c.execute("DELETE FROM regulation_tags WHERE regulation_id = ?", (reg_id,))

    # --- Insert sections (recursive) ---
    section_map = {}  # "Hoofdstuk 2 > Afdeling 1" -> section_id

    def insert_sections(sections_list, parent_id, depth, path_prefix):
        for i, sec in enumerate(sections_list):
            sec_type = sec.get("type", "hoofdstuk")
            number = sec.get("number", "")
            title = sec.get("title", "")
            body = sec.get("body")

            c.execute(
                """INSERT INTO sections
                   (regulation_id, parent_id, section_type, number, title, body, sort_order, depth)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (reg_id, parent_id, sec_type, number, title, body, i, depth),
            )
            sec_id = c.lastrowid

            # Build path key for article matching
            label = f"{sec_type.title()} {number}".strip() if number else title
            path = f"{path_prefix} > {label}" if path_prefix else label
            section_map[path] = sec_id

            children = sec.get("children", [])
            if children:
                insert_sections(children, sec_id, depth + 1, path)

    sections = data.get("sections", [])
    if sections:
        insert_sections(sections, None, 0, "")

    # --- Insert articles ---
    articles = data.get("articles", [])
    for i, art in enumerate(articles):
        # Resolve section_id from section_path
        sec_id = None
        sec_path = art.get("section_path", "")
        if sec_path and sec_path in section_map:
            sec_id = section_map[sec_path]
        elif sec_path:
            # Try partial match: find the longest matching prefix
            for key in sorted(section_map.keys(), key=len, reverse=True):
                if key in sec_path or sec_path in key:
                    sec_id = section_map[key]
                    break

        c.execute(
            """INSERT OR REPLACE INTO articles
               (regulation_id, section_id, article_number, article_title, body, sort_order)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (reg_id, sec_id, art["number"], art.get("title"), art["body"], i),
        )

    # --- Insert references ---
    refs = data.get("references", [])
    for ref in refs:
        c.execute(
            """INSERT INTO law_references
               (regulation_id, ref_type, ref_name, ref_detail)
               VALUES (?, ?, ?, ?)""",
            (reg_id, ref.get("type", "national_law"), ref["name"], ref.get("detail")),
        )

    # --- Insert tags ---
    tags = data.get("tags", [])
    for tag_name in tags:
        tag_name = tag_name.strip().lower()
        if not tag_name:
            continue
        c.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
        tag_id = c.execute("SELECT id FROM tags WHERE name = ?", (tag_name,)).fetchone()[0]
        c.execute(
            "INSERT OR IGNORE INTO regulation_tags (regulation_id, tag_id) VALUES (?, ?)",
            (reg_id, tag_id),
        )

    conn.commit()
    n_sec = len(section_map)
    n_art = len(articles)
    n_ref = len(refs)
    n_tag = len(tags)
    print(f"  OK: {cvdr_id}/{version} — {n_sec} sections, {n_art} articles, {n_ref} refs, {n_tag} tags")
    return True


def store_raw(cvdr_id, version, text):
    """Quick raw-text-only storage."""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "UPDATE regulations SET full_text = ?, fetched = 1 WHERE cvdr_id = ? AND version = ?",
        (text, cvdr_id, version),
    )
    n = c.rowcount
    conn.commit()
    conn.close()
    return n


def ingest_all_json():
    """Find and ingest all reg_CVDR*.json files, move completed ones to ingested/."""
    import glob as globmod
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pattern = os.path.join(script_dir, "reg_CVDR*.json")
    files = sorted(globmod.glob(pattern))
    if not files:
        print("No reg_CVDR*.json files found.")
        return

    conn = get_conn()
    ok = 0
    skip = 0
    fail = 0
    for fpath in files:
        fname = os.path.basename(fpath)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            cvdr = data["cvdr_id"]
            ver = data.get("version", 1)
            row = conn.execute(
                "SELECT fetched FROM regulations WHERE cvdr_id = ? AND version = ?",
                (cvdr, ver),
            ).fetchone()
            if row and row[0] == 1:
                skip += 1
                # Still move it out of the way
                dest_dir = os.path.join(script_dir, "ingested")
                os.makedirs(dest_dir, exist_ok=True)
                os.rename(fpath, os.path.join(dest_dir, fname))
                continue
            if store_regulation(conn, data):
                ok += 1
                dest_dir = os.path.join(script_dir, "ingested")
                os.makedirs(dest_dir, exist_ok=True)
                os.rename(fpath, os.path.join(dest_dir, fname))
            else:
                fail += 1
        except Exception as e:
            print(f"  ERROR: {fname}: {e}")
            fail += 1

    conn.close()
    print(f"\nIngest complete: {ok} new, {skip} already done, {fail} failed")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python store_text.py [--ingest-all | --raw | --batch | file.json]")
        print("  --ingest-all   Auto-discover and ingest all reg_CVDR*.json files")
        print("  --raw CVDR V   Quick text-only store")
        print("  --batch f.json Batch array of regulations")
        print("  file.json      Single regulation JSON")
        sys.exit(0)

    if sys.argv[1] == "--ingest-all":
        ingest_all_json()
        sys.exit(0)

    if sys.argv[1] == "--raw":
        # Quick mode: store_text.py --raw CVDR19478 1 "text..."
        cvdr_id = sys.argv[2]
        version = int(sys.argv[3])
        text = sys.argv[4] if len(sys.argv) > 4 else sys.stdin.read()
        n = store_raw(cvdr_id, version, text)
        print(f"Updated {n} row(s) for {cvdr_id}/{version}")

    elif sys.argv[1] == "--batch":
        # Batch mode: array of regulation objects
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            items = json.load(f)
        conn = get_conn()
        ok = 0
        for item in items:
            if store_regulation(conn, item):
                ok += 1
        conn.close()
        print(f"\nBatch done: {ok}/{len(items)} stored")

    else:
        # Single regulation from file or stdin
        if os.path.isfile(sys.argv[1]):
            with open(sys.argv[1], "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.loads(sys.stdin.read())

        conn = get_conn()
        if isinstance(data, list):
            ok = 0
            for item in data:
                if store_regulation(conn, item):
                    ok += 1
            print(f"\nDone: {ok}/{len(data)} stored")
        else:
            store_regulation(conn, data)
        conn.close()
