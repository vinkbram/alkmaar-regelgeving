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

# Document type hierarchy
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
    # Navigation: commissies with subdomains
    commissies = query("SELECT * FROM commissies ORDER BY id")
    for c in commissies:
        c["subdomains"] = query("""
            SELECT s.*,
                   (SELECT COUNT(DISTINCT at.article_id)
                    FROM subdomain_topics st
                    JOIN topic_tags tt ON tt.topic_id = st.topic_id
                    JOIN article_tags at ON at.tag_id = tt.tag_id
                    WHERE st.subdomain_id = s.id) as article_count
            FROM subdomains s
            WHERE s.commissie_id = %s
            ORDER BY s.name
        """, (c["id"],))
    return render_template("index.html", counts=counts, commissies=commissies, total=475)

@app.route("/onderwerp/<code>")
def subdomain(code):
    subdom = query("SELECT s.*, c.name as commissie_name, c.code as commissie_code FROM subdomains s JOIN commissies c ON c.id = s.commissie_id WHERE s.code=%s", (code,), one=True)
    if not subdom:
        return "Onderwerp niet gevonden", 404
    # Topics under this subdomain with tag counts
    topics = query("""
        SELECT t.*,
               COUNT(DISTINCT at.article_id) as article_count
        FROM topics t
        JOIN subdomain_topics st ON st.topic_id = t.id
        LEFT JOIN topic_tags tt ON tt.topic_id = t.id
        LEFT JOIN article_tags at ON at.tag_id = tt.tag_id
        WHERE st.subdomain_id = %s
        GROUP BY t.id, t.code, t.name
        ORDER BY t.name
    """, (subdom["id"],))
    # For each topic, get its tags with article count
    for tp in topics:
        tp["tags"] = query("""
            SELECT tg.id, tg.label, tg.synonyms,
                   COUNT(DISTINCT at.article_id) as article_count
            FROM tags tg
            JOIN topic_tags tt ON tt.tag_id = tg.id
            LEFT JOIN article_tags at ON at.tag_id = tg.id
            WHERE tt.topic_id = %s
            GROUP BY tg.id, tg.label, tg.synonyms
            ORDER BY tg.label
        """, (tp["id"],))
    return render_template("subdomain.html", subdomain=subdom, topics=topics)

@app.route("/topic/<code>")
def topic(code):
    tp = query("SELECT * FROM topics WHERE code=%s", (code,), one=True)
    if not tp:
        return "Onderwerp niet gevonden", 404
    # Which subdomains contain this topic (for breadcrumb)
    subdom = query("""
        SELECT s.*, c.name as commissie_name, c.code as commissie_code
        FROM subdomains s
        JOIN commissies c ON c.id = s.commissie_id
        JOIN subdomain_topics st ON st.subdomain_id = s.id
        WHERE st.topic_id = %s
        LIMIT 1
    """, (tp["id"],), one=True)
    # Tags under this topic with article count
    tags = query("""
        SELECT tg.id, tg.label, tg.synonyms,
               COUNT(DISTINCT at.article_id) as article_count
        FROM tags tg
        JOIN topic_tags tt ON tt.tag_id = tg.id
        LEFT JOIN article_tags at ON at.tag_id = tg.id
        WHERE tt.topic_id = %s
        GROUP BY tg.id, tg.label, tg.synonyms
        ORDER BY tg.label
    """, (tp["id"],))
    # All regulations that have articles with any of these tags
    tag_ids = [t["id"] for t in tags]
    regulations = []
    if tag_ids:
        regulations = query("""
            SELECT DISTINCT r.* FROM regulations r
            JOIN articles a ON a.regulation_id = r.id
            JOIN article_tags at ON at.article_id = a.id
            WHERE at.tag_id = ANY(%s)
        """, (tag_ids,))
        regulations.sort(key=reg_sort_key)
    return render_template("topic.html", topic=tp, subdomain=subdom, tags=tags, regulations=regulations)

@app.route("/tag/<int:tag_id>")
def tag_detail(tag_id):
    tag = query("SELECT * FROM tags WHERE id=%s", (tag_id,), one=True)
    if not tag:
        return "Tag niet gevonden", 404
    # Which topic(s) contain this tag (for breadcrumb)
    topic = query("""
        SELECT t.*, s.code as subdomain_code, s.name as subdomain_name,
               c.name as commissie_name, c.code as commissie_code
        FROM topics t
        JOIN topic_tags tt ON tt.topic_id = t.id
        JOIN subdomain_topics st ON st.subdomain_id = (
            SELECT st2.subdomain_id FROM subdomain_topics st2
            WHERE st2.topic_id = t.id LIMIT 1
        )
        JOIN subdomains s ON s.id = st.subdomain_id
        JOIN commissies c ON c.id = s.commissie_id
        WHERE tt.tag_id = %s
        LIMIT 1
    """, (tag_id,), one=True)
    # Regulations with this tag, including summary and article count for this tag
    regs_with_tag = query("""
        SELECT r.cvdr_id, r.title, r.doc_type, r.proposal_classification, r.summary,
               COUNT(DISTINCT at.article_id) as tag_count
        FROM regulations r
        JOIN articles a ON a.regulation_id = r.id
        JOIN article_tags at ON at.article_id = a.id
        WHERE at.tag_id = %s
        GROUP BY r.cvdr_id, r.title, r.doc_type, r.proposal_classification, r.summary
        ORDER BY r.title
    """, (tag_id,))
    reg_list = sorted(regs_with_tag, key=lambda r: reg_sort_key(r))
    return render_template("tag_detail.html", tag=tag, topic=topic, reg_groups=reg_list)

