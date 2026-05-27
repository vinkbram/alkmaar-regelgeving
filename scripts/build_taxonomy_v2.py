"""
Three-tier subject taxonomy for Alkmaar laws database.
Domain (8) -> Subdomain (~20) -> Topic (~45) -> Tags
Articles also get classified, not just regulations.
"""
import sqlite3
import re

DB = "C:/Users/Bram Vink/alkmaar-laws/alkmaar_laws.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

# === RECREATE TABLES ===
for t in ["article_subjects", "regulation_subjects", "tag_subject_map", "subjects"]:
    c.execute(f"DROP TABLE IF EXISTS {t}")

c.execute("""
    CREATE TABLE subjects (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_id   INTEGER REFERENCES subjects(id),
        code        TEXT NOT NULL UNIQUE,
        name_nl     TEXT NOT NULL,
        name_en     TEXT NOT NULL,
        depth       INTEGER DEFAULT 0   -- 0=domain, 1=subdomain, 2=topic
    )
""")

c.execute("""
    CREATE TABLE tag_subject_map (
        tag_pattern TEXT NOT NULL,
        subject_id  INTEGER NOT NULL REFERENCES subjects(id),
        PRIMARY KEY (tag_pattern, subject_id)
    )
""")

c.execute("""
    CREATE TABLE regulation_subjects (
        regulation_id INTEGER NOT NULL REFERENCES regulations(id),
        subject_id    INTEGER NOT NULL REFERENCES subjects(id),
        confidence    REAL DEFAULT 1.0,
        PRIMARY KEY (regulation_id, subject_id)
    )
""")

c.execute("""
    CREATE TABLE article_subjects (
        article_id    INTEGER NOT NULL REFERENCES articles(id),
        subject_id    INTEGER NOT NULL REFERENCES subjects(id),
        confidence    REAL DEFAULT 1.0,
        PRIMARY KEY (article_id, subject_id)
    )
""")

c.execute("CREATE INDEX idx_regsub_reg ON regulation_subjects(regulation_id)")
c.execute("CREATE INDEX idx_regsub_sub ON regulation_subjects(subject_id)")
c.execute("CREATE INDEX idx_artsub_art ON article_subjects(article_id)")
c.execute("CREATE INDEX idx_artsub_sub ON article_subjects(subject_id)")

# === THREE-TIER TAXONOMY ===
# Format: (code, name_nl, name_en, parent_code, tag_patterns)

