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
import hashlib
import base64
import imaplib
import email
import email.policy
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urljoin, urlparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import anthropic
import requests
from playwright.sync_api import sync_playwright
from pydantic import BaseModel

DOSSIER = Path(__file__).parent
FICHIER_OFFRES = DOSSIER / "docs" / "offres.json"
FICHIER_STARTUPS = DOSSIER / "startups_suivies.json"  # jeunes startups découvertes via leurs levées de fonds
MODELE = "claude-haiku-5-5"  # modèle le moins cher ; "claude-opus-5-5" juge plus finement
MAX_ANALYSES = int(sys.argv[1]) if len(sys.argv) > 1 else 60  # plafond de dépenses par lancement
EN_TETES = {"User-Agent": "Mozilla/5.0 (compatible; veille-emploi-personnelle)"}

# Premier tri gratuit sur l'intitulé : il faut au moins un mot cible et aucun mot exclu.
MOTS_CIBLES = re.compile(
    r"\b(product|produkt|produto|business analyst|business owner|analyst|analytics|analista|digital|owner|strateg\w*"
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
    r"\b(staff (?:product|engineer|software|data)\w*|driver|warehouse|group product|executive assistant|office manager|deployment|customer success|engineer|engineering|developer|nurse|sales|account executive"
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


def cathay_pacific():
    """Offres de careers.cathaypacific.com (lecture quotidienne autorisée par Cathay Pacific par e-mail, novembre 2026 :
    une fois par jour, usage personnel, aucune rediffusion). La liste n'apparaît qu'une fois la page affichée par un
    navigateur : le robot ouvre chaque page de résultats (20 offres) et lit la liste que la page reçoit, avec une pause."""
    base = "https://careers.cathaypacific.com"
    offres, page_num = [], 1
    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        page = navigateur.new_page(user_agent=EN_TETES["User-Agent"])
        while True:
            with page.expect_response(lambda r: "job-search.json" in r.url, timeout=60000) as reponse:
                page.goto(f"{base}/en/careers/jobs?keyword=&sortby=date&page={page_num}", timeout=60000)
            donnees = reponse.value.json()
            for o in donnees.get("items", []):
                offres.append({
                    "entreprise": "Cathay Pacific",
                    "titre": html.unescape(o["title"]).strip(),
                    "lieu": " ".join((o.get("location") or "").split()),
                    "date_publication": (o.get("applicationStartDate_s") or "")[:10],
                    "lien": base + o["url"],
                })
            if page_num >= donnees.get("meta", {}).get("totalPages", 1):
                break
            page_num += 1
            time.sleep(3)
        navigateur.close()
    return offres


def qantas():
    """Offres du groupe Qantas (lecture quotidienne autorisée par Qantas par e-mail, novembre 2026 : une fois par jour,
    données publiques, aucune rediffusion). L'ancien tableau Workday est vide : Qantas publie désormais ses offres
    sur SmartRecruiters, lu par son interface publique (une seule requête)."""
    return offres_ats("smartrecruiters", "Qantas", "QantasGroup")


def korean_air():
    """Campagnes de recrutement de recruit.koreanair.com (outil coréen « recruiter.co.kr »), lecture quotidienne autorisée
    par Korean Air par e-mail (novembre 2026 : une fois par jour, données publiques, aucune rediffusion).
    Une seule requête ; on ne garde que les campagnes dont les candidatures sont ouvertes. Intitulés en coréen."""
    filtre = {"keyword": "", "tagSnList": [], "jobGroupSnList": [], "careerTypeList": [], "regionSnList": [],
              "submissionStatusList": [], "openStatusList": [], "resumeLanguageTypeList": []}
    reponse = requests.post("https://api-recruiter.recruiter.co.kr/position/v1/jobflex", timeout=30,
                            headers={**EN_TETES, "prefix": "koreanair.recruiter.co.kr"},
                            json={"pageableRq": {"page": 1, "size": 100, "sort": ["CREATED_DATE_TIME"]}, "filter": filtre})
    reponse.raise_for_status()
    # Le détail des annonces est une affiche (image) : Claude juge sur l'intitulé, les étiquettes et les dates.
    return [{"entreprise": "Korean Air", "titre": o["title"].strip(), "lieu": "Corée du Sud",
             "date_publication": (o.get("startDateTime") or "")[:10],
             "lien": f"https://koreanair.recruiter.co.kr/career/jobs/{o['positionSn']}",
             "texte": f"Campagne de recrutement Korean Air (annonce en coréen, détail publié sous forme d'image). "
                      f"Intitulé : {o['title']}. Étiquettes : {', '.join(t['tagName'] for t in o.get('tagList') or [])}. "
                      f"Niveau : {o.get('classificationCode', '')}. Candidatures du {(o.get('startDateTime') or '')[:10]} "
                      f"au {(o.get('endDateTime') or '')[:10]}."}
            for o in reponse.json()["list"] if o.get("submissionStatus") == "IN_SUBMISSION"]


def starlux():
    """Offres de careers.jx-starlux.com, lues par l'interface publique du site (une requête). Lecture quotidienne
    autorisée par STARLUX par e-mail (novembre 2026 : une fois par jour, usage personnel, aucune rediffusion)."""
    donnees = lire("https://erecruiter.jx-starlux.com/api/0.1.0/jobs", params={"rowPerPage": 100}).json()["result"]["data"]
    return [{"entreprise": "STARLUX Airlines", "titre": html.unescape(o["name"]).strip(),
             "lieu": (o.get("location") or {}).get("name") or o.get("locationName") or "Taïwan",
             "date_publication": (o.get("published") or "").replace("/", "-")[:10],
             "lien": f"https://careers.jx-starlux.com/Jobs/Detail/{o['id']}",
             "texte": nettoyer((o.get("description") or "") + " " + (o.get("conditions") or ""))}
            for o in donnees]


def sas():
    """Offres de careers.sasgroup.net (même outil que TAP, présentation en tuiles, sans date de publication).
    Lecture quotidienne autorisée par SAS par e-mail (novembre 2026 : une fois par jour, sans trafic excessif)."""
    base = "https://careers.sasgroup.net"
    aujourd_hui = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    offres, debut = {}, 0
    while True:
        contenu = lire(base + "/search/", params={"q": "", "sortColumn": "referencedate", "sortDirection": "desc",
                                                  "startrow": debut}).text
        nouvelles = 0
        for tuile in re.findall(r'<li[^>]+class="job-tile .*?</li>', contenu, re.S):
            lien = re.search(r'href="(/job/[^"]+)"', tuile)
            titre = re.search(r'class="jobTitle-link[^"]*"[^>]*>\s*([^<]+?)\s*</a>', tuile)
            lieu = re.search(r'multilocation-value">\s*([^<]+?)\s*</div>', tuile)
            if not lien or not titre or base + html.unescape(lien.group(1)) in offres:
                continue
            offres[base + html.unescape(lien.group(1))] = {
                "entreprise": "SAS", "titre": html.unescape(titre.group(1)),
                "lieu": html.unescape(lieu.group(1)) if lieu else "Scandinavie",
                "date_publication": aujourd_hui,  # inconnue : on note le jour où le robot l'a vue
                "lien": base + html.unescape(lien.group(1))}
            nouvelles += 1
        if nouvelles < 20:
            return list(offres.values())
        debut += nouvelles
        time.sleep(2)


def vietnam_airlines():
    """Annonces de recrutement publiques de vietnamairlines.com (« Career with us »). Le portail tuyendung.* exige une
    connexion : il n'est pas lu. La liste n'apparaît qu'une fois la page affichée : le robot l'ouvre avec le navigateur
    automatisé. Lecture quotidienne autorisée par Vietnam Airlines par e-mail (novembre 2026), données publiques seulement."""
    base = "https://www.vietnamairlines.com"
    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        page = navigateur.new_page(user_agent=EN_TETES["User-Agent"])
        page.goto(base + "/vn/vi/vietnam-airlines/career-with-us/information", wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(3000)
        liens = page.eval_on_selector_all("a[href*='career-with-us/information/']",
                                          "els => els.map(a => [a.getAttribute('href'), a.innerText.trim()])")
        navigateur.close()
    offres = {}
    for lien, titre in liens:
        date = re.search(r"(\d{2})(\d{2})(\d{4})$", lien.rstrip("/"))  # l'adresse finit par MMJJAAAA
        lien = urljoin(base, lien).replace("/content/vna/vn/vi/", "/vn/vi/")
        if titre and lien not in offres:
            offres[lien] = {"entreprise": "Vietnam Airlines", "titre": " ".join(titre.split()), "lieu": "Viêt Nam",
                            "date_publication": f"{date[3]}-{date[1]}-{date[2]}" if date else "", "lien": lien}
    return list(offres.values())


# China Eastern publie en chinois : premier tri sur des mots chinois (produit, numérique, stratégie, analyse…)
MOTS_CHINE = re.compile(r"产品|数字|数据|战略|规划|分析|储备人才|国际化|管培|燕计划|信息|市场|营销|商务|电商|创新|智能|AI|IT类")
EXCLUS_CHINE = re.compile(r"飞行|招飞|乘务|安全员|机务|医生|医学|餐厨")


def china_eastern():
    """Annonces de job.ceair.com : recrutement confirmé (rubrique 3000) et campus (rubrique 4000) ; pilotes et
    personnel navigant ne sont pas lus. Lecture quotidienne autorisée par China Eastern par e-mail (novembre 2026) :
    une fois par jour, rubriques publiques uniquement, aucune rediffusion. Annonces en chinois."""
    offres = {}
    for rubrique in (3000, 4000):
        page_num = 1
        while True:
            reponse = requests.post("https://job.ceair.com/Ashx/Campus.ashx?active=GetPositionListByParams", headers=EN_TETES,
                                    timeout=30, data={"pageIndex": page_num, "pageSize": 50, "positionName": "", "workCity": "",
                                                      "cateId": "", "deptId": "", "banKuaiId": rubrique})
            reponse.raise_for_status()
            donnees = reponse.json()
            for o in donnees.get("data") or []:
                code = lambda x: base64.b64encode(str(x).encode()).decode()
                lien = f"https://job.ceair.com/JobDetail.html?positionId={code(o['zp_NewsInfoID'])}&cateId={code(o['News_CategoryId'])}"
                offre = offres.setdefault(lien, {
                    "entreprise": "China Eastern Airlines", "titre": o["News_Title"].strip(), "lieu": "Chine",
                    "date_publication": datetime.fromtimestamp(int(re.search(r"\d+", o["News_CreateDate"])[0]) / 1000,
                                                               timezone.utc).strftime("%Y-%m-%d"),
                    "lien": lien, "postes": [], "texte": ""})
                offre["postes"].append(o.get("Active_Name") or "")
                if o.get("Active_WorkAddress"):
                    offre["lieu"] = f"{o['Active_WorkAddress']}, Chine"
                offre["texte"] += f"\nPoste : {o.get('Active_Name', '')} ({o.get('Active_WorkAddress', '')})\n{(o.get('Active_Notice') or '')[:1500]}"
            if page_num * 50 >= (donnees.get("total") or 0):
                break
            page_num += 1
            time.sleep(2)
        time.sleep(2)
    retenues = []
    for o in offres.values():
        intitules = o.pop("postes") + [o["titre"]]
        if MOTS_CHINE.search(" ".join(intitules)) and not EXCLUS_CHINE.search(" ".join(intitules)):
            retenues.append(o)
    return retenues


def tap_portugal():
    """Offres du portail recrutamento.tap.pt (lecture quotidienne autorisée par TAP par e-mail, novembre 2026 : une fois
    par jour, données publiques, usage personnel). Page de recherche triée par date, 25 offres par page, avec une pause.
    Les « candidatures spontanées » ne sont pas des offres : on les ignore."""
    base = "https://recrutamento.tap.pt"
    offres, debut = [], 0
    while True:
        contenu = lire(base + "/search/", params={"q": "", "sortColumn": "referencedate", "sortDirection": "desc",
                                                  "startrow": debut}).text
        lignes = re.findall(r'<tr class="data-row[^"]*".*?</tr>', contenu, re.S)
        for ligne in lignes:
            lien = re.search(r'href="(/job/[^"]+)"', ligne)
            textes = [html.unescape(x.strip()) for x in re.sub(r"<[^>]+>", "|", ligne).split("|") if x.strip()]
            date = re.search(r"(\d{2})/(\d{2})/(\d{4})", ligne)
            if not lien or not textes or re.search(r"espont|spontaneous", textes[0], re.I):
                continue
            lieu = next((x for x in textes[1:] if "/" in x and not re.match(r"\d", x)), "Portugal")
            offres.append({
                "entreprise": "TAP Air Portugal",
                "titre": textes[0],
                "lieu": lieu.replace("/", ", "),
                "date_publication": f"{date[3]}-{date[2]}-{date[1]}" if date else "",
                "lien": base + html.unescape(lien.group(1)),
            })
        if len(lignes) < 25:
            return offres
        debut += 25
        time.sleep(2)


JOURS_MAX = 60  # au-delà de 60 jours, une offre n'est plus analysée (ni affichée sur le tableau de bord)
# Les VIE en Europe (hors pays nordiques) ne sont gardés que si le poste est très bon pour le candidat (score de Claude d'au moins 7/10)
PAYS_EUROPE = {"France", "Allemagne", "Autriche", "Belgique", "Bulgarie", "Chypre", "Croatie", "Espagne",
               "Estonie", "Grèce", "Hongrie", "Irlande", "Italie", "Lettonie", "Lituanie", "Luxembourg",
               "Malte", "Pays-Bas", "Pologne", "Portugal", "République tchèque", "Tchéquie", "Roumanie", "Slovaquie",
               "Slovénie", "Royaume-Uni", "Suisse", "Monaco", "Serbie", "Ukraine",
               "Bosnie-Herzégovine", "Albanie", "Macédoine du Nord", "Monténégro", "Moldavie", "Liechtenstein"}
SCORE_VIE_EUROPE = 7  # pays nordiques (Suède, Norvège, Danemark, Finlande, Islande) non concernés
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

# Scale-ups d'Asie et du Moyen-Orient dont l'outil de recrutement a une interface publique
# (Tech in Asia refuse tout ce qui n'est pas un vrai navigateur : non lu).
ASIE_MOYEN_ORIENT = {
    "lever": {"CRED": "cred", "Lalamove": "lalamove", "Meesho": "meesho", "Ninja Van": "ninjavan", "Nium": "nium"},
    "ashby": {"Airwallex": "airwallex", "Ziina": "ziina"},
    "greenhouse": {"Careem": "careem", "Coupang": "coupang", "Groww": "groww", "Moloco": "moloco",
                   "Sendbird": "sendbird", "Tamara": "tamara", "Thunes": "thunes", "Xendit": "xendit"},
    "workable": {"Ajaib": "ajaib", "Foodics": "foodics", "Funding Societies": "fundingsocieties",
                 "Mercari": "mercari", "Salla": "salla", "SmartNews": "smartnews"},
    "recruitee": {"PatSnap": "patsnap", "Unifonic": "unifonic"},
    "smartrecruiters": {"Doctor Anywhere": "doctoranywhere", "Freshworks": "freshworks", "Grab": "grab", "Swiggy": "swiggy"},
}

# Scale-ups africaines (les postes en Afrique s'affichent dans une section à part du tableau de bord)
AFRIQUE = {
    "ashby": {"Andela": "andela", "LemFi": "lemfi", "M-KOPA": "m-kopa"},
    "greenhouse": {"Jumia": "jumia", "Moniepoint": "moniepoint", "Ozow": "ozow"},
    "workable": {"Kuda": "kuda"},
    "smartrecruiters": {"Brimore": "brimore", "PalmPay": "palmpay", "Yassir": "yassir"},
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


def lire_liste(liste, nom):
    """Lit toutes les entreprises d'une liste {outil: {entreprise: code}}."""
    offres, total = [], sum(len(e) for e in liste.values())
    echecs = 0
    for outil, entreprises in liste.items():
        for entreprise, code in entreprises.items():
            try:
                offres += offres_ats(outil, entreprise, code)
            except Exception as erreur:  # une entreprise en panne ne bloque pas les autres
                print(f"⚠️  {nom} {entreprise} : lecture impossible ({erreur})")
                ENTREPRISES_EN_ECHEC.add(entreprise)
                echecs += 1
            time.sleep(0.5)
    if echecs > total / 2:  # sans doute une coupure d'Internet : on ne touche à rien
        raise RuntimeError(f"{echecs} entreprises sur {total} illisibles")
    return offres


def french_tech():
    """Offres des entreprises de la French Tech 120 (promotion 2026) lisibles par une interface publique."""
    return lire_liste(FRENCH_TECH, "French Tech")


def asie_moyen_orient():
    """Offres de scale-ups d'Asie et du Moyen-Orient lisibles par une interface publique."""
    return lire_liste(ASIE_MOYEN_ORIENT, "Asie / Moyen-Orient")


def afrique():
    """Offres de scale-ups africaines lisibles par une interface publique."""
    return lire_liste(AFRIQUE, "Afrique")


# ---------- Jeunes startups en croissance : découvertes via leurs levées de fonds ----------
# Chaque semaine, Les Pépites Tech publie les levées de fonds françaises (données Eldorado.co).
# On garde les tours d'amorçage, série A et série B, puis on cherche où chaque startup publie ses offres :
#   1. un outil de recrutement à interface publique (Lever, Ashby…) repéré dans les liens de son site ;
#   2. sinon sa page carrières, que Claude lit (seulement quand elle a changé, pour limiter le coût).

PEPITES = "https://lespepitestech.com"
TOURS_GARDES = re.compile(r"pre-?seed|seed|amor|s[ée]rie [ab]\b|series [ab]\b", re.I)
MOIS_SUIVI = 18  # une startup est suivie pendant 18 mois après sa levée
LIENS_ATS = [  # (outil, motif repérant l'outil dans un lien du site)
    ("lever", r"jobs\.(?:eu\.)?lever\.co/([\w.-]+)"),
    ("ashby", r"jobs\.ashbyhq\.com/([\w.%-]+)"),
    ("greenhouse", r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([\w-]+)"),
    ("workable", r"apply\.workable\.com/([\w-]+)"),
    ("recruitee", r"([\w-]+)\.recruitee\.com"),
    ("teamtailor", r"([\w-]+)\.teamtailor\.com"),
    ("smartrecruiters", r"(?:careers|jobs)\.smartrecruiters\.com/([\w-]+)"),
    ("wttj", r"welcometothejungle\.com/(?:fr|en)/companies/([\w-]+)"),
]
MOTS_CARRIERES = re.compile(r"career|carri[eè]re|jobs?\b|emplois?|recrut|join|rejoign|hiring|work-with-us|talent", re.I)


def charger_suivi():
    if FICHIER_STARTUPS.exists():
        return json.loads(FICHIER_STARTUPS.read_text(encoding="utf-8"))
    return {"articles_lus": [], "startups": {}}


def outil_dans_page(contenu):
    """Cherche dans le HTML d'une page un lien vers un outil de recrutement connu."""
    for outil, motif in LIENS_ATS:
        m = re.search(motif, contenu, re.I)
        if m and m.group(1).lower() not in ("www", "jobs", "app", "embed", "api"):
            return outil, m.group(1)
    return None


def trouver_offres_startup(site):
    """Renvoie {"outil": ..., "code": ...} ou {"outil": "page", "page": url} ou {"outil": "aucun"}."""
    try:
        accueil = lire(site).text
    except Exception:
        return {"outil": "aucun"}
    trouve = outil_dans_page(accueil)
    if trouve and trouve[0] != "wttj":
        return {"outil": trouve[0], "code": trouve[1]}
    # Liens vers une page carrières sur le même site
    candidats = []
    for lien, texte in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', accueil, re.S | re.I):
        if MOTS_CARRIERES.search(lien) or MOTS_CARRIERES.search(re.sub(r"<[^>]+>", " ", texte)):
            url = urljoin(site, lien)
            if urlparse(url).netloc.replace("www.", "") == urlparse(site).netloc.replace("www.", ""):
                candidats.append(url)
    for page in list(dict.fromkeys(candidats))[:3]:
        try:
            contenu = lire(page).text
        except Exception:
            continue
        trouve = outil_dans_page(contenu)
        if trouve and trouve[0] != "wttj":
            return {"outil": trouve[0], "code": trouve[1]}
        if trouve:  # offres publiées sur Welcome to the Jungle : illisibles par le robot
            return {"outil": "wttj", "code": trouve[1]}
        if len(nettoyer(contenu)) > 300:
            return {"outil": "page", "page": page}
        time.sleep(1)
    return {"outil": "wttj", "code": trouve[1]} if trouve else {"outil": "aucun"}


def decouvrir_startups(suivi):
    """Lit les récapitulatifs hebdomadaires de levées de fonds pas encore traités (au plus 26 semaines)."""
    articles = []
    for page in range(3):
        contenu = lire(f"{PEPITES}/blog/levees-de-fonds", params={"page": page} if page else None).text
        articles += re.findall(r'href="(/blog/20\d\d/\d\d/\d\d/[^"?]*semaine-\d+-20\d\d)"', contenu)
        if suivi["articles_lus"]:  # après le premier lancement, la première page suffit
            break
        time.sleep(1)
    nouvelles = 0
    for article in list(dict.fromkeys(articles))[:26]:
        if article in suivi["articles_lus"]:
            continue
        date_article = "-".join(article.split("/")[2:5])
        contenu = lire(PEPITES + article).text
        for bloc in re.split(r"<h2", contenu)[1:]:
            nom = nettoyer("<h2" + bloc.split("</h2>")[0])
            tour = re.search(r"<strong>([\d,.]+) en ([^<]+)</strong>", bloc)
            site = re.search(r'href="(https?://[^"]+?)(?:\?utm[^"]*)?"[^>]*>\s*Voir le site web', bloc)
            if not (nom and tour and site) or not TOURS_GARDES.search(tour.group(2)) or nom in suivi["startups"]:
                continue
            fiche = {"site": site.group(1), "tour": tour.group(2).strip(), "montant": tour.group(1), "levee_le": date_article}
            fiche.update(trouver_offres_startup(fiche["site"]))
            suivi["startups"][nom] = fiche
            nouvelles += 1
            print(f"  + {nom} ({fiche['tour']}) : {fiche['outil']}")
            time.sleep(1)
        suivi["articles_lus"].append(article)
        time.sleep(1)
    return nouvelles


class OffrePage(BaseModel):
    titre: str
    lien: str
    lieu: str


class OffresPage(BaseModel):
    offres: list[OffrePage]


def offres_page_carrieres(client, nom, fiche):
    """Lit une page carrières « maison ». Claude n'est sollicité que si la page a changé."""
    contenu = lire(fiche["page"]).text
    # Texte de la page en gardant les liens, pour que Claude puisse les recopier
    avec_liens = re.sub(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>',
                        lambda m: f" [{re.sub(r'<[^>]+>', ' ', m.group(2)).strip()}]({urljoin(fiche['page'], m.group(1))}) ",
                        contenu, flags=re.S | re.I)
    texte = nettoyer(avec_liens)[:15000]
    empreinte = hashlib.sha1(texte.encode()).hexdigest()
    if empreinte != fiche.get("empreinte"):
        reponse = client.messages.parse(
            model=MODELE, max_tokens=4000, output_config={"effort": "low"},
            messages=[{"role": "user", "content":
                       f"Voici la page carrières de la startup {nom}. Liste ses offres d'emploi ouvertes "
                       "(intitulé, lien complet vers l'annonce, lieu). N'inclus pas les candidatures spontanées. "
                       f"S'il n'y a aucune offre, renvoie une liste vide.\n\n{texte}"}],
            output_format=OffresPage,
        )
        # Garde-fou : on ne garde que les offres dont l'intitulé ou le lien figure vraiment sur la page
        fiche["offres"] = [dict(o.model_dump(), lien=o.lien if o.lien in texte and o.lien.startswith("http") else fiche["page"])
                           for o in reponse.parsed_output.offres
                           if o.lien in texte or o.titre.lower()[:40] in texte.lower()]
        fiche["empreinte"] = empreinte
    return [{"entreprise": nom, "titre": o["titre"], "lieu": o["lieu"], "date_publication": "",
             "lien": urljoin(fiche["page"], o["lien"]) or fiche["page"]} for o in fiche.get("offres", [])]


def jeunes_startups():
    """Offres des jeunes startups suivies (amorçage, série A, série B), découvertes via leurs levées de fonds."""
    suivi = charger_suivi()
    try:
        nouvelles = decouvrir_startups(suivi)
        print(f"Jeunes startups : {nouvelles} nouvelles startups découvertes, {len(suivi['startups'])} suivies")
    except Exception as erreur:
        print(f"⚠️  Découverte des levées de fonds impossible ({erreur})")
    limite = (datetime.now(timezone.utc) - timedelta(days=30 * MOIS_SUIVI)).strftime("%Y-%m-%d")
    client = anthropic.Anthropic(api_key=cle_api())
    offres, echecs, lisibles = [], 0, 0
    for nom, fiche in suivi["startups"].items():
        if fiche["levee_le"] < limite or fiche["outil"] in ("aucun", "wttj"):
            continue
        lisibles += 1
        try:
            if fiche["outil"] == "page":
                offres += offres_page_carrieres(client, nom, fiche)
            else:
                offres += offres_ats(fiche["outil"], nom, fiche["code"])
        except Exception as erreur:
            print(f"⚠️  Jeune startup {nom} : lecture impossible ({erreur})")
            ENTREPRISES_EN_ECHEC.add(nom)
            echecs += 1
        time.sleep(0.5)
    FICHIER_STARTUPS.write_text(json.dumps(suivi, ensure_ascii=False, indent=1), encoding="utf-8")
    if lisibles and echecs > lisibles / 2:
        raise RuntimeError(f"{echecs} startups sur {lisibles} illisibles")
    return offres


# ---------- États-Unis : job boards de fonds d'investissement et « Who is hiring? » ----------

FONDS_GETRO = ["jobs.accel.com", "jobs.generalcatalyst.com", "jobs.insightpartners.com", "jobs.khoslaventures.com",
               "jobs.thrivecap.com", "jobs.craftventures.com", "jobs.techstars.com",  # États-Unis et monde
               "careers.antler.co", "jobs.mevp.com"]  # Asie du Sud-Est (Antler) et Moyen-Orient (MEVP)
RECHERCHES_GETRO = ["chief of staff", "founder associate", "founders associate", "bizops", "business operations",
                    "strategy operations", "special projects", "associate product manager", "product manager", "product owner"]
STADES_GARDES = {"pre_seed", "seed", "series_a", "series_b", "series_c"}  # jeunes startups en forte croissance


def fonds_investissement():
    """Offres des startups financées par de grands fonds (pages publiques Getro), filtrées par stade de financement."""
    offres = {}
    for site in FONDS_GETRO:
        for recherche in RECHERCHES_GETRO:
            contenu = lire(f"https://{site}/jobs", params={"q": recherche}).text
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', contenu, re.S)
            if not m:
                continue
            for o in json.loads(m.group(1))["props"]["pageProps"]["initialState"]["jobs"]["found"]:
                org = o.get("organization") or {}
                # « Remote » est une plateforme qui republie les offres d'autres entreprises : on l'ignore
                if org.get("stage") not in STADES_GARDES or not o.get("url") or org.get("name") == "Remote":
                    continue
                offres.setdefault(o["url"], {
                    "entreprise": org.get("name", ""),
                    "titre": o["title"],
                    "lieu": " / ".join(o.get("locations") or []) or ("Remote" if o.get("workMode") == "remote" else ""),
                    "date_publication": datetime.fromtimestamp(o["createdAt"], timezone.utc).strftime("%Y-%m-%d") if o.get("createdAt") else "",
                    "lien": o["url"],  # lien direct vers l'annonce sur le site de la startup
                })
            time.sleep(1)
    return list(offres.values())


# ---------- LinkedIn : recherche publique (sans connexion), postes de Chief of Staff dans le monde ----------

RECHERCHES_LINKEDIN = ['"Chief of Staff" OR "Founder\'s Associate" OR "Founders Associate" OR "Founder\'s Office"',
                       '"Strategy & Operations" OR "Strategy and Operations" OR "Business Operations" OR "BizOps"']
VILLES_LINKEDIN = ["Singapore", "Hong Kong", "Dubai, United Arab Emirates", "Tokyo, Japan", "New York, United States",
                   "San Francisco Bay Area", "London, United Kingdom", "Berlin, Germany", "Paris, France", "Amsterdam, Netherlands"]


def linkedin():
    """Offres de la semaine sur LinkedIn (pages publiques), par mot-clé et par ville ; Claude ne garde que les startups.
    Une pause entre chaque requête ; si LinkedIn freine le robot (erreur 429), on s'arrête là pour aujourd'hui."""
    offres = {}
    for ville in VILLES_LINKEDIN:
        for recherche in RECHERCHES_LINKEDIN:
            for debut in (0, 10):  # 2 pages : les 20 offres les plus récentes
                for essai in (1, 2):
                    reponse = requests.get("https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                                           params={"keywords": recherche, "location": ville, "f_TPR": "r604800", "start": debut},
                                           headers=EN_TETES, timeout=30)
                    if reponse.status_code != 429:
                        break
                    if essai == 1:
                        time.sleep(60)  # LinkedIn demande de ralentir : on attend une minute, une seule fois
                if reponse.status_code == 429:
                    print(f"LinkedIn freine le robot : arrêt après {len(offres)} offres")
                    return list(offres.values())
                reponse.raise_for_status()
                cartes = reponse.text.split('<li>')[1:]
                for carte in cartes:
                    numero = re.search(r"urn:li:jobPosting:(\d+)", carte)
                    titre = re.search(r'base-search-card__title">\s*(.*?)\s*</h3>', carte, re.S)
                    if not numero or not titre:
                        continue
                    entreprise = re.search(r'base-search-card__subtitle">.*?>\s*(.*?)\s*</a>', carte, re.S)
                    lieu = re.search(r'job-search-card__location">\s*(.*?)\s*</span>', carte, re.S)
                    date = re.search(r'datetime="([\d-]+)"', carte)
                    lien = f"https://www.linkedin.com/jobs/view/{numero.group(1)}"
                    offres.setdefault(lien, {
                        "entreprise": html.unescape(entreprise.group(1)) if entreprise else "",
                        "titre": html.unescape(titre.group(1)),
                        "lieu": html.unescape(lieu.group(1)) if lieu else ville,
                        "date_publication": date.group(1) if date else "",
                        "lien": lien,
                    })
                time.sleep(5)
                if len(cartes) < 10:
                    break
    return list(offres.values())


def who_is_hiring():
    """Fil mensuel « Ask HN: Who is hiring? » de Hacker News (interface officielle Algolia de HN).
    Chaque commentaire est une offre rédigée par une startup ; on garde ceux qui parlent des postes visés."""
    fils = lire("https://hn.algolia.com/api/v1/search_by_date",
                params={"query": "Who is hiring", "tags": "story,author_whoishiring", "hitsPerPage": 2}).json()["hits"]
    offres = []
    for fil in fils:
        if not fil["title"].startswith("Ask HN: Who is hiring"):
            continue
        commentaires = lire(f"https://hn.algolia.com/api/v1/search",
                            params={"tags": f"comment,story_{fil['objectID']}", "hitsPerPage": 1000}).json()["hits"]
        for c in commentaires:
            if c.get("parent_id") != int(fil["objectID"]) or not c.get("comment_text"):
                continue  # seulement les offres (pas les réponses aux offres)
            texte = nettoyer(c["comment_text"])
            if not MOTS_CIBLES_STARTUP.search(texte[:1500]):
                continue
            entete = texte.split(" | ")
            offres.append({
                "entreprise": entete[0][:60],
                "titre": " | ".join(entete[1:3])[:150] if len(entete) > 1 else texte[:150],
                "lieu": entete[2][:80] if len(entete) > 2 else "",
                "date_publication": c["created_at"][:10],
                "lien": f"https://news.ycombinator.com/item?id={c['objectID']}",
                "texte": texte,
                "hn": True,
            })
        time.sleep(1)
    return offres


# ---------- Alertes e-mail (LinkedIn, Welcome to the Jungle, sites carrières…) ----------
# Le robot lit (sans rien modifier) les alertes emploi reçues sur Gmail ces derniers jours.
# Il ne visite jamais les sites d'origine : il se contente de ce que dit l'e-mail.

JOURS_ALERTES = 4  # relit les e-mails des 4 derniers jours (rattrape un lancement manqué)


class OffreAlerte(BaseModel):
    titre: str
    entreprise: str
    lieu: str
    lien: str
    volet: Literal["compagnies", "startups", "autres"]
    extrait: str


class OffresAlerte(BaseModel):
    offres: list[OffreAlerte]


def texte_avec_liens(contenu, base=""):
    """Texte d'une page ou d'un e-mail HTML en gardant les liens sous la forme [texte](lien)."""
    avec_liens = re.sub(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>',
                        lambda m: f" [{re.sub(r'<[^>]+>', ' ', m.group(2)).strip()}]({urljoin(base, m.group(1))}) ",
                        contenu, flags=re.S | re.I)
    return nettoyer(avec_liens)


def lien_propre(lien):
    """Retire les paramètres de suivi, pour reconnaître une même offre reçue dans plusieurs alertes."""
    m = re.search(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)", lien)
    if m:
        return f"https://www.linkedin.com/jobs/view/{m.group(1)}/"
    morceaux = urlparse(lien)
    gardes = [p for p in morceaux.query.split("&")
              if p and not re.match(r"(utm_|trk|tracking|refid|ref=|src=|source=|mc_|email)", p, re.I)]
    return morceaux._replace(query="&".join(gardes), fragment="").geturl()


def alertes_email():
    adresse = os.environ.get("GMAIL_ADRESSE", "").strip()
    mot_de_passe = os.environ.get("GMAIL_MOT_DE_PASSE", "").replace(" ", "")
    libelle = os.environ.get("GMAIL_LIBELLE", "").strip()  # facultatif : ne lire que ce libellé Gmail
    if not adresse or not mot_de_passe:
        print("   (alertes e-mail pas encore configurées : rien à lire)")
        return []
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    boite = imaplib.IMAP4_SSL("imap.gmail.com")
    boite.login(adresse, mot_de_passe)
    # Dossier « Tous les messages » (son nom dépend de la langue de Gmail)
    _, dossiers = boite.list()
    tous = next(d.decode().rsplit(' "/" ', 1)[1] for d in dossiers if b"\\All" in d)
    boite.select(tous, readonly=True)  # lecture seule : le robot ne touche à rien
    requete = f"newer_than:{JOURS_ALERTES}d" + (f" label:{libelle}" if libelle else "")
    _, numeros = boite.search(None, "X-GM-RAW", f'"{requete}"')
    offres = {}
    for numero in numeros[0].split()[-50:]:  # 50 e-mails au plus
        _, donnees = boite.fetch(numero, "(BODY.PEEK[])")
        message = email.message_from_bytes(donnees[0][1], policy=email.policy.default)
        corps = message.get_body(preferencelist=("html", "plain"))
        if corps is None:
            continue
        contenu = corps.get_content()
        texte = (texte_avec_liens(contenu) if corps.get_content_subtype() == "html" else contenu)[:15000]
        sujet = str(message["subject"] or "")
        try:
            date = parsedate_to_datetime(message["date"]).strftime("%Y-%m-%d")
        except Exception:
            date = ""
        reponse = client.messages.parse(
            model=MODELE, max_tokens=4000, output_config={"effort": "low"},
            messages=[{"role": "user", "content":
                       f"Voici un e-mail reçu (objet : « {sujet} »). S'il s'agit d'une alerte emploi, liste "
                       "les offres qu'il présente : intitulé, entreprise, lieu, lien complet vers l'annonce "
                       "(recopié tel quel depuis l'e-mail), volet (« compagnies » si l'employeur est une compagnie "
                       "aérienne, « startups » si c'est une startup ou une scale-up, « autres » sinon) et un extrait "
                       "reprenant tout ce que l'e-mail dit de l'offre (contrat, salaire, description…), sans rien "
                       "inventer et sans aucun nom de personne. Si l'e-mail ne présente aucune offre (publicité, "
                       f"message de bienvenue, autre sujet), renvoie une liste vide.\n\n{texte}"}],
            output_format=OffresAlerte,
        )
        for o in reponse.parsed_output.offres:
            if not (o.lien.startswith("http") and o.lien in texte):
                continue  # garde-fou : le lien doit vraiment figurer dans l'e-mail
            lien = lien_propre(o.lien)
            offres.setdefault(lien, {
                "entreprise": o.entreprise, "titre": o.titre, "lieu": o.lieu, "date_publication": date,
                "lien": lien, "volet": o.volet, "alerte": True,
                "texte": f"{o.extrait}\n(Offre reçue par alerte e-mail : « {sujet} ».)",
            })
    boite.logout()
    return list(offres.values())


SOURCES = {"Etihad Airways": etihad, "Lufthansa": lufthansa,
           "Singapore Airlines": singapore, "Qatar Airways": qatar,
           "Emirates": emirates, "Air New Zealand": air_new_zealand, "Air Tahiti Nui": air_tahiti_nui,
           "Cathay Pacific": cathay_pacific, "Qantas": qantas,
           "TAP Air Portugal": tap_portugal, "Korean Air": korean_air,
           "STARLUX Airlines": starlux, "SAS": sas, "Vietnam Airlines": vietnam_airlines,
           "China Eastern Airlines": china_eastern,
           "Business France (VIE)": business_france, "Y Combinator": y_combinator,
           "French Tech 120": french_tech, "Asie / Moyen-Orient": asie_moyen_orient,
           "Afrique": afrique, "Jeunes startups (levées de fonds)": jeunes_startups,
           "Fonds d'investissement (US)": fonds_investissement, "Hacker News (US)": who_is_hiring, "LinkedIn": linkedin,
           "Alertes e-mail": alertes_email}
VOLETS = {"Business France (VIE)": "autres", "Y Combinator": "startups", "French Tech 120": "startups", "Asie / Moyen-Orient": "startups", "Afrique": "startups", "Jeunes startups (levées de fonds)": "startups",
          "Fonds d'investissement (US)": "startups", "Hacker News (US)": "startups", "LinkedIn": "startups"}  # les autres sources vont dans le volet « compagnies »
SANS_VERIFICATION = {"Alertes e-mail", "LinkedIn"}  # e-mails, et LinkedIn qui ne montre que la semaine : on ne peut pas vérifier qu'elles sont toujours en ligne


def volet_de(offre):
    """Volet du tableau de bord : donné par la source, ou choisi par Claude pour les alertes e-mail."""
    return offre.get("volet") or VOLETS.get(offre["source"], "compagnies")


def filtre_titre(source, titre):
    """Premier tri gratuit sur l'intitulé : au moins un mot cible et aucun mot exclu."""
    if VOLETS.get(source) == "startups":
        return bool(MOTS_CIBLES_STARTUP.search(titre)) and not MOTS_EXCLUS_STARTUP.search(titre)
    if VOLETS.get(source) == "autres":
        return bool(MOTS_CIBLES_VIE.search(titre)) and not MOTS_EXCLUS_VIE.search(titre) and not MOTS_EXCLUS.search(titre)
    if source in ("Korean Air", "Vietnam Airlines"):  # intitulés en coréen / vietnamien, très peu d'annonces : Claude les juge toutes
        return True
    if source == "China Eastern Airlines":  # déjà triées sur des mots chinois dans china_eastern()
        return True
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
    ashby = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})", offre["lien"])
    if ashby:  # Ashby : page en JavaScript, mais son interface publique donne le texte
        for o in lire(f"https://api.ashbyhq.com/posting-api/job-board/{unquote(ashby.group(1))}").json()["jobs"]:
            if o["id"] == ashby.group(2):
                return o.get("descriptionPlain") or nettoyer(o.get("descriptionHtml", ""))
    linkedin = re.search(r"linkedin\.com/jobs/view/(\d+)", offre["lien"])
    if linkedin:  # LinkedIn : version publique de l'annonce (sans connexion)
        return nettoyer(lire(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{linkedin.group(1)}").text)
    texte = nettoyer(lire(offre["lien"]).text)
    if len(texte) < 500:  # page vide sans JavaScript (Gem, Workable…) : on l'ouvre dans le navigateur automatisé
        try:
            texte = texte_navigateur(offre["lien"])
        except Exception as erreur:
            print(f"⚠️  {offre['titre']} : page illisible même avec le navigateur ({erreur})")
    return texte


def texte_navigateur(lien):
    """Texte visible d'une page qui a besoin de JavaScript, lue avec le navigateur automatisé."""
    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        page = navigateur.new_page(user_agent=EN_TETES["User-Agent"])
        page.goto(lien, timeout=60000, wait_until="load")
        page.wait_for_timeout(5000)  # laisse le JavaScript afficher l'annonce
        texte = page.locator("body").inner_text()
        navigateur.close()
    return re.sub(r"\s+", " ", texte).strip()


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
     L'entreprise doit être une startup ou une scale-up en croissance : écarte les grands groupes établis
     (banques, multinationales, grandes entreprises tech cotées, cabinets de conseil ou de recrutement).
     Écarte les offres au Brésil qui exigent le portugais. Écarte les offres qui exigent la
     nationalité du pays ou un visa déjà obtenu (« US citizen », « must be authorized to work in
     the US », « no visa sponsorship »). « US citizenship/visa not required » n'est PAS un motif de refus."""
    elif volet == "autres":
        profil += "\n" + texte[texte.index("## Volet 1"):texte.index("## Volet 3")]
        sujet = "des offres de VIE (volontariat international en entreprise) et d'autres offres proches"
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
        system=systemes[volet_de(o)],
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
    """Charge les clés du fichier .env (sur l'ordinateur) ; en ligne, elles viennent des secrets GitHub."""
    if (DOSSIER / ".env").exists():
        for ligne in (DOSSIER / ".env").read_text(encoding="utf-8").splitlines():
            if "=" in ligne and not ligne.startswith("#"):
                cle, valeur = ligne.split("=", 1)
                os.environ.setdefault(cle.strip(), valeur.strip())
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
        retenues = [o for o in offres if o.get("hn") or o.get("alerte") or filtre_titre(nom, o["titre"])]
        print(f"{nom} : {len(offres)} offres en ligne, {len(retenues)} retenues après le tri par mots-clés")
        for offre in offres:
            en_ligne.add(offre["lien"])
        for offre in retenues:
            if offre["lien"] not in connues:
                a_analyser.append(dict(offre, source=nom))

    # Retire les offres qui ne sont plus en ligne (seulement pour les sites lus avec succès)
    retirees = [l for l, o in connues.items() if o["source"] in sources_lues and o["source"] not in SANS_VERIFICATION and l not in en_ligne
                and o["entreprise"] not in ENTREPRISES_EN_ECHEC]
    for lien in retirees:
        del connues[lien]

    def enregistrer(offre, analyse, volet, **extra):
        offre.pop("detail", None)
        offre.pop("texte", None)
        offre.pop("texte_complet", None)
        offre.pop("hn", None)
        offre.pop("alerte", None)
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
        lot = [o for o in a_analyser if volet_de(o) == volet]
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
                enregistrer(offre, analyse, volet_de(offre))
                print(f"  {'✅' if analyse.pertinente else '❌'} [{analyse.score}/10] {offre['entreprise']} – {offre['titre']}")

    # VIE en Europe (hors pays nordiques) : écartés sauf si le poste est très bon (repêchables depuis le tableau de bord)
    for offre in connues.values():
        if (offre["source"] == "Business France (VIE)" and offre["pertinente"]
                and offre.get("pays") in PAYS_EUROPE and offre["score"] < SCORE_VIE_EUROPE):
            offre["pertinente"] = False
            offre["raison"] = f"VIE en Europe, gardé seulement s'il vous correspond très bien ({SCORE_VIE_EUROPE}/10 minimum). " + offre["raison"]

    donnees = {"derniere_mise_a_jour": maintenant,
               "offres": sorted(connues.values(), key=lambda o: o["date_publication"], reverse=True)}
    FICHIER_OFFRES.parent.mkdir(exist_ok=True)
    FICHIER_OFFRES.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    gardees = sum(o["pertinente"] for o in connues.values())
    print(f"\nTerminé : {gardees} offres pertinentes au total, {len(retirees)} retirées car plus en ligne.")


if __name__ == "__main__":
    main()