@app.route("/tags")
def tags():
    all_tags = query("""
        SELECT tg.id, tg.label, tg.synonyms,
               COUNT(DISTINCT at.article_id) as cnt
        FROM tags tg
        LEFT JOIN article_tags at ON at.tag_id = tg.id
        GROUP BY tg.id, tg.label, tg.synonyms
        ORDER BY tg.label
    """)
    return render_template("tags.html", tags=all_tags)

@app.route("/zoeken")
def search():
    q = request.args.get("q", "").strip()
    classification = request.args.get("c", "")
    results = []
    matching_tags = []
    if q and classification:
        results = query("""
            SELECT *, ts_rank(tsv, plainto_tsquery('dutch', %s)) as rank
            FROM regulations
            WHERE tsv @@ plainto_tsquery('dutch', %s)
              AND proposal_classification = %s
            ORDER BY rank DESC
            LIMIT 100
        """, (q, q, classification))
    elif q:
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
    if q:
        q_lower = q.lower()
        matching_tags = query("""
            SELECT tg.id, tg.label, tg.synonyms,
                   COUNT(DISTINCT at.article_id) as cnt
            FROM tags tg
            LEFT JOIN article_tags at ON at.tag_id = tg.id
            WHERE LOWER(tg.label) LIKE %s
               OR LOWER(tg.synonyms) LIKE %s
            GROUP BY tg.id, tg.label, tg.synonyms
            ORDER BY tg.label
        """, (f"%{q_lower}%", f"%{q_lower}%"))
    return render_template("search.html", q=q, classification=classification,
                           results=results, matching_tags=matching_tags)

@app.route("/regeling/<cvdr_id>")
def regulation(cvdr_id):
    highlight_tag = request.args.get("tag", "")
    reg = query("SELECT * FROM regulations WHERE cvdr_id=%s", (cvdr_id,), one=True)
    if not reg:
        return "Regeling niet gevonden", 404
    sections = query("SELECT * FROM sections WHERE regulation_id=%s ORDER BY sort_order", (reg["id"],))
    articles = query("SELECT * FROM articles WHERE regulation_id=%s ORDER BY sort_order", (reg["id"],))
    refs_raw = query("SELECT * FROM law_references WHERE regulation_id=%s ORDER BY ref_type, ref_name", (reg["id"],))
    # Enrich refs with links — prefer link_url from database
    refs = []
    for r in refs_raw:
        ref = dict(r)
        ref["link"] = None
        ref["link_title"] = None
        # Use pre-resolved link_url if available
        link_url = r.get("link_url") or ""
        if link_url.startswith("/regeling/"):
            # Internal link — resolve title
            cvdr = link_url.replace("/regeling/", "")
            local = query("SELECT cvdr_id, title FROM regulations WHERE cvdr_id=%s", (cvdr,), one=True)
            if local:
                ref["link"] = link_url
                ref["link_title"] = local["title"]
        elif link_url.startswith("https://"):
            ref["link"] = link_url
        else:
            # Fallback: try to match CVDR refs by name
            name = r["ref_name"] or ""
            if name.startswith("CVDR"):
                cvdr = name.split()[0].split(",")[0]
                local = query("SELECT cvdr_id, title FROM regulations WHERE cvdr_id=%s", (cvdr,), one=True)
                if local:
                    ref["link"] = f"/regeling/{local['cvdr_id']}"
                    ref["link_title"] = local["title"]
        refs.append(ref)
    # Article tags
    art_tags = {}
    if articles:
        art_ids = [a["id"] for a in articles]
        art_tag_rows = query("""
            SELECT at.article_id, tg.id, tg.label
            FROM article_tags at
            JOIN tags tg ON tg.id = at.tag_id
            WHERE at.article_id = ANY(%s)
            ORDER BY tg.label
        """, (art_ids,))
        for row in art_tag_rows:
            art_tags.setdefault(row["article_id"], []).append(row)
    # Distinct tags for this regulation (derived from article tags)
    reg_tags = query("""
        SELECT DISTINCT tg.id, tg.label
        FROM tags tg
        JOIN article_tags at ON at.tag_id = tg.id
        JOIN articles a ON a.id = at.article_id
        WHERE a.regulation_id = %s
        ORDER BY tg.label
    """, (reg["id"],))
    # Highlight articles by tag
    highlighted_articles = set()
    highlight_tag_label = ""
    if highlight_tag:
        try:
            ht_id = int(highlight_tag)
            ht = query("SELECT id, label FROM tags WHERE id=%s", (ht_id,), one=True)
            if ht:
                highlight_tag_label = ht["label"]
                matched = query("""
                    SELECT DISTINCT article_id FROM article_tags
                    WHERE article_id = ANY(%s) AND tag_id = %s
                """, ([a["id"] for a in articles], ht_id))
                highlighted_articles = {r["article_id"] for r in matched}
        except ValueError:
            pass
    return render_template("regulation.html", reg=reg, sections=sections,
                           articles=articles, reg_tags=reg_tags,
                           refs=refs, article_tags=art_tags,
                           highlighted_articles=highlighted_articles,
                           highlight_tag=highlight_tag,
                           highlight_tag_label=highlight_tag_label)

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
