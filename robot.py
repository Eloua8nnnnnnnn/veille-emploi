"""Robot de veille emploi.

Récupère les offres sur les sites carrières, garde celles dont l'intitulé peut
correspondre, les fait juger par Claude selon le profil décrit dans CLAUDE.md,
puis enregistre le résultat dans docs/offres.json (lu par le tableau de bord).

Lancement :  .venv/bin/python robot.py        (analyse au plus 60 nouvelles offres)
             .venv/bin/python robot.py 5      (analyse au plus 5 offres, pour tester)
"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import anthropic
import requests
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


SOURCES = {"Etihad Airways": etihad, "Lufthansa": lufthansa,
           "Singapore Airlines": singapore, "Qatar Airways": qatar}


# ---------- Texte complet d'une annonce ----------

def nettoyer(page_html):
    """Transforme du HTML en texte simple."""
    page_html = re.sub(r"(?is)<(script|style|nav|header|footer)\b.*?</\1>", " ", page_html)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page_html))).strip()


def texte_annonce(offre):
    if "detail" in offre:  # Etihad : l'interface donne l'annonce par sections
        sections = lire(offre["detail"]).json()["jobAd"]["sections"]
        return nettoyer(" ".join(s.get("text", "") for s in sections.values()))
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


def consignes():
    """Reprend le profil (profil.md, ou le secret GitHub PROFIL en ligne) et les critères de CLAUDE.md."""
    texte = (DOSSIER / "CLAUDE.md").read_text(encoding="utf-8")
    profil = os.environ.get("PROFIL") or (DOSSIER / "profil.md").read_text(encoding="utf-8")
    profil += "\n" + texte[texte.index("## Volet 1"):texte.index("## Volet 2")]
    criteres = texte[texte.index("## Critères communs"):texte.index("## Informations à extraire")]
    return f"""Tu aides un candidat à trier des offres d'emploi de compagnies aériennes.

{profil}
{criteres}
Pour l'offre fournie, réponds en français :
- pertinente : true si les trois conditions suivantes sont remplies, false sinon.
  1. Le poste correspond aux postes recherchés du volet 1 (business analyst, business owner,
     product owner, product manager peu expérimenté, ou intitulés proches).
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
- pays : le pays du poste, en français."""


def analyser(client, systeme, offre, texte):
    reponse = client.messages.parse(
        model=MODELE,
        max_tokens=4000,
        output_config={"effort": "low"},
        system=systeme,
        messages=[{"role": "user", "content":
                   f"Entreprise : {offre['entreprise']}\nIntitulé : {offre['titre']}\n"
                   f"Lieu : {offre['lieu']}\n\nAnnonce :\n{texte}"}],
        output_format=Analyse,
    )
    return reponse.parsed_output


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
    systeme = consignes()
    a_analyser, en_ligne, sources_lues = [], set(), set()

    for nom, recuperer in SOURCES.items():
        try:
            offres = recuperer()
        except Exception as erreur:  # un site en panne ne doit pas bloquer les autres
            print(f"⚠️  {nom} : lecture impossible ({erreur})")
            continue
        sources_lues.add(nom)
        retenues = [o for o in offres if MOTS_CIBLES.search(o["titre"]) and not MOTS_EXCLUS.search(o["titre"])]
        print(f"{nom} : {len(offres)} offres en ligne, {len(retenues)} retenues après le tri par mots-clés")
        for offre in offres:
            en_ligne.add(offre["lien"])
        for offre in retenues:
            if offre["lien"] not in connues:
                a_analyser.append(dict(offre, source=nom))

    # Retire les offres qui ne sont plus en ligne (seulement pour les sites lus avec succès)
    retirees = [l for l, o in connues.items() if o["source"] in sources_lues and l not in en_ligne]
    for lien in retirees:
        del connues[lien]

    print(f"\n{len(a_analyser)} nouvelles offres à analyser, {min(len(a_analyser), MAX_ANALYSES)} analysées ce coup-ci")
    for offre in a_analyser[:MAX_ANALYSES]:
        try:
            analyse = analyser(client, systeme, offre, texte_annonce(offre)[:15000])
        except (requests.RequestException, anthropic.APIError) as erreur:
            print(f"⚠️  {offre['titre']} : analyse impossible ({erreur}), nouvel essai au prochain lancement")
            continue
        offre.pop("detail", None)
        offre.update(analyse.model_dump(), volet="compagnies", premiere_vue=maintenant)
        connues[offre["lien"]] = offre
        print(f"  {'✅' if analyse.pertinente else '❌'} [{analyse.score}/10] {offre['entreprise']} – {offre['titre']}")
        time.sleep(1)

    donnees = {"derniere_mise_a_jour": maintenant,
               "offres": sorted(connues.values(), key=lambda o: o["date_publication"], reverse=True)}
    FICHIER_OFFRES.parent.mkdir(exist_ok=True)
    FICHIER_OFFRES.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    gardees = sum(o["pertinente"] for o in connues.values())
    print(f"\nTerminé : {gardees} offres pertinentes au total, {len(retirees)} retirées car plus en ligne.")


if __name__ == "__main__":
    main()
