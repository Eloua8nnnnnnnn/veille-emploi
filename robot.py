"""Robot de veille emploi.

Récupère les offres sur les sites carrières, garde celles dont l'intitulé peut
correspondre, les fait juger par Claude selon le profil décrit dans CLAUDE.md,
puis enregistre le résultat dans docs/offres.json (lu par le tableau de bord).

Les offres VIE de Business France sont lues avec un navigateur automatisé (Playwright),
comme Business France l'a autorisé par e-mail (novembre 2026) : une seule exécution par jour,
une pause entre chaque page, et aucune donnée nominative enregistrée.

Lancement :  .venv/bin/python robot.py        (analyse au plus 60 nouvelles offres)
             .venv/bin/python robot.py 5      (analyse au plus 5 offres, pour tester)
"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import anthropic
import requests
from playwright.sync_api import sync_playwright
from pydantic import BaseModel

DOSSIER = Path(__file__).parent
FICHIER_OFFRES = DOSSIER / "docs" / "offres.json"
MODELE = "claude-haiku-5-5"  # modèle le moins cher ; "claude-opus-5-5" juge plus finement
MAX_ANALYSES = int(sys.argv[1]) if len(sys.argv) > 1 else 60  # plafond de dépenses par lancement
EN_TETES = {"User-Agent": "Mozilla/5.0 (compatible; veille-emploi-personnelle)"}

# Premier tri gratuit sur l'intitulé : il faut au moins un mot cible et aucun mot exclu.
MOTS_CIBLES = re.compile(
    r"\b(product|produkt|business analyst|business owner|analyst|digital|owner|strateg\w*"
    r"|transformation|innovation|e-?commerce|customer experience|ai|genai"
    r"|artificial intelligence|data)\b",
    re.I,
)
MOTS_EXCLUS = re.compile(
    r"\b(pilot|captain|first officer|cabin crew|flight attendant|werkstudent|working student"
    r"|head of|director|vice president|mechanic|technician|ausbildung|duales studium)\b",
    re.I,
)

# Pour les VIE (intitulés souvent en français), le tri est plus large : produit, projet, stratégie…
MOTS_CIBLES_VIE = re.compile(
    r"\b(product|produits?|business analyst|analyste|business owner|chef de projets?|project|projets?"
    r"|strat\w*|transformation|digital|digitale|numériques?|innovation|chief of staff|ceo office"
    r"|ia|ai|marketing|e-?commerce|customer|expérience client)\b",
    re.I,
)
MOTS_EXCLUS_VIE = re.compile(
    r"\b(ingénieur|ingenieur|engineer|engineering|développeur|developpeur|developer|technicien"
    r"|comptable|chantier|travaux|mécanique|électrique|qualité|quality|supply|achats?)\b",
    re.I,
)
# Volet 2 (startups) : postes de Chief of Staff, bras droit du CEO, projets stratégiques
MOTS_CIBLES_STARTUP = re.compile(
    r"\b(chief of staff|ceo office|office of the ceo|founder'?s? associate|founding associate|bras droit"
    r"|strateg\w*|bizops|business operations|strategy (?:&|and) operations|special projects"
    r"|transformation|project manager|chef de projets?|generalist|operations associate"
    r"|product owner|product manager|product analyst|associate product|apm)\b",
    re.I,
)
MOTS_EXCLUS_STARTUP = re.compile(
    r"\b(staff (?:product|engineer|software|data)\w*|executive assistant|office manager|deployment|customer success|engineer|engineering|developer|nurse|sales|account executive"
    r"|head of|director|vp|vice president|senior|sr\.?|lead|principal)\b",
    re.I,
)
LIENS_CONNUS = set()  # rempli par main() : évite de rouvrir chaque jour les annonces déjà analysées


# ---------- Récupération des offres, une fonction par compagnie ----------

def lire(url, **options):
    reponse = requests.get(url, headers=EN_TETES, timeout=30, **options)
    reponse.raise_for_status()
    return reponse


def etihad():
    """Interface officielle SmartRecruiters."""
    adresse = "https://api.smartrecruiters.com/v1/companies/EtihadAirways5/postings"
    offres, debut = [], 0
    while True:
        page = lire(adresse, params={"limit": 100, "offset": debut}).json()
        for p in page["content"]:
            offres.append({
                "entreprise": "Etihad Airways",
                "titre": p["name"],
                "lieu": p["location"].get("fullLocation", "").replace(", ,", ","),
                "date_publication": p["releasedDate"][:10],
                "lien": f"https://jobs.smartrecruiters.com/EtihadAirways5/{p['id']}",
                "detail": f"{adresse}/{p['id']}",
            })
        debut += 100
        if debut >= page["totalFound"]:
            return offres


def lufthansa():
    """Interface publique utilisée par lufthansagroup.careers."""
    champs = ["ID", "PositionTitle", "PositionURI", "PositionLocation.CountryName",
              "PositionLocation.CityName", "PublicationStartDate", "ParentOrganizationName"]
    offres, debut = [], 1
    while True:
        recherche = {"SearchParameters": {"FirstItem": debut, "CountItem": 100, "Sort": [],
                                          "MatchedObjectDescriptor": champs},
                     "SearchCriteria": [], "LanguageCode": "EN"}
        resultat = lire("https://api-apply.lufthansagroup.careers/search/",
                        params={"data": json.dumps(recherche)}).json()["SearchResult"]
        for element in resultat["SearchResultItems"]:
            o = element["MatchedObjectDescriptor"]
            lieu = (o.get("PositionLocation") or [{}])[0]
            offres.append({
                "entreprise": f"Lufthansa Group ({o.get('ParentOrganizationName', '')})",
                "titre": o["PositionTitle"],
                "lieu": f"{lieu.get('CityName', '')}, {lieu.get('CountryName', '')}",
                "date_publication": o.get("PublicationStartDate", ""),
                "lien": o["PositionURI"],
            })
        debut += 100
        if debut > resultat["SearchResultCountAll"]:
            return offres


def singapore():
    """Page carrières SuccessFactors, catégorie « Ground Professionals »."""
    adresse = "https://careers.singaporeair.com/sia/go/Ground-Professionals/689144/"
    offres, debut = [], 0
    while True:
        page = lire(adresse + (f"{debut}/" if debut else "")).text  # pages suivantes : .../10/, .../20/
        lignes = re.findall(r'<tr class="data-row">(.*?)</tr>', page, re.S)
        for ligne in lignes:
            lien, titre = re.search(r'<a href="([^"]+)" class="jobTitle-link">([^<]+)</a>', ligne).groups()
            if any(o["lien"].endswith(lien) for o in offres):
                return offres  # au-delà de la dernière page, le site renvoie la première
            lieu = re.search(r'<span class="jobLocation">\s*([^<]+?)\s*</span>', ligne).group(1)
            jour = re.search(r'<span class="jobDate[^"]*">\s*([^<]+?)\s*</span>', ligne).group(1)
            offres.append({
                "entreprise": "Singapore Airlines",
                "titre": html.unescape(titre),
                "lieu": "Singapour" if lieu == "SG" else lieu,
                "date_publication": datetime.strptime(jour.replace("Sept", "Sep"), "%d %b %Y").strftime("%Y-%m-%d"),
                "lien": "https://careers.singaporeair.com" + lien,
            })
        if len(lignes) < 10:
            return offres
        debut += 10
        time.sleep(1)


def qatar():
    """Page carrières Avature, 6 offres par page."""
    offres, debut = [], 0
    while True:
        page = lire("https://careers.qatarairways.com/global/SearchJobs/",
                    params={"jobOffset": debut}).text
        articles = re.findall(r'<article class="article article--result.*?</article>', page, re.S)
        for article in articles:
            lien, titre = re.search(r'<a class="link" href="([^"]+)"[^>]*>\s*(.*?)\s*</a>', article, re.S).groups()
            if any(o["lien"] == lien for o in offres):
                return offres  # même garde-fou que pour Singapore Airlines
            texte = nettoyer(article)
            lieu = re.search(r"Work locations: (.*?) Posting date", texte)
            jour = re.search(r"Posting date: (\d\d-\d\d-\d{4})", texte)
            offres.append({
                "entreprise": "Qatar Airways",
                "titre": html.unescape(titre.split(" | ")[-1]),
                "lieu": lieu.group(1) if lieu else "",
                "date_publication": datetime.strptime(jour.group(1), "%d-%m-%Y").strftime("%Y-%m-%d") if jour else "",
                "lien": lien,
            })
        if len(articles) < 6:
            return offres
        debut += 6
        time.sleep(1)


def emirates():
    """Interface utilisée par emiratesgroupcareers.com : toutes les offres, avec leur description."""
    offres = []
    for o in lire("https://www.emiratesgroupcareers.com/api/v1/jobs", params={"showAll": "true"}).json()["data"]:
        offres.append({
            "entreprise": f"Emirates Group ({o.get('brand') or 'Emirates'})",
            "titre": html.unescape(o["title"]),
            "lieu": ", ".join(x for x in (o.get("city"), o.get("country")) if x),
            "date_publication": datetime.fromtimestamp(o["postingdate"] / 1000, timezone.utc).strftime("%Y-%m-%d") if o.get("postingdate") else "",
            "lien": f"https://www.emiratesgroupcareers.com/search-and-apply/{o['reqid']}/",
            "texte": nettoyer(o.get("jobdescription") or ""),
        })
    return offres


def air_new_zealand():
    """Page carrières (outil Attrax), 12 offres par page. Les tuiles n'indiquent pas de date de publication."""
    aujourd_hui = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    offres, page = [], 1
    while True:
        contenu = lire("https://careers.airnewzealand.co.nz/jobs", params={"page": page}).text
        tuiles = re.findall(r'<div class="attrax-vacancy-tile[ "].*?(?=<div class="attrax-vacancy-tile[ "]|$)', contenu, re.S)
        nouvelles = 0
        for tuile in tuiles:
            lien = re.search(r'href="(/job/[^"]+)"', tuile)
            if not lien or any(o["lien"].endswith(lien.group(1)) for o in offres):
                continue
            texte = re.sub(r"(\s*\|\s*)+", " | ", re.sub(r"<[^>]+>", " | ", tuile))
            titre = texte.strip(" |").split(" | ")[0]
            lieu = re.search(r"\| Location \| ([^|]+)", texte)
            offres.append({
                "entreprise": "Air New Zealand",
                "titre": html.unescape(titre),
                "lieu": lieu.group(1).strip() if lieu else "Nouvelle-Zélande",
                "date_publication": aujourd_hui,  # inconnue : on note le jour où le robot l'a vue
                "lien": "https://careers.airnewzealand.co.nz" + lien.group(1),
            })
            nouvelles += 1
        if not nouvelles:
            return offres
        page += 1
        time.sleep(1)