taxonomy = [
    # =============================================
    # DOMAIN 1: BESTUUR & ORGANISATIE
    # =============================================
    ("bestuur", "Bestuur & Organisatie", "Governance & Organization", None, []),

    # Subdomain: Democratie & Vertegenwoordiging
    ("bestuur.democratie", "Democratie & Vertegenwoordiging", "Democracy & Representation", "bestuur", []),
    ("bestuur.democratie.raad", "Gemeenteraad & Commissies", "Council & Committees", "bestuur.democratie",
     ["gemeenteraad", "raadscommissie", "rekenkamer", "auditcommissie", "reglement van orde", "fractieondersteuning"]),
    ("bestuur.democratie.verkiezingen", "Verkiezingen & Burgerparticipatie", "Elections & Participation", "bestuur.democratie",
     ["verkiezingen", "stembureau", "stemlokalen", "referendum", "burgerinitiatief", "uitdaagrecht", "participatie"]),
    ("bestuur.democratie.integriteit", "Integriteit & Gedragscodes", "Integrity & Conduct", "bestuur.democratie",
     ["integriteit", "gedragscode", "agressieprotocol", "vertrouwenscommissie", "geheimhouding"]),

    # Subdomain: Ambtelijke Organisatie
    ("bestuur.organisatie", "Ambtelijke Organisatie", "Administrative Organization", "bestuur", []),
    ("bestuur.organisatie.mandaten", "Mandaten & Bevoegdheden", "Mandates & Authority", "bestuur.organisatie",
     ["mandaat", "ondermandaat", "bevoegdheden", "delegatie", "volmacht", "machtiging", "bevoegdhedenregister"]),
    ("bestuur.organisatie.griffie", "Griffie & Personeel", "Clerk & Personnel", "bestuur.organisatie",
     ["griffier", "griffie", "werkgeverscommissie", "rechtspositie", "ambtelijke bijstand"]),
    ("bestuur.organisatie.financieel", "Financieel Beheer", "Financial Management", "bestuur.organisatie",
     ["treasury", "investeren", "afschrijven", "reserves", "voorzieningen", "weerstandsvermogen", "kostprijs", "budget", "controleverordening"]),

    # Subdomain: Rechtsbescherming & Informatie
    ("bestuur.recht", "Rechtsbescherming & Informatie", "Legal Protection & Information", "bestuur", []),
    ("bestuur.recht.klachten", "Klachten & Bezwaar", "Complaints & Objections", "bestuur.recht",
     ["klachtenbehandeling", "bezwaar", "ombudsman", "klachtencommissie", "nadeelcompensatie"]),
    ("bestuur.recht.privacy", "Privacy & Registraties", "Privacy & Registrations", "bestuur.recht",
     ["privacy", "persoonsgegevens", "basisregistratie personen", "brp", "gegevensbescherming", "burgerlijke stand", "naamgeving"]),
    ("bestuur.recht.archief", "Archief & Informatiebeheer", "Archives & Information", "bestuur.recht",
     ["archief", "informatiebeheer", "archiefverordening", "transparantie", "informatieplicht", "bekendmakingswet"]),

    # Subdomain: Samenwerking
    ("bestuur.samenwerking", "Regionale Samenwerking", "Regional Cooperation", "bestuur", []),
    ("bestuur.samenwerking.gr", "Gemeenschappelijke Regelingen", "Joint Arrangements", "bestuur.samenwerking",
     ["gemeenschappelijke regeling", "regio deal", "gisd", "veiligheidsregio", "ggd", "zaffier", "milieudienst"]),

    # =============================================
    # DOMAIN 2: OPENBARE ORDE & VEILIGHEID
    # =============================================
    ("veiligheid", "Openbare Orde & Veiligheid", "Public Order & Safety", None, []),

    # Subdomain: Toezicht & Handhaving
    ("veiligheid.toezicht", "Toezicht & Handhaving", "Supervision & Enforcement", "veiligheid", []),
    ("veiligheid.toezicht.camera", "Cameratoezicht", "Camera Surveillance", "veiligheid.toezicht",
     ["cameratoezicht", "camera", "bodycam", "videobeveiliging"]),
    ("veiligheid.toezicht.handhaving", "Handhaving & Opsporingsambtenaren", "Enforcement Officers", "veiligheid.toezicht",
     ["handhaving", "toezichthouder", "opsporingsambtenaar", "vth", "verblijfsontzegging"]),
    ("veiligheid.toezicht.brand", "Brandveiligheid", "Fire Safety", "veiligheid.toezicht",
     ["brandveiligheid", "brandweer", "brandbeveiliging"]),

    # Subdomain: Openbare Orde
    ("veiligheid.orde", "Openbare Orde", "Public Order", "veiligheid", []),
    ("veiligheid.orde.drugs", "Drugs & Verslavingszorg", "Drugs & Addiction", "veiligheid.orde",
     ["damocles", "opiumwet", "drugs", "coffeeshop", "lachgas"]),
    ("veiligheid.orde.alcohol", "Alcohol & Horeca", "Alcohol & Hospitality", "veiligheid.orde",
     ["alcohol", "alcoholverbod", "horeca", "drank", "horecaverordening"]),
    ("veiligheid.orde.prostitutie", "Prostitutie & Seksbranche", "Sex Work", "veiligheid.orde",
     ["prostitutie", "seksbranche", "seksbedrijf", "mensenhandel"]),
    ("veiligheid.orde.overlast", "Overlast & Gebiedsverboden", "Nuisance & Area Bans", "veiligheid.orde",
     ["overlast", "bedelverbod", "gebiedsaanwijzing", "samenscholing"]),
    ("veiligheid.orde.evenementen", "Evenementen & Festiviteiten", "Events & Festivals", "veiligheid.orde",
     ["evenementen", "kermis", "collectieve festiviteiten", "vuurwerk", "zomerkermis"]),

    # =============================================
    # DOMAIN 3: MOBILITEIT & RUIMTE
    # =============================================
    ("mobiliteit", "Mobiliteit & Ruimte", "Mobility & Spatial Planning", None, []),

    # Subdomain: Verkeer & Parkeren
    ("mobiliteit.verkeer", "Verkeer & Parkeren", "Traffic & Parking", "mobiliteit", []),
    ("mobiliteit.verkeer.parkeren", "Parkeren", "Parking", "mobiliteit.verkeer",
     ["parkeren", "parkeerbelasting", "parkeervergunning", "parkeerzone", "parkeerfonds", "parkeergarage", "betaald parkeren", "parkeerverordening", "parkeernorm"]),
    ("mobiliteit.verkeer.wegverkeer", "Wegverkeer & Fietsen", "Road Traffic & Cycling", "mobiliteit.verkeer",
     ["verkeer", "fiets", "bromfiets", "voertuig", "wegsleep", "snelheidsbeperking", "laadpalen"]),
    ("mobiliteit.verkeer.water", "Vaarwegen & Scheepvaart", "Waterways & Navigation", "mobiliteit.verkeer",
     ["openbaar water", "scheepvaart", "ligplaats", "vaartuigen", "havengelden"]),

    # Subdomain: Ruimtelijke Ontwikkeling
    ("mobiliteit.ruimte", "Ruimtelijke Ontwikkeling", "Spatial Development", "mobiliteit", []),
    ("mobiliteit.ruimte.ordening", "Ruimtelijke Ordening & Omgevingsplan", "Spatial Planning", "mobiliteit.ruimte",
     ["ruimtelijke ordening", "omgevingsplan", "omgevingsvisie", "bestemmingsplan", "welstand", "omgevingswet", "stedenbouw", "ontwikkelkader", "gebiedsoverstijgende voorzieningen"]),
    ("mobiliteit.ruimte.infra", "Infrastructuur & Kabels", "Infrastructure & Utilities", "mobiliteit.ruimte",
     ["infrastructuur", "kabels", "leidingen", "kunstwerken", "openbare verlichting", "wegen", "antenne", "stedelijk water", "riolering"]),

    # =============================================
    # DOMAIN 4: FINANCIEN & ECONOMIE
    # =============================================
    ("financien", "Financien & Economie", "Finance & Economy", None, []),

    # Subdomain: Belastingen & Heffingen
    ("financien.belasting", "Belastingen & Heffingen", "Taxes & Levies", "financien", []),
    ("financien.belasting.lokaal", "Gemeentelijke Belastingen", "Municipal Taxes", "financien.belasting",
     ["belasting", "heffing", "precariobelasting", "toeristenbelasting", "forensenbelasting", "reclamebelasting", "rioolheffing", "onroerende zaak", "baatbelasting", "kwijtschelding", "leges", "afvalstoffenheffing"]),

    # Subdomain: Subsidies
    ("financien.subsidie", "Subsidies & Bekostiging", "Subsidies & Funding", "financien", []),
    ("financien.subsidie.regels", "Subsidieregels & Plafonds", "Subsidy Rules", "financien.subsidie",
     ["subsidie", "subsidies", "subsidieplafond", "subsidieregeling", "bekostiging", "esf"]),

    # Subdomain: Economie
    ("financien.economie", "Economie & Ondernemerschap", "Economy & Enterprise", "financien", []),
    ("financien.economie.markt", "Markten & Winkels", "Markets & Shops", "financien.economie",
     ["economie", "ondernemerschap", "winkeltijden", "markt", "sponsoring", "opkopers", "kaasmarkt"]),

    # =============================================
    # DOMAIN 5: SOCIAAL DOMEIN
    # =============================================
    ("sociaal", "Sociaal Domein", "Social Domain", None, []),

    # Subdomain: Zorg & Ondersteuning
    ("sociaal.zorg", "Zorg & Ondersteuning", "Care & Support", "sociaal", []),
    ("sociaal.zorg.wmo", "Wmo & Maatschappelijke Ondersteuning", "Social Support (Wmo)", "sociaal.zorg",
     ["wmo", "maatschappelijke ondersteuning", "mantelzorg", "huishoudelijke hulp"]),
    ("sociaal.zorg.jeugd", "Jeugdhulp & Jeugdzorg", "Youth Care", "sociaal.zorg",
     ["jeugdhulp", "jeugd", "jeugdzorg", "kinderopvang", "peuteropvang"]),
    ("sociaal.zorg.gezondheid", "Volksgezondheid", "Public Health", "sociaal.zorg",
     ["gezondheid", "ggd", "sociaal medisch"]),

    # Subdomain: Werk & Inkomen
    ("sociaal.werk", "Werk & Inkomen", "Employment & Income", "sociaal", []),
    ("sociaal.werk.participatie", "Participatiewet & Bijstand", "Participation & Welfare", "sociaal.werk",
     ["participatiewet", "bijstand", "tegenprestatie", "re-integratie", "minimabeleid", "inkomenstoeslag", "schuldhulp", "alkmaarpass"]),
    ("sociaal.werk.inburgering", "Inburgering & Integratie", "Civic Integration", "sociaal.werk",
     ["inburgering", "integratie", "statushouders", "ontheemden", "hersteloperatie"]),

    # =============================================
    # DOMAIN 6: LEEFOMGEVING & DUURZAAMHEID
    # =============================================
    ("leefomgeving", "Leefomgeving & Duurzaamheid", "Environment & Sustainability", None, []),

    # Subdomain: Afval & Circulair
    ("leefomgeving.afval", "Afval & Circulaire Economie", "Waste & Circular Economy", "leefomgeving", []),
    ("leefomgeving.afval.inzameling", "Afvalinzameling & Containers", "Waste Collection", "leefomgeving.afval",
     ["afval", "inzameling", "minicontainers", "ondergrondse containers", "afvalstoffenverordening", "rolemmers", "huishoudelijk afval", "afvalverwerking", "afvalbeheer", "inzamelvoorziening", "aanbiedplaatsen", "verbranding"]),

    # Subdomain: Klimaat & Energie
    ("leefomgeving.klimaat", "Klimaat & Energie", "Climate & Energy", "leefomgeving", []),
    ("leefomgeving.klimaat.adaptatie", "Klimaatadaptatie & Verduurzaming", "Climate Adaptation", "leefomgeving.klimaat",
     ["klimaat", "duurzaam", "isolatie", "verduurzam", "energie", "windturbine", "klimaatadaptatie"]),

    # Subdomain: Natuur & Milieu
    ("leefomgeving.natuur", "Natuur & Milieu", "Nature & Environment", "leefomgeving", []),
    ("leefomgeving.natuur.groen", "Groen & Dierenwelzijn", "Green & Animal Welfare", "leefomgeving.natuur",
     ["groen", "dierenwelzijn", "honden", "dode dieren", "bomen", "speeltuinen"]),
    ("leefomgeving.natuur.bodem", "Bodem & Geluid", "Soil & Noise", "leefomgeving.natuur",
     ["milieu", "pfas", "bodem", "geluid", "grondverzet"]),

    # =============================================
    # DOMAIN 7: WONEN & ERFGOED
    # =============================================
    ("wonen", "Wonen & Erfgoed", "Housing & Heritage", None, []),

    # Subdomain: Volkshuisvesting
    ("wonen.huisvesting", "Volkshuisvesting", "Housing", "wonen", []),
    ("wonen.huisvesting.toewijzing", "Woningtoewijzing & Huisvesting", "Housing Allocation", "wonen.huisvesting",
     ["huisvesting", "woning", "kamerverhuur", "woningsplitsing", "starterslening", "woonwagen", "urgenties", "doorstroom", "huisvestingsverordening"]),

    # Subdomain: Erfgoed & Begraafplaatsen
    ("wonen.erfgoed", "Erfgoed & Cultuurhistorie", "Heritage & Cultural History", "wonen", []),
    ("wonen.erfgoed.monumenten", "Monumenten & Stadsgezichten", "Monuments & Townscapes", "wonen.erfgoed",
     ["erfgoed", "monument", "stadsgezicht", "cultureel erfgoed", "kerkenvisie", "archeologie", "erfgoedbeleid"]),
    ("wonen.erfgoed.begraafplaatsen", "Begraafplaatsen & Uitvaart", "Cemeteries & Burial", "wonen.erfgoed",
     ["begraafplaats", "lijkbezorging", "begraving", "crematie"]),

    # =============================================
    # DOMAIN 8: ONDERWIJS & CULTUUR
    # =============================================
    ("onderwijs_cultuur", "Onderwijs, Cultuur & Sport", "Education, Culture & Sports", None, []),

    # Subdomain: Onderwijs
    ("onderwijs_cultuur.onderwijs", "Onderwijs & Leerplicht", "Education", "onderwijs_cultuur", []),
    ("onderwijs_cultuur.onderwijs.scholen", "Scholen & Voorzieningen", "Schools & Facilities", "onderwijs_cultuur.onderwijs",
     ["onderwijs", "leerplicht", "school", "gymnastiekruimte", "leerlingenvervoer", "schoolpleinen"]),

    # Subdomain: Cultuur & Sport
    ("onderwijs_cultuur.vrije_tijd", "Cultuur, Sport & Recreatie", "Culture, Sports & Recreation", "onderwijs_cultuur", []),
    ("onderwijs_cultuur.vrije_tijd.cultuur", "Cultuur & Kunst", "Culture & Arts", "onderwijs_cultuur.vrije_tijd",
     ["cultuur", "kunst", "amateurkunst", "jongerencultuur", "pakor", "erfgoedinitiatieven"]),
    ("onderwijs_cultuur.vrije_tijd.sport", "Sport & Speeltuinen", "Sports & Playgrounds", "onderwijs_cultuur.vrije_tijd",
     ["sport", "sportstimulering", "speeltuinen", "buitensport", "sportevenementen"]),
]

