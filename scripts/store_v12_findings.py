"""
Store v12 initiatiefvoorstel findings into the database.
Adds columns: proposal_classification, proposal_action, proposal_reason
Updates all 475 regulations with their v12 classification and
stores specific action items + reasoning for herzien/intrekken items.
"""
import sqlite3

DB = "C:/Users/Bram Vink/alkmaar-laws/alkmaar_laws.db"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Add v12 columns if they don't exist
for col, typ in [("proposal_classification", "TEXT"), ("proposal_action", "TEXT"), ("proposal_reason", "TEXT")]:
    try:
        conn.execute(f"ALTER TABLE regulations ADD COLUMN {col} {typ}")
    except:
        pass  # column already exists

# --- ID sets and classification logic (same as generator) ---
REGISTERCORRECTIE_IDS = {
    "CVDR625615","CVDR627717","CVDR627718","CVDR643675","CVDR651951",
    "CVDR651952","CVDR653664","CVDR659300","CVDR659389","CVDR703999",
    "CVDR704029","CVDR640481","CVDR379098","CVDR474696",
}
INTREKKEN_IDS = {
    "CVDR714263","CVDR656726","CVDR646047","CVDR661505","CVDR701376","CVDR658008",
    "CVDR614400","CVDR612596","CVDR612278","CVDR612279","CVDR612277","CVDR612280",
    "CVDR19478","CVDR19812","CVDR229374","CVDR432125",
    "CVDR381147","CVDR376149","CVDR333089","CVDR455950","CVDR20097","CVDR279359",
    "CVDR295160","CVDR443390","CVDR646447","CVDR452547","CVDR612105","CVDR645890",
    "CVDR396885","CVDR102037","CVDR661376","CVDR686734","CVDR734596",
    "CVDR685163","CVDR665210","CVDR690834","CVDR685164","CVDR673512",
    "CVDR474524","CVDR691608","CVDR360078",
    "CVDR297276","CVDR374362","CVDR453955","CVDR634525","CVDR661143","CVDR433927",
    "CVDR425357","CVDR640729","CVDR471688","CVDR406853","CVDR19654","CVDR631852",
    "CVDR468912","CVDR475992",
}
HERZIEN_IDS = {
    "CVDR611737","CVDR411302","CVDR360077","CVDR430752","CVDR113117",
    "CVDR645171","CVDR78435","CVDR657444","CVDR359896",
    "CVDR636108","CVDR637218","CVDR485888","CVDR657136","CVDR418284",
    "CVDR420538","CVDR428551",
    "CVDR471695","CVDR394144",
    "CVDR488682","CVDR725563","CVDR424074",
}
CONSOLIDEREN_IDS = {"CVDR723933","CVDR723934","CVDR628472"}

def is_container(title):
    t = (title or "").lower()
    return any(k in t for k in [
        "aanwijzingsbesluit mc", "aanwijzingsbesluit oc",
        "aanwijzingsbesluit schepenakker", "minicontainer",
        "inzamelvoorziening", "aanbiedplaatsen", "ontwerp-aanwijzingsbesluit",
    ])

def classify(cvdr_id, title, verdict):
    if cvdr_id in REGISTERCORRECTIE_IDS: return "registercorrectie"
    if cvdr_id in INTREKKEN_IDS: return "intrekken"
    if cvdr_id in HERZIEN_IDS: return "herzien"
    if cvdr_id in CONSOLIDEREN_IDS: return "consolideren"
    if is_container(title): return "consolideren"
    if (verdict or "").lower() == "consolidate": return "consolideren"
    return "actueel"