def air_tahiti_nui():
    """Page « Job offers » du site, souvent vide (petite compagnie)."""
    aujourd_hui = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    contenu = lire("https://www.airtahitinui.com/en/career/jobs").text
    liens = dict(re.findall(r'href="(/en/career/jobs/[^"#?]+)"[^>]*>\s*(?:<[^>]+>\s*)*([^<]+)', contenu))
    return [{"entreprise": "Air Tahiti Nui", "titre": html.unescape(titre.strip()), "lieu": "Polynésie française",
             "date_publication": aujourd_hui, "lien": "https://www.airtahitinui.com" + lien}
            for lien, titre in liens.items()]


JOURS_MAX = 60  # au-delà de 60 jours, une offre n'est plus analysée (ni affichée sur le tableau de bord)
JOURS_VIE = 14  # le robot ne lit que les offres VIE publiées depuis moins de 14 jours


def date_vie(page, lien):
    """Ouvre une annonce VIE et renvoie (date de publication « AAAA-MM-JJ », texte de l'annonce)."""
    for essai in (1, 2):  # le site est parfois lent : on laisse une seconde chance
        page.goto(lien, timeout=60000)
        try:
            page.wait_for_selector("text=Publiée le", state="attached", timeout=30000)
            break
        except Exception:
            if essai == 2 and len(page.locator("body").inner_text()) < 1500:
                raise  # page vraiment vide : l'annonce n'existe plus ou le site ne répond pas
            time.sleep(5)
    texte = page.locator("main").inner_text()
    date = re.search(r"Publiée le (\d{2})/(\d{2})/(\d{4})", texte)
    return (f"{date.group(3)}-{date.group(2)}-{date.group(1)}" if date else ""), texte