# === INSERT TAXONOMY ===
subject_ids = {}
for code, name_nl, name_en, parent_code, _ in taxonomy:
    parent_id = subject_ids.get(parent_code)
    depth = code.count(".")  # 0=domain, 1=subdomain, 2=topic
    c.execute("INSERT INTO subjects (parent_id, code, name_nl, name_en, depth) VALUES (?,?,?,?,?)",
              (parent_id, code, name_nl, name_en, depth))
    subject_ids[code] = c.lastrowid

# === INSERT TAG MAPPINGS (only for depth=2 topics) ===
for code, _, _, _, patterns in taxonomy:
    if not patterns:
        continue
    sid = subject_ids[code]
    for pat in patterns:
        c.execute("INSERT OR IGNORE INTO tag_subject_map (tag_pattern, subject_id) VALUES (?,?)", (pat, sid))

print(f"Taxonomy: {len([t for t in taxonomy if t[3] is None])} domains, "
      f"{len([t for t in taxonomy if t[3] and t[3].count('.')==0])} subdomains, "
      f"{len([t for t in taxonomy if t[3] and t[3].count('.')==1])} topics")

# === CLASSIFY REGULATIONS ===
regs = conn.execute("SELECT id, category, title FROM regulations WHERE fetched=1").fetchall()
reg_count = 0
for reg_id, category, title in regs:
    assigned = set()
    title_lower = title.lower()

    # From tags
    tags = conn.execute("""
        SELECT t.name FROM tags t
        JOIN regulation_tags rt ON rt.tag_id = t.id
        WHERE rt.regulation_id = ?
    """, (reg_id,)).fetchall()

    for (tag_name,) in tags:
        tag_lower = tag_name.lower()
        matches = conn.execute("""
            SELECT subject_id FROM tag_subject_map
            WHERE ? LIKE '%' || tag_pattern || '%' OR tag_pattern LIKE '%' || ? || '%'
        """, (tag_lower, tag_lower)).fetchall()
        for (sid,) in matches:
            assigned.add(sid)

    # Also try title-based matching against tag patterns
    all_patterns = conn.execute("SELECT tag_pattern, subject_id FROM tag_subject_map").fetchall()
    for pat, sid in all_patterns:
        if pat.lower() in title_lower:
            assigned.add(sid)

    # Propagate up: topic -> subdomain -> domain
    full_assigned = set()
    for sid in assigned:
        full_assigned.add(sid)
        # Get parent chain
        current = sid
        for _ in range(3):
            parent = conn.execute("SELECT parent_id FROM subjects WHERE id=?", (current,)).fetchone()
            if parent and parent[0]:
                full_assigned.add(parent[0])
                current = parent[0]
            else:
                break

    for sid in full_assigned:
        c.execute("INSERT OR IGNORE INTO regulation_subjects (regulation_id, subject_id) VALUES (?,?)", (reg_id, sid))

    if full_assigned:
        reg_count += 1