# --- Specific actions and reasons for each item ---
ACTIONS = {
    # Registercorrecties
    "CVDR625615": ("Registercorrectie", "Artikel 6 bepaalt: 'Zij vervallen op 1 juli 2023.'"),
    "CVDR627717": ("Registercorrectie", "Aanwijzing voor drie jaar vanaf 28 september 2019, verstreken op 28 september 2022."),
    "CVDR627718": ("Registercorrectie", "Driejaarsperiode verstreken op 28 september 2022."),
    "CVDR643675": ("Registercorrectie", "Eenmalig evenementenbesluit Zomerkermis, geldig 31 augustus t/m 3 september 2020."),
    "CVDR651951": ("Registercorrectie", "Artikel 2: cameratoezicht tot 5 januari 2021."),
    "CVDR651952": ("Registercorrectie", "Artikel 2: cameratoezicht tot 5 januari 2021."),
    "CVDR653664": ("Registercorrectie", "Cameratoezicht van 1 februari 2021 tot 1 februari 2024."),
    "CVDR659300": ("Registercorrectie", "Cameratoezicht gedurende drie maanden vanaf 23 juni 2021."),
    "CVDR659389": ("Registercorrectie", "Alcoholverbod 27 juni 2021 t/m 19 september 2021."),
    "CVDR703999": ("Registercorrectie", "Eenmalig besluit voor de Tweede Kamerverkiezing van 22 november 2023."),
    "CVDR704029": ("Registercorrectie", "Aanwijzing 67 stemlokalen voor de verkiezing van 22 november 2023."),
    "CVDR640481": ("Registercorrectie", "Tijdelijke COVID-19 maatregel, enkel voor de duur van de maatregelen."),
    "CVDR379098": ("Registercorrectie", "Beheersverordeningen zijn per 1 januari 2024 van rechtswege opgegaan in het tijdelijke omgevingsplan (art. 4.6 lid 1 Invoeringswet Omgevingswet)."),
    "CVDR474696": ("Registercorrectie", "Reeds formeel ingetrokken door CVDR643223 (artikel 2 lid 2, augustus 2020), maar registerstatus niet bijgewerkt."),

    # Intrekken: original cameras
    "CVDR714263": ("Intrekken", "Driemaandsautorisatie vanaf januari 2024, verstreken circa april 2024."),
    "CVDR656726": ("Intrekken", "Autorisatie tot 30 september 2021."),
    "CVDR646047": ("Intrekken", "Zesmaandsautorisatie vanaf november 2020, verstreken circa mei 2021."),
    "CVDR661505": ("Intrekken", "Eenmalig evenement 20–29 augustus 2021."),
    "CVDR701376": ("Intrekken", "Driemaandsautorisatie vanaf oktober 2023, verstreken circa januari 2024."),
    "CVDR658008": ("Intrekken", "Driemaandsverlenging vanaf mei 2021, verstreken circa augustus 2021."),

    # Intrekken: original containers
    "CVDR614400": ("Intrekken", "Eenmalig plaatsingsbesluit afvalcontainer, locatie Absdale (2018)."),
    "CVDR612596": ("Intrekken", "Eenmalig plaatsingsbesluit afvalcontainer, locatie Elzasstraat/Vogezenstraat (2018)."),
    "CVDR612278": ("Intrekken", "Eenmalig plaatsingsbesluit afvalcontainer, locatie Huiswaard (2018)."),
    "CVDR612279": ("Intrekken", "Eenmalig plaatsingsbesluit afvalcontainer, locatie Frieseweg (2018)."),
    "CVDR612277": ("Intrekken", "Eenmalig plaatsingsbesluit afvalcontainer, locatie Oudorperpolder/Rekerbuurt (2018)."),
    "CVDR612280": ("Intrekken", "Eenmalig plaatsingsbesluit afvalcontainer, locatie Oudorperpolder/Rekerbuurt (2018). Tweede CVDR-entry met identieke titel."),

    # Intrekken: original projects
    "CVDR19478": ("Intrekken", "Bekostigingsbesluit Boekelermeer-Zuid I (2000). Wettelijke termijn baatbelasting ruim verstreken."),
    "CVDR19812": ("Intrekken", "Bekostigingsbesluit Boekelermeer-Zuid 2 (2004). Idem."),
    "CVDR229374": ("Intrekken", "Bekostigingsbesluit Noordelijke ontsluiting Beverkoog (2013). Baatbelastingverordening vastgesteld en uitgevoerd."),
    "CVDR432125": ("Intrekken (onder voorbehoud)", "Baatbelastingverordening Beverkoog met 20-jarig aanslagtijdvak. Aanslagtijdvak verstreken of nadert einde; verordening praktisch uitgewerkt. Voorbehoud: verifiëren of geen lopende aanslagen bestaan."),

    # Intrekken: original substantive
    "CVDR381147": ("Intrekken", "Wet afschaffing precariobelasting leidingen verbiedt sinds 1 juli 2022 nieuwe precariobelasting op nutsleidingen. Overgangsperiode (vijf jaar) verstreken."),
    "CVDR376149": ("Intrekken", "Verwijst naar Drank- en Horecawet (nu Alcoholwet) én gold uitsluitend voor Koningsdag 2015–2018."),
    "CVDR333089": ("Intrekken", "Bevestigd duplicaat van CVDR376153. Inhoudelijk identiek."),
    "CVDR455950": ("Intrekken", "Toewijzingsronde afgerond. Opvolger CVDR637623 (2020) regelt huidige verdeling."),
    "CVDR20097": ("Intrekken", "Taken MRA overgegaan naar Omgevingsdienst NHN. CVDR715899 regelt huidige mandaatrelatie. Dit mandaatbesluit uit 2001 heeft geen praktische werking meer."),
    "CVDR279359": ("Intrekken (onder voorbehoud)", "Mandaat belastingheffing aan unitmanagers. Voorbehoud: verifiëren of bevoegdhedenregister (CVDR674639) alle bevoegdheden dekt."),
    "CVDR295160": ("Intrekken", "Inburgeringsverordening voor trajecten vóór 2013. Wet inburgering 2021 (in werking per 1-1-2022) vervangt het stelsel geheel."),
    "CVDR443390": ("Intrekken", "Kaderstellend besluit beleidsperiode 2017–2021. Periode vijf jaar verstreken."),
    "CVDR646447": ("Intrekken", "Subsidieplafonds begrotingsjaar 2021. Jaarlijks instrument zonder doorlopende werking."),
    "CVDR452547": ("Intrekken", "Jaarprogramma vergunningverlening, toezicht en handhaving (VTH) 2017. Operationeel werkplan, 9 jaar oud."),
    "CVDR612105": ("Intrekken", "Jaarprogramma VTH 2018. Idem."),
    "CVDR645890": ("Intrekken", "Verordening vertrouwenscommissie burgemeestersvacature 2020. Vervalbepaling: vervalt bij aantreden nieuwe burgemeester. Burgemeester Schouten beëdigd op 23 juni 2021."),
    "CVDR396885": ("Intrekken (onder voorbehoud)", "Overgangsrecht subsidieleningen Huibert Pootlaan (2007). Na 19 jaar vrijwel zeker afgelost. Voorbehoud: verifiëren bij afdeling Financiën."),
    "CVDR102037": ("Intrekken", "Wet kinderopvang (gewijzigd bij Stb. 2017/252) heft peuterspeelzalen als juridische categorie op. Landelijke kwaliteitseisen dekken volledig."),
    "CVDR661376": ("Intrekken", "Transitie-artefact: gedeeltelijke intrekking ouder containerbesluit. Vervangende locatie vastgesteld."),
    "CVDR686734": ("Intrekken", "Vuurwerkvrijezone jaarwisseling 2022–2023. Eenmalig, 2,5 jaar uitgewerkt."),
    "CVDR734596": ("Intrekken", "Veiligheidsrisicogebied AZ–AS Roma 23 januari 2025. 16-uursvenster verstreken."),

    # Intrekken: new cameras (3.6)
    "CVDR685163": ("Intrekken", "Tijdelijke driemaandsautorisatie cameratoezicht Lekstraat vanaf 2 december 2022, materieel uitgewerkt sinds maart 2023."),
    "CVDR665210": ("Intrekken", "Driemaandsautorisatie cameratoezicht Thomas à Kempislaan vanaf 30 november 2021, uitgewerkt sinds februari 2022. Gezamenlijk intrekken met CVDR673512."),
    "CVDR690834": ("Intrekken", "Tijdelijke driemaandsautorisatie cameratoezicht Ruusbroechof vanaf 5 januari 2023, uitgewerkt sinds april 2023."),
    "CVDR685164": ("Intrekken", "Tijdelijke driemaandsautorisatie cameratoezicht Stalpaertstraat vanaf 2 december 2022, uitgewerkt sinds maart 2023."),
    "CVDR673512": ("Intrekken", "Driemaandsverlenging cameratoezicht Thomas à Kempislaan vanaf 1 maart 2022, uitgewerkt sinds juni 2022. Gezamenlijk intrekken met CVDR665210."),

    # Intrekken: new personnel (3.6)
    "CVDR474524": ("Intrekken", "Aanwijzing enkele onbezoldigde ambtenaar als BOA parkeerhandhaving (2017). Na 9 jaar feitelijk achterhaald."),
    "CVDR691608": ("Intrekken", "Aanwijzing 8 medewerkers Nationaal Coördinatiecentrum Ondermijning en Datafraude (NCOD) als BRP-toezichthouders. Per eigen bepaling verlopen op 31-12-2023."),
    "CVDR360078": ("Intrekken", "Benoeming ambtenaren burgerlijke stand 2015 (na herindeling). Buitengewone ambtenaren verlopen per 01-01-2016; CVDR636108 (2020) regelt dezelfde materie."),

    # Intrekken: new legal basis (3.6)
    "CVDR297276": ("Intrekken", "Privacyreglement BRP: verwijst naar Wet GBA (vervangen 2014) en Wbp (vervangen 2018). Beide grondslagen vervallen."),
    "CVDR374362": ("Intrekken", "Brandbeveiligingsverordening 2015: gebaseerd op bouwkwaliteitsbepalingen Woningwet/Bouwbesluit 2012, per 2024 overgeheveld naar Omgevingswet/Bbl. Geen zelfstandige rechtswerking meer."),
    "CVDR453955": ("Intrekken", "Beleid hogere waarden Wet geluidhinder: Wet geluidhinder per 2024 opgegaan in Omgevingswet. Procedure 'hogere waarden' bestaat niet meer."),
    "CVDR634525": ("Intrekken", "Beleidsregel PFAS: gebaseerd op Wet bodembescherming/Besluit bodemkwaliteit, per 2024 opgegaan in Omgevingswet. Art. 9 voorzag in evaluatie bij Omgevingswet; niet uitgevoerd."),
    "CVDR661143": ("Intrekken", "Lokaal lachgasverbod (2021, APV art. 2:51): lachgas sinds 1-1-2023 op Lijst II Opiumwet. Landelijke strafbaarstelling biedt sterkere handhaving. Regelgevingsoverlap opheffen."),
    "CVDR433927": ("Intrekken", "Verordening ADV: herhaalt grotendeels Wet gemeentelijke antidiscriminatievoorzieningen. Enige lokale bepaling (aanwijzing Art.1 Bureau NHN) kan via collegebesluit."),

    # Intrekken: new spent (3.6)
    "CVDR425357": ("Intrekken", "Beleidskader peuteropvang 2016: omvorming peuterspeelzaalwerk voltooid per 1-1-2018 (Wet kinderopvang, Stb. 2017/252). Beleidsdoel bereikt."),
    "CVDR640729": ("Intrekken", "Uitvoeringsregels horeca (Deel 3A: COVID-19 terrassen). Noodverordening vervallen; regeling heeft materieel geen werking meer."),
    "CVDR471688": ("Intrekken", "Benoemingsbesluit klachtencommissie: 4 personen bij naam uit 2017. Persoonsgebonden besluit van 9 jaar oud. Bij doorlopende behoefte actueel besluit vaststellen."),
    "CVDR406853": ("Intrekken", "Subsidieregeling ESF 2014–2020: EU-programmaperiode afgesloten, kostenperiode verstreken per 31-12-2023. Bewaarplicht tot 31-12-2027."),
    "CVDR19654": ("Intrekken", "Verordening cliëntenparticipatie Wmo 2008: grondslag (oorspronkelijke Wmo) per 2015 vervallen, vervangen door Wmo 2015. Over het hoofd gezien bij wettransitie."),
    "CVDR631852": ("Intrekken", "Eenmalig aanwijzingsbesluit aanbiedplaatsen rolemmers (2019). Na 6 jaar gevestigde praktijk; geen toegevoegde waarde meer."),

    # Herzien: law references (4.1)
    "CVDR611737": ("Herzien", "Nota informatieplicht en geheimhouding 2018: drie van vier grondslagen gewijzigd: Wob→Woo (2022), geheimhoudingsbepalingen (artt. 25/55/86 Gemeentewet) per april 2023 vervangen door nieuw regime, Wbp→AVG (2018). Gehele nota herschrijven."),
    "CVDR411302": ("Herzien", "Privacyregeling gegevensverwerking Jeugd: verwijst naar Wbp (nu AVG). Jeugdwet-grondslag geldig; Wbp-verwijzingen vervangen door AVG/UAVG."),
    "CVDR360077": ("Herzien", "Regeling beheer en toezicht BRP 2015: Wet BRP-grondslag geldig, privacy-verwijzingen naar Wbp actualiseren naar AVG."),
    "CVDR430752": ("Herzien", "Beleidsregel kamerverhuur: verwijst naar 'bestemmingsplan' (nu omgevingsplan per Omgevingswet 2024). Terminologie actualiseren."),
    "CVDR113117": ("Herzien", "Beleidsregel alcohol bij evenementen: verwijst naar Drank- en Horecawet (nu Alcoholwet per 2021). Wetsverwijzingen actualiseren."),
    "CVDR645171": ("Herzien", "Mandaatbesluit HALte werk: verwijst naar Wob (nu Woo per 2022). Wetsverwijzing actualiseren."),
    "CVDR78435": ("Herzien", "Uitvoeringsregeling belastingen 2011: bepalingen over hondenbelasting (art. 2) achterhaald — gemeente Alkmaar heft deze belasting niet meer. Geactualiseerde uitvoeringsregeling vaststellen."),
    "CVDR657444": ("Herzien", "Treasurystatuut 2021: verwijst naar financiële verordening vóór 2024. In lijn brengen met Financiële verordening 2024 (art. 212 Gemeentewet)."),
    "CVDR359896": ("Herzien", "Klachtenregeling 2015: geen verwijzing naar Awb hoofdstuk 9, dupliceert Awb-bepalingen. Herzie met grondslagverwijzing titel 9.1 Awb, schrap duplicaten."),

    # Herzien: personnel (4.2)
    "CVDR636108": ("Herzien", "Aanwijzingsbesluit ambtenaren burgerlijke stand (2020): 46 namen, 6+ jaar oud. Vervang door actueel aanwijzingsbesluit."),
    "CVDR637218": ("Herzien", "Aanwijzingsbesluit toezichthouders (2020): 5 namen voor APV/afval/horeca. 6+ jaar oud. Vervang door actuele aanwijzing."),
    "CVDR485888": ("Herzien", "Aanwijzingsbesluit boswachter Staatsbosbeheer: enkele boswachter, Schermereiland. Verifiëren of persoon nog in functie en overeenkomst actueel."),
    "CVDR657136": ("Herzien", "Aanwijzingsbesluit toezichthouders Wmo/Jeugd (2021): 3 namen. Na 5 jaar mogelijk verouderd. Verifiëren en actualiseren."),
    "CVDR418284": ("Herzien", "Aanwijzingsbesluit toezichthouders Halte Werk (2015/2016): Participatiewet/Ioaw/Ioaz. Na 10 jaar mogelijk niet meer in lijn met organisatie. Verifiëren en actualiseren."),

    # Herzien: plan periods (4.3)
    "CVDR420538": ("Herzien", "Beleidsplan civieltechnische kunstwerken 2017-2026: planperiode loopt eind 2026 af. Opvolgend plan 2027-2036 voorbereiden."),
    "CVDR428551": ("Herzien", "Beleidsplan wegen 2017-2026: planperiode verstrijkt 2026. Zonder opvolger ontbreekt per 2027 beleidsbasis wegenonderhoud. Met spoed opvolger voorbereiden."),

    # Herzien: tariffs (4.4)
    "CVDR471695": ("Herzien", "Vergoeding klachtencommissie (€200/€250, 2017): niet geïndexeerd. Verifiëren of bedragen nog in lijn met vergoedingenkader."),
    "CVDR394144": ("Herzien", "Financieel besluit Jeugdhulp 2016: tarieventabel uit beginjaren Jeugdwet. Verifiëren of actueler besluit bestaat, zo niet actualiseren."),
    "CVDR468912": ("Intrekken", "Verordening parkeerbelastingen 2018: achterhaald door opeenvolgende jaarlijkse tarievenverordeningen. CVDR757906 (Verordening parkeerbelastingen 2026) is de vigerende versie."),

    # Herzien: other (4.5)
    "CVDR488682": ("Herzien", "Mandaatbesluit Stadswerk 072 NV (2017): zeer smal mandaat (enkel Afvalstoffenverordening). Opnemen in bevoegdhedenregister, als zelfstandig besluit intrekken."),
    "CVDR725563": ("Herzien", "Ondermandaat Duurzaamheid (2024): drempel €40.000 vs €10.000 bij vergelijkbare ondermandaten. Mandaatketen verduidelijken en opnemen in bevoegdhedenregister."),
    "CVDR424074": ("Herzien", "Sponsorprotocol (2016): verwijst naar beleidskaders (Actieplan Economie, Citymarketingbeleid) die na twee coalitieperioden niet actueel zijn. Actualiseren."),
    "CVDR475992": ("Intrekken", "Aanwijzingsbesluit Parkeren 2018: achterhaald door opvolgend aanwijzingsbesluit (CVDR757908). Vigerende versie is 2025/2026."),

    # Consolideren: mandaat (5.2)
    "CVDR723933": ("Consolideren", "Ondermandaat subsidieregelingen unit Publieke Dienstverlening (2024). Opnemen in bevoegdhedenregister als onderdeel mandaatstructuur subsidieverlening."),
    "CVDR723934": ("Consolideren", "Ondermandaat subsidieregelingen unit Vitaliteit (2024). Samenvoegen met CVDR723933 in bevoegdhedenregister."),
    "CVDR628472": ("Consolideren", "Regeling rechtspositie B&W 2019: uitsluitend lokale uitvoeringsbepalingen bij landelijk Rechtspositiebesluit. Opnemen als bijlage bij integraal rechtspositiekader."),
}