def business_france():
    """Offres VIE du portail Mon VIE-VIA, lues avec un navigateur automatisé (autorisé par Business France).

    La page de recherche affiche les offres de la plus récente à la plus ancienne, 6 par 6, avec un
    bouton « Voir plus d'offres ». On clique (avec une pause) jusqu'à atteindre des offres de plus de
    JOURS_VIE jours : toutes les 10 pages, on ouvre la dernière annonce affichée pour lire sa date.
    Seules les annonces récentes, nouvelles et qui passent le tri par mots-clés sont ensuite ouvertes."""
    base = "https://mon-vie-via.businessfrance.fr"
    limite = (datetime.now(timezone.utc) - timedelta(days=JOURS_VIE)).strftime("%Y-%m-%d")
    offres = []
    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        liste, annonce = navigateur.new_page(), navigateur.new_page()
        liste.goto(base + "/offres/recherche", timeout=60000)
        liste.wait_for_selector(".figure_container", state="attached", timeout=60000)
        time.sleep(2)
        nombre = liste.locator(".figure_container").count()
        for clic in range(1, 300):  # garde-fou : 300 pages = 1 800 offres
            if clic % 10 == 0:  # la dernière offre affichée est-elle trop ancienne ?
                dernier = liste.locator(".figure_container a.postuler").last.get_attribute("href")
                if date_vie(annonce, base + dernier)[0] < limite:
                    break
                time.sleep(2)
            bouton = liste.locator(".see-more-btn")
            if not bouton.count():
                break
            bouton.first.dispatch_event("click")
            time.sleep(1.5)
            nouveau = liste.locator(".figure_container").count()
            if nouveau == nombre:
                time.sleep(3)  # le site est peut-être lent : on laisse une seconde chance
                nouveau = liste.locator(".figure_container").count()
                if nouveau == nombre:
                    break
            nombre = nouveau
        cartes = liste.eval_on_selector_all(".figure_container", """cartes => cartes.map(c => ({
            entreprise: c.querySelector('.organization-name')?.innerText.trim() || '',
            titre: c.querySelector('.mission-title')?.innerText.trim() || '',
            lieu: c.querySelector('.location')?.innerText.trim() || '',
            lien: c.querySelector('a.postuler')?.getAttribute('href') || ''}))""")
        for carte in cartes:
            if carte["lien"] and not any(o["lien"] == base + carte["lien"] for o in offres):
                offres.append(dict(carte, lien=base + carte["lien"], date_publication=""))

        # Ouvre les annonces nouvelles et intéressantes pour lire leur texte et leur date
        for offre in list(offres):
            if offre["lien"] in LIENS_CONNUS or not filtre_titre("Business France (VIE)", offre["titre"]):
                continue
            try:
                offre["date_publication"], texte = date_vie(annonce, offre["lien"])
            except Exception as erreur:
                print(f"⚠️  VIE {offre['titre']} : annonce illisible ({erreur})")
                continue
            time.sleep(2)
            if offre["date_publication"] and offre["date_publication"] < limite:
                offres.remove(offre)  # trop ancienne : on l'ignore
                continue
            # On coupe la partie « contact » : aucune donnée nominative ne doit être transmise
            offre["texte"] = re.split(r"\n\s*CONTACT", texte, flags=re.I)[0]

        # Les offres VIE déjà enregistrées mais sorties de la fenêtre de 14 jours : sont-elles encore en ligne ?
        vues = {o["lien"] for o in offres}
        for lien in sorted(l for l in LIENS_CONNUS if l.startswith(base) and l not in vues):
            try:
                date_vie(annonce, lien)
                offres.append({"lien": lien, "titre": "", "deja_connue": True})
            except Exception:
                pass  # annonce introuvable : elle sera retirée du tableau de bord
            time.sleep(2)
        navigateur.close()
    return offres