print(f"Regulations classified: {reg_count}/475")

# === CLASSIFY ARTICLES ===
articles = conn.execute("""
    SELECT a.id, a.article_title, a.body, a.regulation_id
    FROM articles a
""").fetchall()

art_count = 0
all_patterns = conn.execute("SELECT tag_pattern, subject_id FROM tag_subject_map").fetchall()

for art_id, art_title, body, reg_id in articles:
    assigned = set()
    searchable = ((art_title or "") + " " + (body or "")[:500]).lower()

    for pat, sid in all_patterns:
        if pat.lower() in searchable:
            assigned.add(sid)

    # Propagate up
    full_assigned = set()
    for sid in assigned:
        full_assigned.add(sid)
        current = sid
        for _ in range(3):
            parent = conn.execute("SELECT parent_id FROM subjects WHERE id=?", (current,)).fetchone()
            if parent and parent[0]:
                full_assigned.add(parent[0])
                current = parent[0]
            else:
                break

    for sid in full_assigned:
        c.execute("INSERT OR IGNORE INTO article_subjects (article_id, subject_id) VALUES (?,?)", (art_id, sid))

    if full_assigned:
        art_count += 1

print(f"Articles classified: {art_count}/{len(articles)}")

conn.commit()

# === REPORT ===
print("\n=== THREE-TIER TAXONOMY ===\n")
domains = conn.execute("SELECT id, code, name_nl FROM subjects WHERE depth=0 ORDER BY id").fetchall()
for did, dcode, dname in domains:
    dreg = conn.execute("SELECT COUNT(DISTINCT regulation_id) FROM regulation_subjects WHERE subject_id=?", (did,)).fetchone()[0]
    dart = conn.execute("SELECT COUNT(DISTINCT article_id) FROM article_subjects WHERE subject_id=?", (did,)).fetchone()[0]
    print(f"{dname} ({dreg} regs, {dart} articles)")

    subdomains = conn.execute("SELECT id, code, name_nl FROM subjects WHERE parent_id=? ORDER BY id", (did,)).fetchall()
    for sdid, sdcode, sdname in subdomains:
        sdreg = conn.execute("SELECT COUNT(DISTINCT regulation_id) FROM regulation_subjects WHERE subject_id=?", (sdid,)).fetchone()[0]
        sdart = conn.execute("SELECT COUNT(DISTINCT article_id) FROM article_subjects WHERE subject_id=?", (sdid,)).fetchone()[0]
        if sdreg > 0 or sdart > 0:
            print(f"  {sdname} ({sdreg} regs, {sdart} arts)")

            topics = conn.execute("SELECT id, code, name_nl FROM subjects WHERE parent_id=? ORDER BY id", (sdid,)).fetchall()
            for tid, tcode, tname in topics:
                treg = conn.execute("SELECT COUNT(DISTINCT regulation_id) FROM regulation_subjects WHERE subject_id=?", (tid,)).fetchone()[0]
                tart = conn.execute("SELECT COUNT(DISTINCT article_id) FROM article_subjects WHERE subject_id=?", (tid,)).fetchone()[0]
                if treg > 0 or tart > 0:
                    print(f"    {tname}: {treg} regs, {tart} arts")
    print()

total_reg = conn.execute("SELECT COUNT(DISTINCT regulation_id) FROM regulation_subjects").fetchone()[0]
total_art = conn.execute("SELECT COUNT(DISTINCT article_id) FROM article_subjects").fetchone()[0]
print(f"Total: {total_reg}/475 regs classified, {total_art}/{len(articles)} articles classified")

conn.close()
