"""Alkmaar Regelgeving — searchable database of all 475 municipal regulations."""
import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, g, jsonify

app = Flask(__name__)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://buyingappadmin:FocusPlan2026!@buyingapp-pg.postgres.database.azure.com:5432/alkmaar_regelgeving?sslmode=require"
)

def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(DATABASE_URL)
        g.db.autocommit = True
    return g.db

def query(sql, args=None, one=False):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, args or ())
    if one:
        return cur.fetchone()
    return cur.fetchall()

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db: db.close()

# Document type hierarchy: lower number = more important
DOC_TYPE_INFO = {
    "verordening":              (1, "Verordening", "Bindende regels vastgesteld door de raad"),
    "gemeenschappelijke_regeling": (2, "Gemeenschappelijke regeling", "Samenwerkingsverband met andere gemeenten"),
    "regeling":                 (3, "Regeling", "Uitvoeringsregels van college of raad"),
    "beleidsregel":             (4, "Beleidsregel", "Beleidskader voor de uitvoering"),
    "subsidieregeling":         (4, "Subsidieregeling", "Subsidiekader en -voorwaarden"),
    "nota":                     (5, "Nota", "Beleidsnota of -visie"),
    "omgevingsvisie":           (5, "Omgevingsvisie", "Langetermijnvisie op de leefomgeving"),
    "nadere regels":            (4, "Nadere regels", "Uitwerking van een verordening"),
    "mandaatbesluit":           (6, "Mandaatbesluit", "Overdracht van bevoegdheden"),
    "ondermandaatbesluit":      (6, "Ondermandaatbesluit", "Verdere overdracht van bevoegdheden"),
    "besluit":                  (7, "Besluit", "Eenmalig of uitvoeringsbesluit"),
    "aanwijzingsbesluit":       (8, "Aanwijzingsbesluit", "Aanwijzing van locatie, persoon of gebied"),
}
DOC_TYPE_DEFAULT = (9, "Overig", "")

CLASSIFICATION_NL = {
    "registercorrectie": ("Registercorrectie", "amber"),
    "intrekken": ("Intrekken", "red"),
    "herzien": ("Herzien", "orange"),
    "consolideren": ("Consolideren", "blue"),
    "actueel": ("Actueel", "green"),
}

@app.context_processor
def inject_helpers():
    return {"classification_nl": CLASSIFICATION_NL, "doc_type_info": DOC_TYPE_INFO, "doc_type_default": DOC_TYPE_DEFAULT}

def doc_type_sort_key(doc_type):
    return DOC_TYPE_INFO.get(doc_type, DOC_TYPE_DEFAULT)[0]

def reg_sort_key(r):
    """Sort: intrekken/registercorrectie always last, then by doc_type importance, then title."""
    cls = r.get("proposal_classification", "")
    if cls in ("intrekken", "registercorrectie"):
        return (100, doc_type_sort_key(r.get("doc_type")), r.get("title") or "")
    return (0, doc_type_sort_key(r.get("doc_type")), r.get("title") or "")

# --- ROUTES ---

@app.route("/")
def index():
    counts = {}
    for r in query("SELECT proposal_classification, COUNT(*) as n FROM regulations GROUP BY proposal_classification"):
        counts[r["proposal_classification"]] = r["n"]
    subjects = query("SELECT * FROM subjects WHERE depth=0 ORDER BY name_nl")
    # Get children for each top-level subject
    for s in subjects:
        s["children"] = query("""
            SELECT s.*, COUNT(DISTINCT rs.regulation_id) as reg_count
            FROM subjects s
            LEFT JOIN regulation_subjects rs ON rs.subject_id = s.id
            WHERE s.parent_id=%s
            GROUP BY s.id, s.parent_id, s.code, s.name_nl, s.name_en, s.depth
            ORDER BY s.name_nl
        """, (s["id"],))
    return render_template("index.html", counts=counts, subjects=subjects, total=475)

@app.route("/zoeken")
def search():
    q = request.args.get("q", "").strip()
    classification = request.args.get("c", "")
    results = []
    if q:
        results = query("""
            SELECT *, ts_rank(tsv, plainto_tsquery('dutch', %s)) as rank
            FROM regulations
            WHERE tsv @@ plainto_tsquery('dutch', %s)
            ORDER BY rank DESC
            LIMIT 100
        """, (q, q))
    elif classification:
        results = query("""
            SELECT * FROM regulations WHERE proposal_classification=%s
            ORDER BY title
        """, (classification,))
    return render_template("search.html", q=q, classification=classification, results=results)

@app.route("/onderwerp/<code>")
def subject(code):
    subj = query("SELECT * FROM subjects WHERE code=%s", (code,), one=True)
    if not subj:
        return "Onderwerp niet gevonden", 404
    children = query("""
        SELECT s.*, COUNT(DISTINCT rs.regulation_id) as reg_count
        FROM subjects s
        LEFT JOIN regulation_subjects rs ON rs.subject_id = s.id
        WHERE s.parent_id=%s
        GROUP BY s.id, s.parent_id, s.code, s.name_nl, s.name_en, s.depth
        ORDER BY s.name_nl
    """, (subj["id"],))
    # Breadcrumb
    breadcrumb = [subj]
    parent = subj
    while parent["parent_id"]:
        parent = query("SELECT * FROM subjects WHERE id=%s", (parent["parent_id"],), one=True)
        breadcrumb.insert(0, parent)
    # All descendant subject IDs
    subject_ids = [subj["id"]]
    for ch in children:
        subject_ids.append(ch["id"])
        grandchildren = query("SELECT id FROM subjects WHERE parent_id=%s", (ch["id"],))
        subject_ids.extend(gc["id"] for gc in grandchildren)
    regulations = query("""
        SELECT DISTINCT r.* FROM regulations r
        JOIN regulation_subjects rs ON r.id = rs.regulation_id
        WHERE rs.subject_id = ANY(%s)
    """, (subject_ids,))
    regulations.sort(key=reg_sort_key)
    return render_template("subject.html", subject=subj, children=children,
                           breadcrumb=breadcrumb, regulations=regulations)