def y_combinator():
    """Offres publiques des startups Y Combinator (ycombinator.com/jobs ; Work at a Startup bloque les robots).

    Chaque page affiche au plus une cinquantaine d'offres : on lit la page « Operations » et les pages
    par ville, puis on ouvre seulement les annonces nouvelles qui passent le tri par mots-clés."""
    base = "https://www.ycombinator.com"
    pages = ["operations", "product-manager"] + [f"operations/{ville}" for ville in (
        "san-francisco", "new-york", "los-angeles", "seattle", "boston", "austin", "chicago", "remote",
        "london", "paris", "berlin", "amsterdam", "europe", "singapore", "dubai", "india")]
    aujourd_hui = datetime.now(timezone.utc)
    offres = {}
    for chemin in pages:
        for o in props_yc(lire(f"{base}/jobs/role/{chemin}").text).get("jobPostings") or []:
            offres.setdefault(o["url"], {
                "entreprise": o["companyName"],
                "titre": o["title"],
                "lieu": o.get("location") or "",
                "date_publication": date_relative(o.get("createdAt") or "", aujourd_hui),
                "lien": base + o["url"],
            })
        time.sleep(1)
    for offre in offres.values():
        if offre["lien"] in LIENS_CONNUS or not filtre_titre("Y Combinator", offre["titre"]):
            continue
        j = props_yc(lire(offre["lien"]).text).get("job") or {}
        # Les infos utiles à Claude, sans le nom du recruteur (hiringManager)
        offre["texte"] = (f"Startup : {j.get('companyName')} ({j.get('companyOneLiner')}), promotion YC {j.get('companyBatchName')}\n"
                          f"Contrat : {j.get('type')} · Expérience minimale : {j.get('minExperience')} · Visa : {j.get('visa')}\n"
                          f"Salaire : {j.get('salaryRange')}\n\n{j.get('description') or ''}")
        time.sleep(1)
    return list(offres.values())


def props_yc(page_html):
    """Les pages YC rangent leurs données dans un attribut data-page (format JSON)."""
    m = re.search(r'data-page="([^"]+)"', page_html)
    return json.loads(html.unescape(m.group(1)))["props"] if m else {}


def date_relative(texte, aujourd_hui):
    """Transforme « 2 days », « about 1 month », « over 1 year » en date approximative AAAA-MM-JJ."""
    m = re.search(r"(\d+)\s*(minute|hour|day|week|month|year)", texte)
    jours = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}
    ecart = int(m.group(1)) * jours[m.group(2)] if m else 0
    return (aujourd_hui - timedelta(days=ecart)).strftime("%Y-%m-%d")


# French Tech 120 (promotion 2026) : entreprises dont l'outil de recrutement a une interface publique.
# Les 67 autres (Welcome to the Jungle ou site maison) ne sont pas encore lues.
FRENCH_TECH = {
    "lever": {"360Learning": "360learning", "Agicap": "agicap", "Bigblue": "bigblue", "BlaBlaCar": "blablacar",
              "Contentsquare": "contentsquare", "Ekimetrics": "ekimetrics", "Malt": "malt", "Pigment": "pigment",
              "Swile": "swile", "Verkor": "verkor", "Vestiaire Collective": "vestiairecollective"},
    "ashby": {"AMI Labs": "ami", "Akur8": "akur8", "Alan": "alan", "Alma": "alma", "Back Market": "backmarket",
              "Doctolib": "doctolib", "H Company": "hcompany", "Ledger": "ledger", "Pennylane": "pennylane",
              "Qonto": "qonto", "Seyna": "seyna", "Voodoo": "voodoo", "Yubo": "yubo"},
    "greenhouse": {"Flowdesk": "flowdesk", "Ouihelp": "ouihelp", "Shift Technology": "shifttechnology"},
    "workable": {"Exotec": "exotec"},
    "recruitee": {"Adikteev": "adikteev", "Mistertemp' Group": "mistertemp", "Quobly": "quobly"},
    "smartrecruiters": {"EcoVadis": "ecovadis", "Shippeo": "shippeo", "Yespark": "yespark"},
    "teamtailor": {"Akeneo": "akeneo", "Aqemia": "aqemia", "Deepki": "deepki", "Descartes Underwriting": "descartesunderwriting",
                   "Exotrail": "exotrail", "Foodles": "foodles", "GitGuardian": "gitguardian", "HomeExchange": "homeexchange",
                   "Hublo": "hublo", "Legalplace": "legalplace", "Libon": "libon", "MWM": "mwm", "MyLight150": "mylight150",
                   "MyUnisoft": "myunisoft", "Ornikar": "ornikar", "Pasqal": "pasqal", "PayFit": "payfit", "Stoïk": "stoik",
                   "Tissium": "tissium", "Waat": "waat"},
}