# --- Update all 475 regulations ---
updated = 0
for reg in conn.execute("SELECT cvdr_id, title, audit_verdict FROM regulations WHERE fetched=1"):
    cvdr_id = reg["cvdr_id"]
    classification = classify(cvdr_id, reg["title"], reg["audit_verdict"])

    if cvdr_id in ACTIONS:
        action, reason = ACTIONS[cvdr_id]
    elif classification == "consolideren" and is_container(reg["title"]):
        action = "Consolideren"
        reason = "Individueel aanwijzingsbesluit afvalcontainer(s). Consolideren in enkel overzichtsbesluit (containerlocatieregister)."
    elif classification == "consolideren":
        action = "Consolideren"
        reason = "Consolidatiekandidaat op basis van individuele audit."
    else:
        action = ""
        reason = ""

    conn.execute("""
        UPDATE regulations SET
            proposal_classification = ?,
            proposal_action = ?,
            proposal_reason = ?
        WHERE cvdr_id = ?
    """, (classification, action, reason, cvdr_id))
    updated += 1

conn.commit()

# Print summary
print(f"Updated {updated} regulations")
for row in conn.execute("""
    SELECT proposal_classification, COUNT(*) as cnt
    FROM regulations WHERE fetched=1
    GROUP BY proposal_classification
    ORDER BY cnt DESC
"""):
    print(f"  {row['proposal_classification']}: {row['cnt']}")

# Count items with specific actions
with_action = conn.execute("SELECT COUNT(*) FROM regulations WHERE fetched=1 AND proposal_action != ''").fetchone()[0]
print(f"  Items with specific action: {with_action}")

conn.close()
