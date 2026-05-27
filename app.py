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

CLASSIFICATION_NL = {
    "registercorrectie": ("Registercorrectie", "amber"),
    "intrekken": ("Intrekken", "red"),
    "herzien": ("Herzien", "orange"),
    "consolideren": ("Consolideren", "blue"),
    "actueel": ("Actueel", "green"),
}

@app.context_processor
def inject_helpers():
    return {"classification_nl": CLASSIFICATION_NL}

# --- ROUTES ---

@app.route("/")
def index():
    counts = {}
    for r in query("SELECT proposal_classification, COUNT(*) as n FROM regulations GROUP BY proposal_classification"):
        counts[r["proposal_classification"]] = r["n"]
    subjects = query("SELECT * FROM subjects WHERE depth=0 ORDER BY name_nl")
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
    children = query("SELECT * FROM subjects WHERE parent_id=%s ORDER BY name_nl", (subj["id"],))
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
        ORDER BY r.title
    """, (subject_ids,))
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
        WHERE rt.tag_id=%s ORDER BY r.title
    """, (tag_id,))
    return render_template("tag_detail.html", tag=tag, regulations=regulations)

@app.route("/regeling/<cvdr_id>")
def regulation(cvdr_id):
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
    refs = query("SELECT * FROM law_references WHERE regulation_id=%s ORDER BY ref_type, ref_name", (reg["id"],))
    return render_template("regulation.html", reg=reg, sections=sections,
                           articles=articles, tags=reg_tags, subjects=subjects, refs=refs)

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