def offres_ats(outil, entreprise, code):
    """Lit les offres d'une entreprise sur l'interface publique de son outil de recrutement."""
    def offre(titre, lieu, date, lien, texte=""):
        return {"entreprise": entreprise, "titre": titre.strip(), "lieu": lieu or "", "date_publication": date or "",
                "lien": lien, "texte": nettoyer(texte) if texte else ""}
    if outil == "lever":
        return [offre(o["text"], (o.get("categories") or {}).get("location"),
                      datetime.fromtimestamp(o["createdAt"] / 1000, timezone.utc).strftime("%Y-%m-%d"),
                      o["hostedUrl"], o.get("descriptionPlain") or o.get("description") or "")
                for o in lire(f"https://api.lever.co/v0/postings/{code}", params={"mode": "json"}).json()]
    if outil == "ashby":
        return [offre(o["title"], o.get("location"), (o.get("publishedAt") or "")[:10], o["jobUrl"], o.get("descriptionPlain") or "")
                for o in lire(f"https://api.ashbyhq.com/posting-api/job-board/{code}").json()["jobs"] if o.get("isListed", True)]
    if outil == "greenhouse":
        return [offre(o["title"], (o.get("location") or {}).get("name"), (o.get("first_published") or o.get("updated_at") or "")[:10],
                      o["absolute_url"], html.unescape(o.get("content") or ""))
                for o in lire(f"https://boards-api.greenhouse.io/v1/boards/{code}/jobs", params={"content": "true"}).json()["jobs"]]
    if outil == "workable":
        return [offre(o["title"], ", ".join(x for x in (o.get("city"), o.get("country")) if x), o.get("published_on"), o["url"])
                for o in lire(f"https://apply.workable.com/api/v1/widget/accounts/{code}").json()["jobs"]]
    if outil == "recruitee":
        return [offre(o["title"], ", ".join(x for x in (o.get("city"), o.get("country")) if x), (o.get("published_at") or "")[:10],
                      o["careers_url"], o.get("description") or "")
                for o in lire(f"https://{code}.recruitee.com/api/offers/").json()["offers"]]
    if outil == "smartrecruiters":
        return [offre(o["name"], ", ".join(x for x in ((o.get("location") or {}).get("city"), (o.get("location") or {}).get("country")) if x),
                      (o.get("releasedDate") or "")[:10], f"https://jobs.smartrecruiters.com/{code}/{o['id']}")
                for o in lire(f"https://api.smartrecruiters.com/v1/companies/{code}/postings", params={"limit": 100}).json()["content"]]
    if outil == "teamtailor":  # flux RSS public
        offres = []
        for item in re.findall(r"<item>(.*?)</item>", lire(f"https://{code}.teamtailor.com/jobs.rss").text, re.S):
            champ = lambda nom: (re.search(rf"<{nom}>(.*?)</{nom}>", item, re.S) or [None, ""])[1]
            try:
                date = datetime.strptime(champ("pubDate").strip()[:16], "%a, %d %b %Y").strftime("%Y-%m-%d")
            except ValueError:
                date = ""
            offres.append(offre(html.unescape(champ("title")), html.unescape(champ("tt:city") or champ("tt:name")),
                                date, champ("link").strip(), html.unescape(champ("description"))))
        return offres
    return []


ENTREPRISES_EN_ECHEC = set()  # entreprises French Tech illisibles ce jour-là : on garde leurs offres


def french_tech():
    """Offres des entreprises de la French Tech 120 (promotion 2026) lisibles par une interface publique."""
    offres, total = [], sum(len(e) for e in FRENCH_TECH.values())
    for outil, entreprises in FRENCH_TECH.items():
        for entreprise, code in entreprises.items():
            try:
                offres += offres_ats(outil, entreprise, code)
            except Exception as erreur:  # une entreprise en panne ne bloque pas les autres
                print(f"⚠️  French Tech {entreprise} : lecture impossible ({erreur})")
                ENTREPRISES_EN_ECHEC.add(entreprise)
            time.sleep(0.5)
    if len(ENTREPRISES_EN_ECHEC) > total / 2:  # sans doute une coupure d'Internet : on ne touche à rien
        raise RuntimeError(f"{len(ENTREPRISES_EN_ECHEC)} entreprises sur {total} illisibles")
    return offres


