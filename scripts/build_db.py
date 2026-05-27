"""
Build SQLite database of Alkmaar local regulations.
Source: lokaleregelgeving.overheid.nl

Schema overview:
  regulations     – one row per regulation (metadata + raw text)
  sections        – hierarchical breakdown (hoofdstuk > afdeling > paragraaf)
  articles        – individual articles/artikelen, linked to regulation + optional section
  law_references  – cross-references to national laws or other local regulations
  regulations_fts – FTS5 index on regulations (title + full_text + summary)
  sections_fts    – FTS5 index on sections (title + body)
  articles_fts    – FTS5 index on articles (article_title + body)
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "alkmaar_laws.db")
BASE_URL = "https://lokaleregelgeving.overheid.nl"


def create_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    c = conn.cursor()

    # ── Drop old tables ──
    for t in [
        "regulations_fts", "articles_fts", "sections_fts",
        "regulation_tags", "tags",
        "articles", "sections", "law_references", "regulations",
    ]:
        c.execute(f"DROP TABLE IF EXISTS {t}")

    # Drop old triggers
    for tr in [
        "regulations_ai", "regulations_ad", "regulations_au",
        "sections_ai", "sections_ad", "sections_au",
        "articles_ai", "articles_ad", "articles_au",
    ]:
        c.execute(f"DROP TRIGGER IF EXISTS {tr}")

    # ── regulations: one row per regulation ──
    c.execute("""
        CREATE TABLE regulations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            cvdr_id         TEXT NOT NULL,
            version         INTEGER NOT NULL,
            title           TEXT NOT NULL,
            url             TEXT NOT NULL,

            -- structured metadata (agents fill these)
            doc_type        TEXT,       -- verordening, beleidsregel, aanwijzingsbesluit, nota, regeling, mandaatbesluit, subsidieregeling, besluit, overig
            authority       TEXT,       -- raad, college, burgemeester
            effective_from  TEXT,       -- ISO date: 2026-01-01
            effective_to    TEXT,       -- ISO date or NULL if still active
            adoption_date   TEXT,       -- ISO date
            legal_basis     TEXT,       -- free text: referenced laws/articles
            signatories     TEXT,       -- comma-separated names
            citeertitel     TEXT,       -- official citation title
            category        TEXT,       -- topic category

            -- content
            full_text       TEXT,       -- raw full text of the regulation
            summary         TEXT,       -- agent-generated plain-language summary
            fetched         INTEGER DEFAULT 0,

            UNIQUE(cvdr_id, version)
        )
    """)

    # ── sections: hierarchical breakdown of large documents ──
    # Represents: Hoofdstuk > Afdeling > Paragraaf (or free-form chapters in policy docs)
    # Short decisions don't need sections; large docs like APV get full trees.
    c.execute("""
        CREATE TABLE sections (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            regulation_id   INTEGER NOT NULL REFERENCES regulations(id) ON DELETE CASCADE,
            parent_id       INTEGER REFERENCES sections(id) ON DELETE CASCADE,
            section_type    TEXT NOT NULL,   -- hoofdstuk, afdeling, paragraaf, titel, bijlage
            number          TEXT,            -- e.g. "2", "3.1", "Titel 1"
            title           TEXT NOT NULL,   -- e.g. "Openbare orde en veiligheid"
            body            TEXT,            -- for policy docs: free-form text of this section
            sort_order      INTEGER,         -- ordering within parent
            depth           INTEGER DEFAULT 0  -- 0=top-level, 1=sub, 2=sub-sub
        )
    """)

    # ── articles: individual articles extracted from regulations ──
    c.execute("""
        CREATE TABLE articles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            regulation_id   INTEGER NOT NULL REFERENCES regulations(id) ON DELETE CASCADE,
            section_id      INTEGER REFERENCES sections(id) ON DELETE SET NULL,
            article_number  TEXT NOT NULL,   -- e.g. "1:1", "2:10", "3"
            article_title   TEXT,            -- e.g. "Begripsbepalingen"
            body            TEXT NOT NULL,   -- full article text
            sort_order      INTEGER,         -- for ordering within a regulation
            UNIQUE(regulation_id, article_number)
        )
    """)

    # ── tags: searchable keyword labels for regulations ──
    c.execute("""
        CREATE TABLE tags (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL UNIQUE  -- normalized lowercase: "horeca", "parkeren", "vergunning"
        )
    """)
    c.execute("""
        CREATE TABLE regulation_tags (
            regulation_id   INTEGER NOT NULL REFERENCES regulations(id) ON DELETE CASCADE,
            tag_id          INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (regulation_id, tag_id)
        )
    """)

    # ── law_references: cross-references to other laws ──
    c.execute("""
        CREATE TABLE law_references (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            regulation_id   INTEGER NOT NULL REFERENCES regulations(id) ON DELETE CASCADE,
            ref_type        TEXT NOT NULL,   -- national_law, local_regulation, eu_directive
            ref_name        TEXT NOT NULL,   -- e.g. "Gemeentewet", "Participatiewet", "CVDR429464"
            ref_detail      TEXT,            -- e.g. "artikel 147", "artikelen 8, 8b"
            direction       TEXT DEFAULT 'outgoing'  -- outgoing = this reg cites it; incoming = cited by
        )
    """)

    # ── FTS5: regulations ──
    c.execute("""
        CREATE VIRTUAL TABLE regulations_fts USING fts5(
            title, full_text, summary,
            content='regulations',
            content_rowid='id'
        )
    """)
    c.execute("""
        CREATE TRIGGER regulations_ai AFTER INSERT ON regulations BEGIN
            INSERT INTO regulations_fts(rowid, title, full_text, summary)
            VALUES (new.id, new.title, new.full_text, new.summary);
        END
    """)
    c.execute("""
        CREATE TRIGGER regulations_ad AFTER DELETE ON regulations BEGIN
            INSERT INTO regulations_fts(regulations_fts, rowid, title, full_text, summary)
            VALUES ('delete', old.id, old.title, old.full_text, old.summary);
        END
    """)
    c.execute("""
        CREATE TRIGGER regulations_au AFTER UPDATE ON regulations BEGIN
            INSERT INTO regulations_fts(regulations_fts, rowid, title, full_text, summary)
            VALUES ('delete', old.id, old.title, old.full_text, old.summary);
            INSERT INTO regulations_fts(rowid, title, full_text, summary)
            VALUES (new.id, new.title, new.full_text, new.summary);
        END
    """)

    # ── FTS5: sections ──
    c.execute("""
        CREATE VIRTUAL TABLE sections_fts USING fts5(
            title, body,
            content='sections',
            content_rowid='id'
        )
    """)
    c.execute("""
        CREATE TRIGGER sections_ai AFTER INSERT ON sections BEGIN
            INSERT INTO sections_fts(rowid, title, body)
            VALUES (new.id, new.title, new.body);
        END
    """)
    c.execute("""
        CREATE TRIGGER sections_ad AFTER DELETE ON sections BEGIN
            INSERT INTO sections_fts(sections_fts, rowid, title, body)
            VALUES ('delete', old.id, old.title, old.body);
        END
    """)
    c.execute("""
        CREATE TRIGGER sections_au AFTER UPDATE ON sections BEGIN
            INSERT INTO sections_fts(sections_fts, rowid, title, body)
            VALUES ('delete', old.id, old.title, old.body);
            INSERT INTO sections_fts(rowid, title, body)
            VALUES (new.id, new.title, new.body);
        END
    """)

    # ── FTS5: articles ──
    c.execute("""
        CREATE VIRTUAL TABLE articles_fts USING fts5(
            article_title, body,
            content='articles',
            content_rowid='id'
        )
    """)
    c.execute("""
        CREATE TRIGGER articles_ai AFTER INSERT ON articles BEGIN
            INSERT INTO articles_fts(rowid, article_title, body)
            VALUES (new.id, new.article_title, new.body);
        END
    """)
    c.execute("""
        CREATE TRIGGER articles_ad AFTER DELETE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, article_title, body)
            VALUES ('delete', old.id, old.article_title, old.body);
        END
    """)
    c.execute("""
        CREATE TRIGGER articles_au AFTER UPDATE ON articles BEGIN
            INSERT INTO articles_fts(articles_fts, rowid, article_title, body)
            VALUES ('delete', old.id, old.article_title, old.body);
            INSERT INTO articles_fts(rowid, article_title, body)
            VALUES (new.id, new.article_title, new.body);
        END
    """)

    # ── Indexes ──
    c.execute("CREATE INDEX idx_sections_reg ON sections(regulation_id)")
    c.execute("CREATE INDEX idx_sections_parent ON sections(parent_id)")
    c.execute("CREATE INDEX idx_articles_reg ON articles(regulation_id)")
    c.execute("CREATE INDEX idx_articles_sec ON articles(section_id)")
    c.execute("CREATE INDEX idx_lawrefs_reg ON law_references(regulation_id)")
    c.execute("CREATE INDEX idx_reg_doctype ON regulations(doc_type)")
    c.execute("CREATE INDEX idx_reg_category ON regulations(category)")
    c.execute("CREATE INDEX idx_reg_fetched ON regulations(fetched)")
    c.execute("CREATE INDEX idx_regtags_reg ON regulation_tags(regulation_id)")
    c.execute("CREATE INDEX idx_regtags_tag ON regulation_tags(tag_id)")

    conn.commit()
    return conn


def parse_cvdr_path(path):
    parts = path.strip("/").split("/")
    cvdr_id = parts[0]
    version = int(parts[1]) if len(parts) > 1 else 1
    return cvdr_id, version


def insert_regulations(conn):
    entries = [
        # === PAGE 1 (entries 1-200) ===
        ("Aangevuld bekostigingsbesluit Boekelermeer Zuid I", "/CVDR19478/1"),
        ("Gemeenschappelijke regeling Milieudienst regio Alkmaar (MRA)", "/CVDR20097/1"),
        ("Aangevuld bekostigingsbesluit Boekelermeer Zuid 2", "/CVDR19812/1"),
        ("Verordening cliëntenparticipatie beleid voor mensen met een beperking", "/CVDR19654/1"),
        ("Verkeersbesluit snelheidsbeperking bij gemeente in beheer zijnde wateren", "/CVDR141375/1"),
        ("Beleidsregel schenken zwakalcoholhoudende dranken buiten een inrichting", "/CVDR113117/1"),
        ("Uitvoeringsregeling gemeentelijke belastingen Alkmaar 2011", "/CVDR78435/1"),
        ("Beleidsregels ambtshalve vermindering gemeentelijke belastingen", "/CVDR202435/1"),
        ("Besluit maximum aantal en gebruik parkeervergunningen", "/CVDR234414/1"),
        ("Mandaat heffings- en inrichtingsbevoegdheden gemeentelijke belastingen", "/CVDR279359/1"),
        ("Bekostigingsbesluit Noordelijke ontsluiting Beverkoog", "/CVDR229374/2"),
        ("Privacyreglement BRP", "/CVDR297276/1"),
        ("Mandaatbesluit griffiepersoneel", "/CVDR324168/1"),
        ("Verordening tegenprestatie Alkmaar 2015", "/CVDR358615/1"),
        ("Besluit benoeming (buitengewoon) ambtenaren van de burgerlijke stand", "/CVDR360078/1"),
        ("Aanwijzingsbesluit voor ambtenaren, belast met het in ontvangst nemen van gevonden voorwerpen", "/CVDR360079/1"),
        ("Aan te wijzen instellingen op grond van artikel 2.40 Wet Basisregistratie Personen", "/CVDR360369/1"),
        ("Woonplaatsenbesluit gemeente Alkmaar 2015", "/CVDR374340/1"),
        ("Aanwijzen van het huis van de gemeente Alkmaar", "/CVDR374344/1"),
        ("Besluit tot vaststelling nieuwe wijk- en buurtindeling Alkmaar 2015", "/CVDR360368/1"),
        ("Aanwijziging huis der gemeente in eenmalige situaties voor huwelijk", "/CVDR367450/1"),
        ("Klachtenregeling", "/CVDR359896/1"),
        ("Regeling beheer en toezicht basisregistratie personen 2015", "/CVDR360077/1"),
        ("Verordening Basis registratie personen Alkmaar 2015", "/CVDR360134/1"),
        ("Brandbeveiligingsverordening 2015", "/CVDR374362/1"),
        ("Verordening werkgeverscommissie griffie Alkmaar 2015", "/CVDR333089/1"),
        ("Delegatiebesluit bevoegdheden van de gemeenteraad aan werkgeverscommissie", "/CVDR359063/1"),
        ("Verordening werkgeverscommissie griffie Alkmaar 2015", "/CVDR376153/1"),
        ("Reglement BRP Alkmaar 2015", "/CVDR376151/1"),
        ("Drank- en Horecaverordening", "/CVDR376149/1"),
        ("Verordening op de vertrouwenscommissie", "/CVDR358662/2"),
        ("Organisatieverordening van de griffie gemeente Alkmaar", "/CVDR369640/1"),
        ("Aanwijzingsbesluit artikel 3 van Archiefverordening 2015", "/CVDR372255/1"),
        ("Reglement BRP", "/CVDR376253/1"),
        ("Beheersverordening Alkmaar Noord", "/CVDR379098/1"),
        ("Verordening precariobelasting kabels en leidingen", "/CVDR381147/1"),
        ("Financieel besluit Jeugdhulp Alkmaar 2016", "/CVDR394144/1"),
        ("Beleidsregels Wet op de Lijkbezorging gemeente Alkmaar", "/CVDR395943/1"),
        ("Protocol actieve informatieplicht", "/CVDR396241/1"),
        ("Verordening overgangsrecht Subsidieregeling duurzame renovatie Huibert Pootlaan", "/CVDR396885/1"),
        ("Werkafspraken Bestuurlijke Kalender", "/CVDR407580/1"),
        ("Verordening dode gezelschapsdieren gemeente Alkmaar", "/CVDR407585/1"),
        ("Verordening gemeentelijke onderscheiding", "/CVDR410899/1"),
        ("Privacyregeling gegevensverwerking Jeugd Alkmaar", "/CVDR411302/1"),
        ("Beleidsregels mantelzorgcompliment gemeente Alkmaar", "/CVDR414819/1"),
        ("Aanwijzingsbesluit toezichthouders gemeente Alkmaar", "/CVDR418284/1"),
        ("Verordening naamgeving en nummering Gemeente Alkmaar (adressen)", "/CVDR419752/1"),
        ("Beleidsplan civieltechnische kunstwerken 2017-2026", "/CVDR420538/1"),
        ("Gebiedsaanwijzing Johanna Naberstraat inclusief Johan Cruijffcourt", "/CVDR420731/1"),
        ("Gebiedsaanwijzing Melis Stokelaan en omgeving", "/CVDR421303/1"),
        ("Gebiedsaanwijzing op grond van artikel 2.45 Algemene plaatselijke verordening", "/CVDR421329/1"),
        ("Beleidsregel inzake vissend overnachten aan het water", "/CVDR421518/1"),
        ("Handhavingsarrangement Overlast op openbaar water", "/CVDR421522/1"),
        ("Aanwijzingsbesluit toezichthouders Apv", "/CVDR421547/1"),
        ("Aanwijzingsbesluit toezichthouders Havenbeveiligingswet", "/CVDR421557/1"),
        ("Verordening op de kansspelen Alkmaar 2016", "/CVDR421897/1"),
        ("Verordening bezwaarschriften Alkmaar", "/CVDR423360/1"),
        ("Sponsorprotocol gemeente Alkmaar", "/CVDR424074/1"),
        ("Beleid inzameling huishoudelijke afvalstoffen nabij elk perceel", "/CVDR425908/1"),
        ("Beleid coffeeshops gemeente Alkmaar", "/CVDR428192/1"),
        ("Verordening ruimte- en inrichtingseisen peuterspeelzalen", "/CVDR102037/2"),
        ("Beleidsplan wegen 2017-2026", "/CVDR428551/1"),
        ("Beleidsplan Stedelijk water 2017-2026", "/CVDR428561/1"),
        ("Aanwijzingsbesluit overlast fiets/bromfiets station-noord", "/CVDR429603/1"),
        ("Aanwijzingsbesluit overlast fiets/bromfiets station-centrum", "/CVDR429617/1"),
        ("Verordening Wet inburgering", "/CVDR295160/2"),
        ("Beleidskader Peuteropvang Alkmaar vanaf 2016", "/CVDR425357/2"),
        ("Verordening werkzaamheden kabels en leidingen Alkmaar", "/CVDR429464/1"),
        ("Beleidsregel kamerverhuur en woningsplitsing", "/CVDR430752/1"),
        ("Verordening Inrichting Antidiscriminatievoorziening gemeente Alkmaar", "/CVDR433927/1"),
        ("Aanwijzingsbesluit Digitaal Opkopers Register", "/CVDR434258/1"),
        ("Klachtenregeling aanbestedingen gemeente Alkmaar 2017", "/CVDR437540/1"),
        ("Regeling PAKOR", "/CVDR438269/1"),
        ("Regeling Adviescommissie Cultuur", "/CVDR439177/1"),
        ("Beleidsregel bekostiging gymnastiekruimte voor onderwijs", "/CVDR439447/1"),
        ("Aanwijzingsbesluit toezichthouders gemeente Alkmaar", "/CVDR439588/1"),
        ("Uitwerking Hoofdstuk 3 APV Prostitutie Alkmaar 2016", "/CVDR441114/1"),
        ("Handhavingsarrangement prostitutie Alkmaar 2016", "/CVDR441134/1"),
        ("Aanwijzingsbesluit ondergrondse inzamelvoorzieningen Ravelijn, Rammekens, Absdale", "/CVDR441950/1"),
        ("Aanwijzingsbesluit toezichthouders Apv prostitutiebranche", "/CVDR443666/1"),
        ("Minimabeleid 2017-2021", "/CVDR443390/1"),
        ("Gebiedsaanwijzing Paardenmarkt en omgeving", "/CVDR446157/1"),
        ("Aanwijzingsbesluit verbods- en losloopgebieden voor honden", "/CVDR447012/1"),
        ("Uitvoeringsprogramma toezicht en handhaving omgevingsrecht 2017", "/CVDR452547/1"),
        ("Beleid hogere waarden Wet geluidhinder gemeente Alkmaar 2016", "/CVDR453955/1"),
        ("Regeling briefadres gemeente Alkmaar 2017", "/CVDR454383/1"),
        ("Beleidsregel verdeling schaarse vergunningen voor seksbedrijf", "/CVDR455950/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening Vroonermeer", "/CVDR460814/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening Alkmaar-Noord", "/CVDR463392/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening Kompasweg Alkmaar", "/CVDR463470/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR465836/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen Elgerweg en de Drogerij", "/CVDR469090/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening Alkmaar-Noord", "/CVDR470822/1"),
        ("Aanwijzingsbesluit parkeren grote voertuigen 2017", "/CVDR471450/1"),
        ("Aanwijzingsbesluit verbod op het te koop aanbieden van voertuigen 2017", "/CVDR471458/1"),
        ("Klachtenregeling Maatschappelijke ondersteuning, Jeugd en Onderwijs", "/CVDR471299/1"),
        ("Benoemingsbesluit leden klachtencommissie", "/CVDR471688/1"),
        ("Besluit vergoeding voorzitter en leden klachtencommissie", "/CVDR471695/1"),
        ("Aanwijzingsbesluit buitengewoon opsporingsambtenaar en toezichthouders", "/CVDR474524/1"),
        ("Aanwijsbesluit Parkeerfonds Overstad", "/CVDR474696/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen", "/CVDR474946/1"),
        ("Verordening baatbelasting Noordelijke ontsluiting Beverkoog", "/CVDR432125/2"),
        ("Beleidsregel bestuurlijke boete Wet BRP gemeente Alkmaar", "/CVDR481324/1"),
        ("Verordening parkeerbelastingen 2018", "/CVDR468912/1"),
        ("Aanwijzingsbesluit Parkeren 2018", "/CVDR475992/1"),
        ("Aanwijzingsbesluit ondergrondse inzamelvoorziening", "/CVDR482356/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR483878/1"),
        ("Aanwijzingsbesluit Verordening openbaar water", "/CVDR420721/2"),
        ("Reglement op het kaasdragersgilde", "/CVDR484478/1"),
        ("Aanwijzingsbesluit boswachter staatsbosbeheer", "/CVDR485888/1"),
        ("Verordening op de ambtelijke bijstand, financiele fractieondersteuning", "/CVDR486953/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen", "/CVDR487281/1"),
        ("Regeling klein grondverzet gemeente Alkmaar", "/CVDR488145/1"),
        ("Mandaatbesluit directeur Stadswerk", "/CVDR488682/1"),
        ("Reglement van orde van het college", "/CVDR611010/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen", "/CVDR611130/1"),
        ("Nota actieve informatieplicht en geheimhouding 2018", "/CVDR611737/1"),
        ("Uitvoeringsprogramma vergunningen, toezicht en handhaving omgevingsrecht 2018", "/CVDR612105/1"),
        ("Aanwijzingsbesluit ondergrondse inzamelvoorzieningen Oudorperpolder, Rekerbuurt", "/CVDR612277/1"),
        ("Aanwijzingsbesluit ondergrondse inzamelvoorziening Huiswaard", "/CVDR612278/1"),
        ("Aanwijzingsbesluit ondergrondse inzamelvoorziening aan de Frieseweg", "/CVDR612279/1"),
        ("Aanwijzingsbesluit ondergrondse inzamelvoorzieningen Oudorperpolder, Rekerbuurt", "/CVDR612280/1"),
        ("Aanwijzingsbesluit ondergrondse inzamelvoorziening Elzasstraat/Vogezenstraat", "/CVDR612596/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR612598/1"),
        ("Aanwijzingsbesluit ondergrondse inzamelvoorziening Absdale", "/CVDR614400/1"),
        ("Reglement van orde Rekenkamercommissie Alkmaar", "/CVDR618188/1"),
        ("Beleidsregels verkeersontheffingen gemeente Alkmaar", "/CVDR613799/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR620854/1"),
        ("Aanwijzing gebieden bedelverbod Alkmaar", "/CVDR621089/1"),
        ("Verordening gedragscode bestuurlijke integriteit Alkmaar 2018", "/CVDR621895/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen", "/CVDR622102/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen", "/CVDR622103/1"),
        ("Verordening winkeltijden Alkmaar 2019", "/CVDR622653/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR623204/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR623206/1"),
        ("Nadere regels Subsidie Sportevenementen", "/CVDR624052/1"),
        ("Nadere regels Subsidie Erfgoedinitiatieven Alkmaar", "/CVDR624053/1"),
        ("Archiefverordening Alkmaar 2019", "/CVDR624275/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR624528/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen", "/CVDR624969/1"),
        ("Beleidsregels urgenties Alkmaar 2019", "/CVDR625615/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR627120/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen", "/CVDR627173/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR627708/1"),
        ("Aanwijzingsbesluit cameratoezicht centrum Alkmaar", "/CVDR627717/1"),
        ("Aanwijzingsbesluit cameratoezicht stationsgebied Alkmaar", "/CVDR627718/1"),
        ("Verantwoordings- en accountantsprotocol subsidies gemeente Alkmaar 2020", "/CVDR628107/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR628117/1"),
        ("Regeling rechtspositie burgemeester en wethouders 2019", "/CVDR628472/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR628742/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR629825/1"),
        ("Aanwijzingsbesluit ondergrondse inzamelvoorzieningen", "/CVDR629806/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen", "/CVDR630267/1"),
        ("Aanwijzingsbesluiten nieuwe aanbiedplaatsen voor rolemmers", "/CVDR631852/1"),
        ("Beleidsregel PFAS", "/CVDR634525/1"),
        ("Besluit vervanging archiefbescheiden gemeente Alkmaar 2020", "/CVDR634927/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR636145/1"),
        ("Aanwijzingsbesluit ambtenaren en buitengewoon ambtenaren burgerlijke stand", "/CVDR636108/1"),
        ("Beleidsregel gemeente Alkmaar vastgoedtransacties Wet Bibob", "/CVDR636799/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR637129/1"),
        ("Aanwijzingsbesluit toezichthouder gemeente Alkmaar", "/CVDR637218/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen", "/CVDR637394/1"),
        ("Besluit van de burgemeester raadsgriffier", "/CVDR637424/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR637614/1"),
        ("Beleidsregel verdeling schaarse vergunningen voor seksbedrijf", "/CVDR637623/1"),
        ("Prostitutiebeleid Gemeente Alkmaar", "/CVDR637627/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen", "/CVDR638034/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR638833/1"),
        ("Gebiedsaanwijzing overlast van fiets of bromfiets", "/CVDR640481/1"),
        ("Nadere regels maatschappelijke ondersteuning Alkmaar 2020", "/CVDR640510/1"),
        ("Beleidsplan Openbare Verlichting 2020-2029", "/CVDR640546/1"),
        ("Uitvoeringsregels horecabeleid", "/CVDR640729/1"),
        ("Subsidieregeling Cultuur Alkmaar", "/CVDR640585/1"),
        ("Nadere regels subsidie Sportstimulering", "/CVDR640593/1"),
        ("Subsidieregeling Alkmaar Maakt Het!", "/CVDR640594/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen", "/CVDR640851/1"),
        ("Handhavingsarrangement Clarissenbolwerk", "/CVDR643149/1"),
        ("Aanwijzingsbesluit Parkeerfonds Alkmaar 2020", "/CVDR643223/1"),
        ("Aanwijzingsbesluit verlenging cameratoezicht Zomerkermis evenemententerrein", "/CVDR643675/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening", "/CVDR643523/1"),
        ("Aanwijzingsbesluit locatie ondergrondse inzamelvoorziening Noorderkade/Kwakelkade", "/CVDR643911/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening Vroonermeer Noord", "/CVDR644599/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening Frederik Hendriklaan Trefpuntkerk", "/CVDR644601/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening Jan Steenstraat", "/CVDR644602/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening Huiswaarderplein", "/CVDR644603/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening Frederik Hendriklaan Ons Park", "/CVDR644604/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorziening Truus Wijsmuller-Meijerstraat", "/CVDR644606/1"),
        ("Subsidieregeling ESF-projecten Arbeidsmarktregio Noord-Holland Noord", "/CVDR406853/2"),
        ("Mandaatbesluit HALte werk", "/CVDR645171/1"),
        ("Verordening op de vertrouwenscommissie burgemeestersvacature Alkmaar 2020", "/CVDR645890/1"),
        ("Aanwijzingsbesluit cameratoezicht Melis Stokelaan/Percivalstraat", "/CVDR646047/1"),
        ("Subsidieplafonds 2021 van de gemeente Alkmaar", "/CVDR646447/1"),
        ("Aanwijzingsbesluiten ondergrondse inzamelvoorzieningen Vroonermeer Noord", "/CVDR648248/1"),
        ("Aanwijzingsbesluit extra cameratoezicht Beneluxplein", "/CVDR651951/1"),
        ("Aanwijzingsbesluit extra cameratoezicht Station Noord", "/CVDR651952/1"),
        ("Nadere regels Subsidie Groen en Dierenwelzijn", "/CVDR640587/1"),
        ("Aanwijzingsbesluiten aanbiedplaatsen Markenbinnen", "/CVDR653260/1"),
        ("Aanwijzingsbesluit verlenging permanent Cameratoezicht winkelcentrum De Mare", "/CVDR653664/1"),
        ("Verordening Startersleningen Gemeente Alkmaar 2015", "/CVDR367399/4"),
        ("Gemeenschappelijke Regeling Gemeentelijke Gezondheidsdienst Hollands Noorden", "/CVDR654871/1"),
        # === PAGE 2 (entries 201-400) ===
        ("Protocol camerabeveiliging Stadhuis en Stadskantoor Alkmaar", "/CVDR655963/1"),
        ("DAEB Stichting Hart van Noord-Holland", "/CVDR656231/1"),
        ("Aanwijzingsbesluit cameratoezicht Kennemersingel", "/CVDR656726/1"),
        ("Aanwijzingsbesluit toezichthouder rechtmatigheid Wmo en Jeugd, gemeente Alkmaar", "/CVDR657136/1"),
        ("Treasurystatuut 2021", "/CVDR657444/1"),
        ("Nota investeren en afschrijven 2021", "/CVDR657455/1"),
        ("Nota onderhoud kapitaalgoederen 2021", "/CVDR657457/1"),
        ("Nota reserves en voorzieningen 2021", "/CVDR657458/1"),
        ("Nota weerstandsvermogen en risicos 2021", "/CVDR657463/1"),
        ("Verlengingsbesluit cameratoezicht Melis Stokelaan/Percivalstraat", "/CVDR658008/1"),
        ("Gebiedsaanwijzing op grond van artikel 2.45 van de Apv Alkmaar", "/CVDR658430/1"),
        ("Aanwijzingsbesluit cameratoezicht Spilstraat", "/CVDR659300/1"),
        ("Gebiedsaanwijzing alcoholverbod Clarissenbolwerk", "/CVDR659389/1"),
        ("Aanwijzingsbesluit uitgiftepunt Bekendmakingswet", "/CVDR659800/1"),
        ("Aanwijzingsbesluit verbod gebruik lachgas op openbare plaatsen", "/CVDR661143/1"),
        ("Aanwijzingsbesluit Schepenakker_001_ZL", "/CVDR661371/1"),
        ("Aanwijzingsbesluit OC202125-HW021R", "/CVDR661375/1"),
        ("Intrekkingsbesluit gedeeltelijk intrekken aanwijzingsbesluit OC202018-HW022R", "/CVDR661376/1"),
        ("Aanwijzingsbesluit OC202127-OV057R", "/CVDR661377/1"),
        ("Aanwijzingsbesluit MC2021-09-VN06", "/CVDR661378/1"),
        ("Aanwijzingsbesluit MC2021-09-VN05", "/CVDR661379/1"),
        ("Aanwijzingsbesluit MC2021-09-VN07", "/CVDR661380/1"),
        ("Aanwijzingsbesluit cameratoezicht Zomerkermis Noorderstraat Alkmaar", "/CVDR661505/1"),
        ("Beleidsregels Bijstandsverlening zelfstandigen (Bbz2004) gemeente Alkmaar", "/CVDR661691/1"),
        ("Taak Kabels en Leidingen", "/CVDR662189/1"),
        ("Besluit tot het instellen van flexibel cameratoezicht middels bodycams", "/CVDR663077/1"),
        ("Aanwijzingsbesluit OC202134-HW004R", "/CVDR663646/1"),
        ("Verordening reclamebelasting 2021", "/CVDR650396/2"),
        ("Aanwijzingsbesluit cameratoezicht Thomas a Kempislaan", "/CVDR665210/1"),
        ("Nota gebiedsgericht samenwerken Samen maken we Alkmaar", "/CVDR666232/1"),
        ("Aanwijzingsbesluit MC2021-11-SP01", "/CVDR666868/1"),
        ("Aanwijzingsbesluit OC202136-MA106R", "/CVDR666869/1"),
        ("Verordening voorzieningen huisvesting onderwijs gemeente Alkmaar 2020", "/CVDR666475/1"),
        ("Ontwerp-aanwijzingsbesluit MC2022-01-VN08", "/CVDR671765/1"),
        ("Ontwerp-aanwijzingsbesluit MC2022-01-VN09", "/CVDR671767/1"),
        ("Ontwerp-aanwijzingsbesluit OC202201-VR026R", "/CVDR671768/1"),
        ("Ontwerp-aanwijzingsbesluit OC202201-VR027R", "/CVDR671769/1"),
        ("Mandaatbesluit heffing en invordering parkeerbelastingen", "/CVDR671859/1"),
        ("Aanwijzingsbesluit buitengewoon opsporingsambtenaar en toezichthouder", "/CVDR672032/1"),
        ("Kermissen", "/CVDR672197/1"),
        ("Verordening beslistermijn schuldhulpverlening gemeente Alkmaar", "/CVDR672207/1"),
        ("Aanwijzingsbesluit OC202205-ZU119R", "/CVDR672886/1"),
        ("Beleidsregels handhaving Wet kinderopvang gemeente Alkmaar 2022", "/CVDR673441/1"),
        ("Verlengingsbesluit cameratoezicht Thomas a Kempislaan", "/CVDR673512/1"),
        ("Afwijkingenbeleid gemeente Alkmaar Februari 2022", "/CVDR674625/1"),
        ("Aanwijzingsbesluit OC202213-HW021R", "/CVDR674946/1"),
        ("Aanwijzingsbesluit OC202211-OU065R", "/CVDR674947/1"),
        ("Aanwijzingsbesluit MC2022-05-BL01", "/CVDR674948/1"),
        ("Aanwijzingsbesluit OC202212-WE142R", "/CVDR674949/1"),
        ("Aanwijzingsbesluit MC2022-04-VN08", "/CVDR674980/1"),
        ("Aanwijzingsbesluit MC2022-04-VN09", "/CVDR674990/1"),
        ("Aanwijzingsbesluit OC202210-VR026R", "/CVDR674994/1"),
        ("Aanwijzingsbesluit OC202210-VR027R", "/CVDR674996/1"),
        ("Aanwijzingsbesluit OC202214-CT045R", "/CVDR675617/1"),
        ("Aanwijzingsbesluit OC202215-CT046R", "/CVDR675618/1"),
        ("Verordening op de ambtelijke bijstand gemeente Alkmaar 2020", "/CVDR645892/2"),
        ("Aanwijzingsbesluit OC202216-WE110R", "/CVDR676552/1"),
        ("Aanwijzingsbesluit OC202217-WE111R", "/CVDR676553/1"),
        ("Welstandsnota Alkmaar 2016", "/CVDR676545/2"),
        ("Aanwijzingsbesluit toezichthouder rechtmatigheid Wmo en Jeugd gemeente Alkmaar", "/CVDR676847/1"),
        ("Afvalstoffenverordening gemeente Alkmaar 2016", "/CVDR424430/2"),
        ("Uitvoeringsbesluit 2016 Afvalstoffenverordening gemeente Alkmaar 2016", "/CVDR425727/3"),
        ("Aanwijzingsbesluit MC2022-06-DR01", "/CVDR677315/1"),
        ("Aanwijzingsbesluit MC2022-06-DR02", "/CVDR677316/1"),
        ("Aanwijzingsbesluit MC2022-06-GS01", "/CVDR677317/1"),
        ("Aanwijzingsbesluit MC2022-06-GS02", "/CVDR677319/1"),
        ("Aanwijzingsbesluit MC2022-06-GS03", "/CVDR677320/1"),
        ("Aanwijzingsbesluit MC2022-06-GS04", "/CVDR677321/1"),
        ("Aanwijzingsbesluit MC2022-06-OT01", "/CVDR677322/1"),
        ("Aanwijzingsbesluit MC2022-06-OT02", "/CVDR677324/1"),
        ("Aanwijzingsbesluit MC2022-06-OT03", "/CVDR677326/1"),
        ("Aanwijzingsbesluit MC2022-06-ST01", "/CVDR677327/1"),
        ("Aanwijzingsbesluit MC2022-06-ST02", "/CVDR677329/1"),
        ("Aanwijzingsbesluit MC2022-06-ST03", "/CVDR677332/1"),
        ("Aanwijzingsbesluit MC2022-06-ST04", "/CVDR677336/1"),
        ("Aanwijzingsbesluit MC2022-06-ST05", "/CVDR677339/1"),
        ("Aanwijzingsbesluit MC2022-06-ST06", "/CVDR677343/1"),
        ("Aanwijzingsbesluit MC2022-06-ZS01", "/CVDR677345/1"),
        ("Aanwijzingsbesluit MC2022-06-ZS02", "/CVDR677347/1"),
        ("Aanwijzingsbesluit MC2022-06-ZS04", "/CVDR677349/1"),
        ("Aanwijzingsbesluit MC2022-06-ZS03", "/CVDR677525/1"),
        ("Beleidsregel aanwijzing tot BABS voor een dag in gemeente Alkmaar", "/CVDR677837/1"),
        ("Reglement burgerlijke stand 2022", "/CVDR677839/1"),
        ("Besluit ondermandaat/ondervolmacht/ondermachtiging", "/CVDR677889/1"),
        ("Reglement van orde van het college 2022", "/CVDR679768/1"),
        ("Aanwijzingsbesluit Cameratoezicht stationsgebied Alkmaar 2022-2027", "/CVDR681658/1"),
        ("Aanwijzingsbesluit Cameratoezicht centrum Alkmaar 2022-2027", "/CVDR681659/1"),
        ("Beleidsregel verblijfsontzegging Alkmaar", "/CVDR682006/1"),
        ("Gebiedsaanwijzing Johanna Naberstraat inclusief Johan Cruijffcourt en omgeving 2022", "/CVDR682010/1"),
        ("Gebiedsaanwijzing winkelcentrum De Mare en omgeving", "/CVDR682012/1"),
        ("Gebiedsaanwijzing Melis Stokelaan en omgeving 2022", "/CVDR682013/1"),
        ("Gebiedsaanwijzing Alkmaar binnenstad, Munnikenbolwerk en Clarissenbolwerk", "/CVDR682014/1"),
        ("Beleidsregels bekostiging leerlingenvervoer Alkmaar 2023", "/CVDR682557/1"),
        ("Kerkenvisie Alkmaar", "/CVDR683342/1"),
        ("Aanwijzingsbesluit Tijdelijke cameratoezicht Lekstraat", "/CVDR685163/1"),
        ("Aanwijzingsbesluit tijdelijke cameratoezicht Stalpaertstraat", "/CVDR685164/1"),
        ("Mandaatbesluit unit Veiligheid team Handhaving verblijfsontzegging Alkmaar", "/CVDR685610/1"),
        ("Mandaatbesluit politie voor verblijfsontzegging Alkmaar", "/CVDR685611/1"),
        ("Mandaatbesluit Ontwikkelfonds NHN", "/CVDR686307/1"),
        ("Vuurwerkvrijezone Binnenstad jaarwisseling 2022-2023", "/CVDR686734/1"),
        ("Uitvoeringsbesluit aanvullende bekostiging nieuwe groene schoolpleinen", "/CVDR687581/1"),
        ("Verordening bekostiging leerlingenvervoer Alkmaar 2023", "/CVDR685111/1"),
        ("Aanwijzingsbesluit tijdelijke cameratoezicht Ruusbroechof", "/CVDR690834/1"),
        ("Aanwijzingsbesluit toezichthouders Wet basisregistratie personen", "/CVDR691608/1"),
        ("Uitvoeringsregeling bouwgerelateerde leges", "/CVDR692210/1"),
        ("Aanwijzingsbesluit leerplichtambtenaren preventieve verzuim spreekuren", "/CVDR695861/1"),
        ("Aanwijzingsbesluit leerplichtambtenaren", "/CVDR696018/1"),
        ("Beleidsregels Doorstroomvoorrang 2023 Alkmaar", "/CVDR698152/1"),
        ("Beleidsregels urgenties Alkmaar 2023", "/CVDR698188/1"),
        ("Aanwijzing Oostwijk in Koedijk als gemeentelijk beschermd stadsgezicht", "/CVDR698345/1"),
        ("Verordening burgerinitiatief Alkmaar 2023", "/CVDR698979/1"),
        ("Instellingsbesluit markten gemeente Alkmaar 2023", "/CVDR700084/1"),
        ("Verordening rekenkamer Alkmaar", "/CVDR698983/1"),
        ("VTH-Beleidsnota 2023-2026", "/CVDR700929/1"),
        ("Aanwijzingsbesluit tijdelijke cameratoezicht Ruusbroechof 2023", "/CVDR701376/1"),
        ("Verordening op het onderzoeksrecht van de raad Alkmaar 2023", "/CVDR701690/1"),
        ("Wegsleepverordening Alkmaar", "/CVDR429427/2"),
        ("Alcoholverordening Alkmaar 2023-2026", "/CVDR702300/1"),
        ("Aanwijzingsbesluit locatie gemeentelijk stembureau (GSB)", "/CVDR703999/1"),
        ("Aanwijzingsbesluit stemlokalen Tweede Kamerverkiezing 22 november 2023", "/CVDR704029/1"),
        ("Woonwagen- en standplaatsenbeleid", "/CVDR711771/1"),
        ("Toewijzingsverordening woonwagenstandplaatsen", "/CVDR711787/1"),
        ("Subsidie Klimaatadaptieve maatregelen Alkmaar 2023", "/CVDR712390/1"),
        ("Beleidsregels gemeentelijk beschermd stadsgezicht Oostwijk", "/CVDR712689/1"),
        ("Beleid gemeentelijk beschermd stads- of dorpsgezicht", "/CVDR712691/1"),
        ("Nadere regels prostitutie", "/CVDR685296/2"),
        ("Verordening AlkmaarPas voor minima", "/CVDR702632/1"),
        ("Aanwijzingsbesluit toezichthouders Omgevingswet", "/CVDR703355/1"),
        ("Parkeerfondsverordening Alkmaar 2024", "/CVDR706066/1"),
        ("Voorbeschermingsregels hyperscale datacentra", "/CVDR708557/1"),
        ("Lijst van gevallen adviesrecht Omgevingswet gemeente Alkmaar", "/CVDR709025/1"),
        ("Afstemmingsverordening Participatiewet, IOAW en IOAZ gemeente Alkmaar", "/CVDR713534/1"),
        ("Re-integratieverordening Participatiewet gemeente Alkmaar", "/CVDR713535/1"),
        ("Nalevingsverordening gemeente Alkmaar", "/CVDR713538/1"),
        ("Verordening clientenparticipatie Participatiewet gemeente Alkmaar", "/CVDR713540/1"),
        ("Verordening clientenparticipatie Wsw gemeente Alkmaar", "/CVDR713541/1"),
        ("Nota Gebiedsoverstijgende Voorzieningen 2024", "/CVDR713860/1"),
        ("Aanwijzingsbesluit Tijdelijk cameratoezicht Olieslagerstraat Laan van Brussel", "/CVDR714263/1"),
        ("Vlagprotocol Gemeente Alkmaar", "/CVDR714565/1"),
        ("Reglement van orde commissie omgevingskwaliteit Alkmaar", "/CVDR715202/1"),
        ("Aanwijzingsbesluit Verlenging Permanent Cameratoezicht De Mare 2024-2027", "/CVDR715758/1"),
        ("Mandaatbesluit gemeente Alkmaar aan directeur OD NHN 2023", "/CVDR715899/1"),
        ("Criteria bij realisatie van nieuwe woningen gemeente Alkmaar 2024", "/CVDR715926/1"),
        ("Besluit ondermandaat/ondervolmacht/ondermachtiging 2024", "/CVDR718716/1"),
        ("Controleverordening Alkmaar 2023", "/CVDR718867/1"),
        ("Hoofdstuk 13 Herbruikbare statiegeldbekers bij evenementen", "/CVDR718974/1"),
        ("Algemene subsidieverordening Alkmaar 2019", "/CVDR623786/2"),
        ("Verordening maatschappelijke ondersteuning Alkmaar 2020", "/CVDR636733/2"),
        ("Subsidieregeling Amateurkunstbeoefening Alkmaar", "/CVDR640581/3"),
        ("Nadere regels subsidie bewonersondernemingen, wijk- en buurtcentra", "/CVDR640583/2"),
        ("Nadere regels subsidie Sociaal Domein Alkmaar", "/CVDR640588/2"),
        ("Nadere regels Sociaal Medische Indicatie Kinderopvang gemeente Alkmaar", "/CVDR673129/2"),
        ("Nadere regels Subsidie Peuteropvang en VVE gemeente Alkmaar vanaf 2024", "/CVDR701123/2"),
        ("Beleidsregel reserves en voorzieningen subsidies", "/CVDR719286/1"),
        ("Beleidsregel meerjarige subsidieverstrekking Alkmaar", "/CVDR719292/1"),
        ("Beleidskader kleine windturbines", "/CVDR720073/1"),
        ("Verordening Basisregistratie Personen (BRP) Alkmaar 2024", "/CVDR720711/1"),
        ("Gemeenschappelijke regeling Regionaal Historisch Centrum Alkmaar", "/CVDR723034/1"),
        ("Gemeenschappelijke regeling Zaffier", "/CVDR723045/1"),
        ("Gemeenschappelijke regeling vuilverbrandingsinstallatie Alkmaar en omstreken", "/CVDR723050/1"),
        ("Gemeenschappelijke regeling Veiligheidsregio Noord-Holland Noord 2024", "/CVDR723054/1"),
        ("Gemeenschappelijke Regeling GGD Hollands Noorden", "/CVDR723114/1"),
        ("Mandaat tot subsidieverlening Witgoedregeling en Isolatieregeling lage inkomens", "/CVDR723457/1"),
        ("Ondermandaat subsidieregelingen", "/CVDR723933/1"),
        ("Ondermandaat subsidieregelingen 2", "/CVDR723934/1"),
        ("Beleidsplan Klimaatadaptatie Alkmaar 2024-2028", "/CVDR724285/1"),
        ("Nadere regels subsidie Bewonersorganisatie", "/CVDR724466/1"),
        ("Nadere regels subsidie Bewonersinitiatieven", "/CVDR724467/1"),
        ("Beleidsregel Wet Bibob (vergunningen) gemeente Alkmaar", "/CVDR725020/1"),
        ("Handboek kabels en leidingen Alkmaar", "/CVDR725093/1"),
        ("Ondermandaat subsidieregelingen op het gebied van Duurzaamheid", "/CVDR725563/1"),
        ("Gemeentelijk beschermd stadsgezicht vier vierkanten", "/CVDR725869/1"),
        ("Beleidsregels urgenties gemeente Alkmaar 2024", "/CVDR726285/1"),
        ("Archeologische verwachtingskaart 2024", "/CVDR728150/1"),
        ("Verordening precariobelasting 2025", "/CVDR729757/1"),
        ("Bevoegdhedenregister Alkmaar", "/CVDR674639/8"),
        ("Verordening gemeentelijke ombudsman", "/CVDR721969/1"),
        ("Aanwijzingsbesluit veiligheidsrisicogebied omgeving AFAS stadion en centrum en station Alkmaar", "/CVDR734596/1"),
        ("Verlenging Cameratoezicht Robonbosweg 2025-2031", "/CVDR734664/1"),
        ("Dierenwelzijnsbeleid Gemeente Alkmaar 2025-2030", "/CVDR734958/1"),
        ("Referendumverordening Alkmaar 2025", "/CVDR734989/1"),
        ("Financiele verordening 212 Gemeente Alkmaar 2024", "/CVDR735403/1"),
        ("Nota kostprijsberekening en prijzen economische activiteiten 2024", "/CVDR735404/1"),
        ("Nota verbonden partijen 2024", "/CVDR735405/1"),
        ("Verordening participatie en uitdaagrecht Alkmaar 2025", "/CVDR734951/1"),
        ("Ondermandatering teamleider Verkeer en Vormgeving", "/CVDR736413/1"),
        ("Beheerregeling Informatiebeheer gemeente Alkmaar 2025", "/CVDR736568/1"),
        ("Verordening Nadeelcompensatie Alkmaar 2025", "/CVDR737358/1"),
        ("Verordening rechtspositie raads- en commissieleden gemeente Alkmaar 2025", "/CVDR738414/1"),
        ("Uitvoeringsprogramma VTH 2025", "/CVDR738541/1"),
        ("Parkeerverordening 2025", "/CVDR735217/1"),
        ("Nadere regels subsidie Diversiteit en Inclusie gemeente Alkmaar", "/CVDR738874/1"),
        ("Subsidieregeling Isolatie lage inkomens Alkmaar 2023", "/CVDR726880/2"),
        ("Nadere regels subsidie verenigingsaccommodaties buitensport", "/CVDR640591/4"),
        ("Instructie voor de griffier Alkmaar 2025", "/CVDR739524/1"),
        ("Verordening auditcommissie Alkmaar 2025", "/CVDR739527/1"),
        ("Parkeernormennota Alkmaar 2025-2027", "/CVDR739682/1"),
        ("Nadere regels subsidie Lokale Aanpak Isolatie Alkmaar", "/CVDR740642/1"),
        ("Reglement Basisregistratie Personen (BRP) 2025", "/CVDR740570/1"),
        ("Verordening vestigen alleenrecht uitvoering Regio Deal Noord-Holland Noord", "/CVDR740663/1"),
        # === PAGE 3 (entries 401-475) ===
        ("Agressieprotocol politieke ambtsdragers gemeente Alkmaar", "/CVDR740821/1"),
        ("Beleidsregels gebruikelijke hulp Wmo gemeente Alkmaar", "/CVDR658122/2"),
        ("Handreiking opstelpunten antenne-installaties", "/CVDR741895/1"),
        ("Verordening op de raadscommissies gemeente Alkmaar 2025", "/CVDR741887/1"),
        ("Notitie geheimhouding en beslotenheid voor de gemeenteraad gemeente Alkmaar", "/CVDR741986/1"),
        ("Verordening uitvoering en handhaving omgevingsrecht gemeente Alkmaar", "/CVDR743168/1"),
        ("Gebiedsaanwijzing Spoorbuurt en omgeving", "/CVDR743273/1"),
        ("Inkoop- en aanbestedingsbeleid gemeente Alkmaar 2025", "/CVDR743303/1"),
        ("Bekendmaking Rustweekenden 2026", "/CVDR743962/1"),
        ("Beleidsregel Damocles gemeente Alkmaar", "/CVDR745176/1"),
        ("Omgevingsplan gemeente Alkmaar", "/CVDR696288/3"),
        ("Besluit alleenrecht dienstverlening Regio Deal Noord Holland Noord", "/CVDR745568/1"),
        ("Mandaatbesluit Stichting Regio Deal Noord-Holland Noord", "/CVDR745569/1"),
        ("Subsidieregeling Regio Deal Noord Holland Noord", "/CVDR745570/1"),
        ("Regeling Deskundigencommissie Regio Deal Noord Holland Noord", "/CVDR745571/1"),
        ("Tijdelijk cameratoezicht Noorderkade", "/CVDR746228/1"),
        ("Tijdelijk cameratoezicht Helderseweg", "/CVDR746229/1"),
        ("Tijdelijk cameratoezicht Spoorstraat", "/CVDR746231/1"),
        ("Ontwikkelkader Nieuw Oudorp", "/CVDR746649/1"),
        ("Nota Gebiedsoverstijgende Voorzieningen 2025", "/CVDR746676/1"),
        ("Verordening onroerende-zaakbelastingen 2026", "/CVDR750117/1"),
        ("Verordening rioolheffing 2026", "/CVDR750118/1"),
        ("Verordening afvalstoffenheffing 2026", "/CVDR750122/1"),
        ("Legesverordening Alkmaar 2026", "/CVDR750123/1"),
        ("Verordening precariobelasting 2026", "/CVDR750125/1"),
        ("Verordening havengelden 2026", "/CVDR750126/1"),
        ("Verordening Toeristenbelasting 2026", "/CVDR750128/1"),
        ("Verordening forensenbelasting Alkmaar 2026", "/CVDR750131/1"),
        ("Besluit kwijtscheldingsregels 2026", "/CVDR750133/1"),
        ("Verordening Lijkbezorgingsrechten 2026", "/CVDR750135/1"),
        ("Beleidsregels Inning eigen bijdrage ontheemden Oekraine gemeente Alkmaar", "/CVDR750234/1"),
        ("Algemene plaatselijke verordening", "/CVDR659124/9"),
        ("Verordening fysieke leefomgeving", "/CVDR660526/7"),
        ("Nadere regels ligplaatsvergunning vaartuigen binnenstad Alkmaar", "/CVDR745620/1"),
        ("Nadere regels Subsidie Jongerencultuur Alkmaar 2026", "/CVDR747964/1"),
        ("Verordening Individuele inkomenstoeslag gemeente Alkmaar", "/CVDR752379/1"),
        ("Gebiedsaanwijzing alcoholverbod Noorderkade-Huiswaarderplein Alkmaar", "/CVDR754967/1"),
        ("Mandaatbesluit Ontwikkelfonds NHN 2025", "/CVDR754997/1"),
        ("Subsidieregeling Ontwikkelfonds NHN", "/CVDR754998/1"),
        ("Uitvoeringsnota-VTH 2023-2026", "/CVDR755354/1"),
        ("Ontwikkelkader Overdie", "/CVDR755557/1"),
        ("Nadere regels subsidie Speeltuinen", "/CVDR640589/2"),
        ("Mandaatbesluit uitvoering ondersteuning hersteloperatie kinderopvangtoeslag gemeente Alkmaar", "/CVDR755917/1"),
        ("Voorbereidingsbesluit omgevingsverordening NH2022 gemeente Alkmaar", "/CVDR705718/4"),
        ("Nadere regels subsidie monumenten Alkmaar", "/CVDR755999/1"),
        ("Aanwijzing collectieve festiviteiten 2026", "/CVDR756345/1"),
        ("Beheersverordening gemeentelijke begraafplaatsen Alkmaar", "/CVDR408728/2"),
        ("Omgevingsvisie gemeente Alkmaar", "/CVDR756394/1"),
        ("Gemeenschappelijke regeling GISD Regio Alkmaar", "/CVDR756495/1"),
        ("Actieprogramma Economie 2040 toekomst van de Alkmaarse economie", "/CVDR756894/1"),
        ("Participatieplan Omgevingsplan gemeente Alkmaar", "/CVDR757142/1"),
        ("Horecanota 2025-2035", "/CVDR757338/1"),
        ("Uitvoeringsregels gemeentelijke begraafplaatsen Alkmaar", "/CVDR409536/2"),
        ("Huisvestingsverordening Alkmaar 2024", "/CVDR713872/4"),
        ("Ontwikkelkader Viaanse Molen", "/CVDR758343/1"),
        ("Verordening Jeugdhulp Alkmaar 2026", "/CVDR758472/1"),
        ("Nadere regels Subsidie Verduurzamen", "/CVDR758662/1"),
        ("Uitvoeringbeleid Laadpalen ADA 2026-2030", "/CVDR758700/1"),
        ("Beleidsregels brede ondersteuning Wet hersteloperatie toeslagen gemeente Alkmaar", "/CVDR759230/1"),
        ("Aanwijzingsbesluit toezichthouder kwaliteit Wmo", "/CVDR759274/1"),
        ("Mandaatbesluit GISD Regio Alkmaar", "/CVDR759505/1"),
        ("Controleplan Toezicht en Handhaving Wmo 2015 en Jeugdwet", "/CVDR759546/1"),
        ("Nadere regels Jeugdhulp Alkmaar 2026", "/CVDR759759/1"),
        ("Budgethoudersregeling Alkmaar 2026", "/CVDR760659/1"),
        ("Erfgoedbeleid 2026-2036 gemeente Alkmaar", "/CVDR761028/1"),
        ("Uitwerkingsbesluit Parkeren 2026", "/CVDR757905/1"),
        ("Verordening parkeerbelastingen 2026", "/CVDR757906/1"),
        ("Aanwijzingsbesluit Parkeren 2026", "/CVDR757908/1"),
        ("Besluit Parkeergarages 2026", "/CVDR757909/1"),
        ("Aanwijzingsbesluit toezichthouder rechtmatigheid Wmo en Jeugd gemeente Alkmaar 2025a", "/CVDR761151/1"),
        ("Aanwijzingsbesluit toezichthouder rechtmatigheid Wmo en Jeugd gemeente Alkmaar 2025b", "/CVDR761152/1"),
        ("Subsidieregeling Regio Deal Noord Holland", "/CVDR761292/1"),
        ("Subsidieregeling Regio Deal Noord-Holland Noord Little Local", "/CVDR761294/1"),
        ("Verlenging tijdelijk cameratoezicht Spieghelplein", "/CVDR761472/2"),
        ("Tijdelijk cameratoezicht Bannewaard", "/CVDR761976/1"),
    ]

    c = conn.cursor()
    inserted = 0
    skipped = 0
    for title, path in entries:
        cvdr_id, version = parse_cvdr_path(path)
        url = f"{BASE_URL}{path}"
        try:
            c.execute(
                "INSERT INTO regulations (cvdr_id, version, title, url) VALUES (?, ?, ?, ?)",
                (cvdr_id, version, title, url),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    return inserted, skipped


if __name__ == "__main__":
    conn = create_db()
    inserted, skipped = insert_regulations(conn)
    total = conn.execute("SELECT COUNT(*) FROM regulations").fetchone()[0]
    conn.close()
    print(f"Database created at: {DB_PATH}")
    print(f"Inserted: {inserted} | Skipped (duplicates): {skipped} | Total: {total}")