@app.route("/tags")
def tags():
    all_tags = query("""
        SELECT t.id, t.name, COUNT(rt.regulation_id) as cnt
        FROM tags t JOIN regulation_tags rt ON t.id = rt.tag_id
        GROUP BY t.id, t.name ORDER BY cnt DESC
    """)
    return render_template("tags.html", tags=all_tags)

@app.route("/tag/<int:tag_id>")
def tag_detail(tag_id):
    tag = query("SELECT * FROM tags WHERE id=%s", (tag_id,), one=True)
    if not tag:
        return "Tag niet gevonden", 404
    regulations = query("""
        SELECT r.* FROM regulations r
        JOIN regulation_tags rt ON r.id = rt.regulation_id
        WHERE rt.tag_id=%s
    """, (tag_id,))
    regulations.sort(key=reg_sort_key)
    return render_template("tag_detail.html", tag=tag, regulations=regulations)

@app.route("/regeling/<cvdr_id>")
def regulation(cvdr_id):
    highlight_subject = request.args.get("subject", "")
    reg = query("SELECT * FROM regulations WHERE cvdr_id=%s", (cvdr_id,), one=True)
    if not reg:
        return "Regeling niet gevonden", 404
    sections = query("SELECT * FROM sections WHERE regulation_id=%s ORDER BY sort_order", (reg["id"],))
    articles = query("SELECT * FROM articles WHERE regulation_id=%s ORDER BY sort_order", (reg["id"],))
    reg_tags = query("""
        SELECT t.* FROM tags t
        JOIN regulation_tags rt ON t.id = rt.tag_id
        WHERE rt.regulation_id=%s ORDER BY t.name
    """, (reg["id"],))
    subjects = query("""
        SELECT s.* FROM subjects s
        JOIN regulation_subjects rs ON s.id = rs.subject_id
        WHERE rs.regulation_id=%s ORDER BY s.depth, s.name_nl
    """, (reg["id"],))
    refs_raw = query("SELECT * FROM law_references WHERE regulation_id=%s ORDER BY ref_type, ref_name", (reg["id"],))
    # Enrich refs with links
    refs = []
    for r in refs_raw:
        ref = dict(r)
        ref["link"] = None
        name = r["ref_name"] or ""
        # Local CVDR references
        if name.startswith("CVDR"):
            cvdr_id = name.split()[0].split(",")[0]
            local = query("SELECT cvdr_id, title FROM regulations WHERE cvdr_id=%s", (cvdr_id,), one=True)
            if local:
                ref["link"] = f"/regeling/{local['cvdr_id']}"
                ref["link_title"] = local["title"]
        # National law links
        ref_type = (r["ref_type"] or "").lower()
        if not ref["link"] and ref_type in ("national_law", "legislation", "law", "act", "statute",
                "primary_legislation", "national legislation", "dutch law", "wet", "legal statute"):
            ref["link"] = f"https://wetten.overheid.nl/zoeken?q={name.replace(' ', '+')}"
        refs.append(ref)
    # Build article_id → subjects mapping
    art_subjects = {}
    if articles:
        art_ids = [a["id"] for a in articles]
        art_sub_rows = query("""
            SELECT ars.article_id, s.id, s.code, s.name_nl
            FROM article_subjects ars
            JOIN subjects s ON s.id = ars.subject_id
            WHERE ars.article_id = ANY(%s)
            ORDER BY s.depth, s.name_nl
        """, (art_ids,))
        for row in art_sub_rows:
            art_subjects.setdefault(row["article_id"], []).append(row)
    # Build set of article IDs that match the highlight subject
    highlighted_articles = set()
    highlight_subject_name = ""
    if highlight_subject and articles:
        hs = query("SELECT id, name_nl FROM subjects WHERE code=%s", (highlight_subject,), one=True)
        if hs:
            highlight_subject_name = hs["name_nl"]
            # Get all descendant subject IDs too
            hs_ids = [hs["id"]]
            for ch in query("SELECT id FROM subjects WHERE parent_id=%s", (hs["id"],)):
                hs_ids.append(ch["id"])
                for gc in query("SELECT id FROM subjects WHERE parent_id=%s", (ch["id"],)):
                    hs_ids.append(gc["id"])
            matched = query("""
                SELECT DISTINCT article_id FROM article_subjects
                WHERE article_id = ANY(%s) AND subject_id = ANY(%s)
            """, ([a["id"] for a in articles], hs_ids))
            highlighted_articles = {r["article_id"] for r in matched}
    return render_template("regulation.html", reg=reg, sections=sections,
                           articles=articles, tags=reg_tags, subjects=subjects,
                           refs=refs, article_subjects=art_subjects,
                           highlighted_articles=highlighted_articles,
                           highlight_subject=highlight_subject,
                           highlight_subject_name=highlight_subject_name)

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])
    results = query("""
        SELECT cvdr_id, title, proposal_classification
        FROM regulations
        WHERE tsv @@ plainto_tsquery('dutch', %s)
        ORDER BY ts_rank(tsv, plainto_tsquery('dutch', %s)) DESC
        LIMIT 10
    """, (q, q))
    return jsonify(results)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