SOURCES = {"Etihad Airways": etihad, "Lufthansa": lufthansa,
           "Singapore Airlines": singapore, "Qatar Airways": qatar,
           "Emirates": emirates, "Air New Zealand": air_new_zealand, "Air Tahiti Nui": air_tahiti_nui,
           "Business France (VIE)": business_france, "Y Combinator": y_combinator,
           "French Tech 120": french_tech}
VOLETS = {"Business France (VIE)": "autres", "Y Combinator": "startups", "French Tech 120": "startups"}  # les autres sources vont dans le volet « compagnies »


def filtre_titre(source, titre):
    """Premier tri gratuit sur l'intitulé : au moins un mot cible et aucun mot exclu."""
    if VOLETS.get(source) == "startups":
        return bool(MOTS_CIBLES_STARTUP.search(titre)) and not MOTS_EXCLUS_STARTUP.search(titre)
    if VOLETS.get(source) == "autres":
        return bool(MOTS_CIBLES_VIE.search(titre)) and not MOTS_EXCLUS_VIE.search(titre) and not MOTS_EXCLUS.search(titre)
    return bool(MOTS_CIBLES.search(titre)) and not MOTS_EXCLUS.search(titre)


# ---------- Texte complet d'une annonce ----------

def nettoyer(page_html):
    """Transforme du HTML en texte simple."""
    page_html = re.sub(r"(?is)<(script|style|nav|header|footer)\b.*?</\1>", " ", page_html)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page_html))).strip()


def texte_annonce(offre):
    if offre.get("texte"):  # Emirates : la description arrive avec la liste des offres
        return offre["texte"]
    if "detail" in offre:  # Etihad : l'interface donne l'annonce par sections
        sections = lire(offre["detail"]).json()["jobAd"]["sections"]
        return nettoyer(" ".join(s.get("text", "") for s in sections.values()))
    if offre["source"] == "Business France (VIE)":  # l'annonce n'a pas pu être ouverte : on réessaiera demain
        raise requests.RequestException("texte de l'annonce indisponible")
    return nettoyer(lire(offre["lien"]).text)


# ---------- Analyse par Claude ----------

class Analyse(BaseModel):
    pertinente: bool
    score: int
    raison: str
    type_contrat: Literal["CDI", "CDD", "VIE", "Graduate program", "Stage", "Alternance", "Autre", "Non précisé"]
    niveau: Literal["Junior", "Intermédiaire", "Senior", "Non précisé"]
    experience_demandee: str
    missions: str
    visa: Literal["Parrainé", "Nationalité ou visa exigé", "Non mentionné"]
    pays: str
    afrique: bool


def consignes(volet="compagnies"):
    """Reprend le profil (profil.md, ou le secret GitHub PROFIL en ligne) et les critères de CLAUDE.md."""
    texte = (DOSSIER / "CLAUDE.md").read_text(encoding="utf-8")
    profil = os.environ.get("PROFIL") or (DOSSIER / "profil.md").read_text(encoding="utf-8")
    criteres = texte[texte.index("## Critères communs"):texte.index("## Informations à extraire")]
    if volet == "startups":
        profil += "\n" + texte[texte.index("## Volet 2"):texte.index("## Volet 3")]
        sujet = "des offres d'emploi en startup et scale-up"
        condition_poste = """1. Le poste correspond aux postes recherchés du volet 2 : Chief of Staff, bras droit du CEO,
     CEO Office, Founder's Associate, chargé de projets stratégiques ou de transformation auprès de
     la direction, poste généraliste stratégie et opérations, ou poste produit junior : product owner,
     product manager peu expérimenté, associate product manager, product analyst. Écarte les assistants de direction
     traditionnels (secrétariat, agendas), les office managers purs, les consultants en cabinet
     externe, et les postes purement techniques ou commerciaux.
     Écarte les offres au Brésil qui exigent le portugais. Écarte les offres qui exigent la
     nationalité du pays ou un visa déjà obtenu (« US citizen », « must be authorized to work in
     the US », « no visa sponsorship »). « US citizenship/visa not required » n'est PAS un motif de refus."""
    elif volet == "autres":
        profil += "\n" + texte[texte.index("## Volet 1"):texte.index("## Volet 3")]
        sujet = "des offres de VIE (volontariat international en entreprise)"
        condition_poste = """1. Le poste correspond aux postes recherchés des volets 1 et 2 (product owner, product manager
     peu expérimenté, business analyst, chief of staff, projets stratégiques) ou à un poste proche :
     chef de projet digital ou transformation, stratégie, innovation, IA, marketing digital ou
     stratégique. Écarte les postes techniques (ingénierie, développement), purement commerciaux
     (prospection, vente) ou administratifs."""
    else:
        profil += "\n" + texte[texte.index("## Volet 1"):texte.index("## Volet 2")]
        sujet = "des offres d'emploi de compagnies aériennes"
        condition_poste = """1. Le poste correspond aux postes recherchés du volet 1 (business analyst, business owner,
     product owner, product manager peu expérimenté, ou intitulés proches)."""
    return f"""Tu aides un candidat à trier {sujet}.

{profil}
{criteres}
Pour l'offre fournie, réponds en français :
- pertinente : true si les trois conditions suivantes sont remplies, false sinon.
  {condition_poste}
  2. L'expérience demandée est de 3 ans maximum ou n'est pas indiquée. « 3 ans », « 3+ ans » ou
     « au moins 3 ans » sont acceptés. Écarte seulement si l'annonce exige clairement plus de 3 ans
     (4 ans, 5 ans…) ou s'il s'agit d'un poste senior, de direction ou d'encadrement d'équipe.
  3. Le contrat est un CDI, un CDD, un VIE, un graduate program ou un stage. Un contrat non précisé n'est PAS un motif de refus :
     écarte uniquement les autres types de contrats explicitement indiqués (freelance, intérim…).
  Écarte aussi les postes réservés aux nationaux du pays, et ceux qui exigent une autre langue que
  le français ou l'anglais (par exemple l'allemand courant). Si cette autre langue est seulement un
  plus (« un atout », « nice to have », « is a plus »), garde l'offre et signale-le dans la raison.
  Le candidat est citoyen français : il peut travailler sans permis dans toute l'Union européenne,
  l'Espace économique européen et en Suisse. Il est titulaire d'un master : quand l'annonce
  demande moins d'expérience aux titulaires d'un master, c'est cette durée qui compte.
- score : de 0 à 10, adéquation avec le profil.
- raison : une phrase qui justifie le verdict, en vouvoyant le candidat.
- missions : les missions en une phrase courte (ex. « produit, priorisation, suivi des indicateurs »).
- experience_demandee : par exemple « 2 ans minimum » ou « Non précisée ».
- visa : « Parrainé » seulement si l'annonce dit que l'entreprise parraine les visas.
- pays : le pays du poste, en français.
- afrique : true si le poste est situé en Afrique, false sinon."""


class Tri(BaseModel):
    garder: list[int]


def trier_titres(client, systeme, offres):
    """Étape bon marché : Claude lit seulement les intitulés (une seule demande pour toute la liste)
    et renvoie les numéros des offres qui méritent une lecture complète."""
    liste = "\n".join(f"{i}. {o['entreprise']} – {o['titre']} ({o['lieu']})" for i, o in enumerate(offres))
    reponse = client.messages.parse(
        model=MODELE,
        max_tokens=8000,
        output_config={"effort": "low"},
        system=systeme,
        messages=[{"role": "user", "content":
                   "Voici des offres dont tu ne vois que l'intitulé. Donne les numéros de celles qui "
                   "POURRAIENT correspondre aux postes recherchés et méritent qu'on lise l'annonce. "
                   "Écarte seulement celles dont l'intitulé montre clairement un poste hors sujet "
                   "(technique, commercial pur, comptabilité, poste senior ou de direction…). "
                   f"En cas de doute, garde l'offre.\n\n{liste}"}],
        output_format=Tri,
    )
    return set(reponse.parsed_output.garder)


SCHEMA_ANALYSE = anthropic.transform_schema(Analyse)


def analyser_en_lot(client, systemes, offres):
    """Envoie toutes les analyses d'un coup à l'API « Message Batches » (moitié prix).
    Les réponses arrivent en général en quelques minutes ; le robot attend au plus 3 heures."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    demandes = [Request(custom_id=str(i), params=MessageCreateParamsNonStreaming(
        model=MODELE,
        max_tokens=4000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA_ANALYSE}},
        system=systemes[VOLETS.get(o["source"], "compagnies")],
        messages=[{"role": "user", "content":
                   f"Entreprise : {o['entreprise']}\nIntitulé : {o['titre']}\n"
                   f"Lieu : {o['lieu']}\n\nAnnonce :\n{o['texte_complet']}"}],
    )) for i, o in enumerate(offres)]
    lot = client.messages.batches.create(requests=demandes)
    print(f"Lot de {len(demandes)} analyses envoyé, en attente des réponses…")
    for _ in range(360):  # 360 × 30 s = 3 heures maximum
        lot = client.messages.batches.retrieve(lot.id)
        if lot.processing_status == "ended":
            break
        time.sleep(30)
    else:
        client.messages.batches.cancel(lot.id)
        print("⚠️  Le lot n'a pas fini à temps : les offres seront analysées au prochain lancement")
        return {}
    resultats = {}
    for r in client.messages.batches.results(lot.id):
        if r.result.type != "succeeded":
            continue
        texte = next((b.text for b in r.result.message.content if b.type == "text"), "")
        try:
            resultats[int(r.custom_id)] = Analyse.model_validate_json(texte)
        except Exception:
            pass  # réponse illisible : l'offre sera réessayée au prochain lancement
    return resultats


def cle_api():
    if "ANTHROPIC_API_KEY" not in os.environ and (DOSSIER / ".env").exists():
        for ligne in (DOSSIER / ".env").read_text(encoding="utf-8").splitlines():
            if ligne.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = ligne.split("=", 1)[1].strip()
    return os.environ.get("ANTHROPIC_API_KEY")


# ---------- Programme principal ----------

def main():
    maintenant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    donnees = json.loads(FICHIER_OFFRES.read_text(encoding="utf-8")) if FICHIER_OFFRES.exists() else {"offres": []}
    connues = {o["lien"]: o for o in donnees["offres"]}

    client = anthropic.Anthropic(api_key=cle_api())
    systemes = {volet: consignes(volet) for volet in ("compagnies", "startups", "autres")}
    a_analyser, en_ligne, sources_lues = [], set(), set()
    LIENS_CONNUS.update(connues)

    for nom, recuperer in SOURCES.items():
        try:
            offres = recuperer()
        except Exception as erreur:  # un site en panne ne doit pas bloquer les autres
            print(f"⚠️  {nom} : lecture impossible ({erreur})")
            continue
        sources_lues.add(nom)
        retenues = [o for o in offres if filtre_titre(nom, o["titre"])]
        print(f"{nom} : {len(offres)} offres en ligne, {len(retenues)} retenues après le tri par mots-clés")
        for offre in offres:
            en_ligne.add(offre["lien"])
        for offre in retenues:
            if offre["lien"] not in connues:
                a_analyser.append(dict(offre, source=nom))

    # Retire les offres qui ne sont plus en ligne (seulement pour les sites lus avec succès)
    retirees = [l for l, o in connues.items() if o["source"] in sources_lues and l not in en_ligne
                and o["entreprise"] not in ENTREPRISES_EN_ECHEC]
    for lien in retirees:
        del connues[lien]

    def enregistrer(offre, analyse, volet, **extra):
        offre.pop("detail", None)
        offre.pop("texte", None)
        offre.pop("texte_complet", None)
        if not offre["date_publication"]:  # date inconnue : on note le jour où le robot l'a vue
            offre["date_publication"] = maintenant[:10]
        offre.update(analyse.model_dump(), volet=volet, premiere_vue=maintenant, **extra)
        connues[offre["lien"]] = offre

    # Les offres publiées depuis plus de 60 jours ne sont ni analysées ni affichées
    limite = (datetime.now(timezone.utc) - timedelta(days=JOURS_MAX)).strftime("%Y-%m-%d")
    trop_vieilles = [o for o in a_analyser if o.get("date_publication") and o["date_publication"] < limite]
    a_analyser = [o for o in a_analyser if o not in trop_vieilles]
    if trop_vieilles:
        print(f"{len(trop_vieilles)} offres ignorées car publiées depuis plus de {JOURS_MAX} jours")

    # Étape 2 : Claude trie les intitulés (une demande par volet, quelques centimes au plus)
    print(f"\n{len(a_analyser)} nouvelles offres après les mots-clés")
    gardees = []
    for volet in ("compagnies", "startups", "autres"):
        lot = [o for o in a_analyser if VOLETS.get(o["source"], "compagnies") == volet]
        if not lot:
            continue
        try:
            numeros = trier_titres(client, systemes[volet], lot)
        except anthropic.APIError as erreur:
            print(f"⚠️  Tri des titres impossible ({erreur}) : toutes les offres du volet {volet} seront lues")
            numeros = set(range(len(lot)))
        for i, offre in enumerate(lot):
            if i in numeros:
                gardees.append(offre)
            else:  # écartée sur le seul intitulé : rangée dans « Écartées par Claude », repêchable
                enregistrer(offre, Analyse(
                    pertinente=False, score=0, raison="Écartée par Claude sur le seul intitulé (annonce non lue).",
                    type_contrat="Non précisé", niveau="Non précisé", experience_demandee="Non précisée",
                    missions="", visa="Non mentionné", pays="", afrique=False), volet, ecartee_sur_titre=True)
        print(f"  {volet} : {len(numeros & set(range(len(lot))))} gardées sur {len(lot)} après lecture des titres")

    # Étape 3 : analyse complète des offres gardées, envoyées en un seul lot (moitié prix)
    a_lire = []
    for offre in gardees[:MAX_ANALYSES]:
        try:
            offre["texte_complet"] = texte_annonce(offre)[:8000]  # le début de l'annonce suffit
            a_lire.append(offre)
        except requests.RequestException as erreur:
            print(f"⚠️  {offre['titre']} : annonce illisible ({erreur}), nouvel essai au prochain lancement")
    print(f"\n{len(a_lire)} annonces à analyser ce coup-ci (plafond : {MAX_ANALYSES})")
    if a_lire:
        try:
            resultats = analyser_en_lot(client, systemes, a_lire)
        except anthropic.APIError as erreur:
            print(f"⚠️  Analyse impossible ({erreur}), nouvel essai au prochain lancement")
            resultats = {}
        for i, offre in enumerate(a_lire):
            if i in resultats:
                analyse = resultats[i]
                enregistrer(offre, analyse, VOLETS.get(offre["source"], "compagnies"))
                print(f"  {'✅' if analyse.pertinente else '❌'} [{analyse.score}/10] {offre['entreprise']} – {offre['titre']}")

    donnees = {"derniere_mise_a_jour": maintenant,
               "offres": sorted(connues.values(), key=lambda o: o["date_publication"], reverse=True)}
    FICHIER_OFFRES.parent.mkdir(exist_ok=True)
    FICHIER_OFFRES.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    gardees = sum(o["pertinente"] for o in connues.values())
    print(f"\nTerminé : {gardees} offres pertinentes au total, {len(retirees)} retirées car plus en ligne.")


if __name__ == "__main__":
    main()
