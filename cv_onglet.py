"""Copie un onglet de mon CV (Google Docs) dans un nouvel onglet, avec sa mise en page.

L'API Google Docs ne sait pas dupliquer un onglet : ce script lit le document (export JSON de
read_doc) et prépare la liste des modifications qui recréent le texte, les styles de paragraphe
(retraits, espacements, bordures), les styles de texte (gras, taille, couleur, police), les puces
et les marges dans l'onglet cible. Claude envoie ensuite ces modifications à Google Docs.

Utilisation :
  python3 cv_onglet.py dernier DOCUMENT.json                      → identifiant et nom du dernier onglet (le CV le plus récent)
  python3 cv_onglet.py copier DOCUMENT.json SOURCE CIBLE > r.json → requêtes qui recopient l'onglet SOURCE dans CIBLE
  python3 cv_onglet.py lettre DOCUMENT.json SOURCE CIBLE TEXTE.txt → requêtes qui écrivent la lettre TEXTE.txt dans l'onglet CIBLE,
                                                                    avec la mise en page de la lettre SOURCE (paragraphes séparés par
                                                                    une ligne vide ; un simple retour à la ligne reste dans le paragraphe)
  .venv/bin/python cv_onglet.py annonce LIEN                      → texte d'une annonce (navigateur automatisé, pour les sites en JavaScript)
  python3 cv_onglet.py file                                       → offres de la file d'attente « À préparer » (Google Sheet)
  python3 cv_onglet.py maj LIEN ETAT [CV] [LETTRE] [NOTE]         → note l'avancement d'une offre dans la file
  python3 cv_onglet.py idees IDEES.json                           → ajoute des idées de sorties à la page Social du dashboard
                                                                    ([{titre, categorie, lieu, lien, quand, fin}], doublons ignorés)
La file d'attente utilise SHEET_ADRESSE et SHEET_CLE du fichier .env (adresse et mot de passe du script Google Sheet).
"""
import json
import os
import sys
import urllib.request


def trouver_onglet(onglets, identifiant):
    for onglet in onglets:
        if onglet["tabProperties"]["tabId"] == identifiant:
            return onglet
        trouve = trouver_onglet(onglet.get("childTabs", []), identifiant)
        if trouve:
            return trouve
    return None


def requetes_copie(document, source, cible):
    document = document.get("content", document)
    onglet = trouver_onglet(document["tabs"], source)
    if not onglet:
        sys.exit(f"Onglet {source} introuvable")
    contenu = onglet["documentTab"]["body"]["content"]
    paragraphes = []
    for element in contenu:
        if "sectionBreak" in element:
            continue
        if "paragraph" not in element:
            sys.exit("Le CV contient un tableau ou un objet que ce script ne sait pas copier")
        paragraphes.append(element)
        for morceau in element["paragraph"]["elements"]:
            if "textRun" not in morceau:
                sys.exit("Le CV contient un élément non textuel (image, puce intelligente…) que ce script ne sait pas copier")

    texte = "".join(m["textRun"]["content"] for p in paragraphes for m in p["paragraph"]["elements"])
    plage = lambda debut, fin: {"startIndex": debut, "endIndex": fin, "tabId": cible}

    # 1. Le texte (le nouvel onglet contient déjà un paragraphe vide : on garde son retour à la ligne)
    requetes = [{"insertText": {"location": {"index": 1, "tabId": cible}, "text": texte[:-1]}}]

    # 2. Les puces, avant les retraits (les puces imposent leurs propres retraits, qu'on remplace ensuite)
    groupe = None
    for p in paragraphes + [None]:
        liste = p and p["paragraph"].get("bullet", {}).get("listId")
        if groupe and (liste != groupe[0] or p is None):
            requetes.append({"createParagraphBullets": {"range": plage(groupe[1], groupe[2]),
                                                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}})
            groupe = None
        if liste:
            groupe = [liste, groupe[1] if groupe else p["startIndex"], p["endIndex"]]

    # 3. Styles de paragraphe : le type (titre, texte normal) d'abord, puis le reste
    styles = [(p, {k: v for k, v in p["paragraph"]["paragraphStyle"].items() if k not in ("headingId", "tabStops", "direction")})
              for p in paragraphes]
    for p, style in styles:
        requetes.append({"updateParagraphStyle": {"range": plage(p["startIndex"], p["endIndex"]),
                                                  "paragraphStyle": {"namedStyleType": style.pop("namedStyleType")},
                                                  "fields": "namedStyleType"}})
    for p, style in styles:
        if style:
            requetes.append({"updateParagraphStyle": {"range": plage(p["startIndex"], p["endIndex"]),
                                                      "paragraphStyle": style, "fields": ",".join(style)}})

    # 4. Styles de texte, morceau par morceau
    for p in paragraphes:
        for m in p["paragraph"]["elements"]:
            style = m["textRun"].get("textStyle", {})
            if style:
                requetes.append({"updateTextStyle": {"range": plage(m["startIndex"], m["endIndex"]),
                                                     "textStyle": style, "fields": ",".join(style)}})

    # Fusionne les plages voisines qui reçoivent exactement le même style (moins de requêtes à envoyer)
    fusion = []
    for r in requetes:
        type_ = next(iter(r))
        precedente = fusion[-1] if fusion else None
        if (type_ in ("updateParagraphStyle", "updateTextStyle") and precedente and type_ in precedente
                and {k: v for k, v in precedente[type_].items() if k != "range"} == {k: v for k, v in r[type_].items() if k != "range"}
                and precedente[type_]["range"]["endIndex"] == r[type_]["range"]["startIndex"]):
            precedente[type_]["range"]["endIndex"] = r[type_]["range"]["endIndex"]
        else:
            fusion.append(r)
    requetes = fusion

    # 5. Marges et format de page
    page = onglet["documentTab"].get("documentStyle", {})
    champs = [c for c in ("marginTop", "marginBottom", "marginLeft", "marginRight", "pageSize") if c in page]
    if champs:
        requetes.append({"updateDocumentStyle": {"tabId": cible, "documentStyle": {c: page[c] for c in champs},
                                                 "fields": ",".join(champs)}})
    return requetes


def requetes_lettre(document, source, cible, texte):
    """Écrit une nouvelle lettre dans l'onglet cible, avec l'espacement, les marges et les liens de la lettre source."""
    document = document.get("content", document)
    onglet = trouver_onglet(document["tabs"], source)
    if not onglet:
        sys.exit(f"Onglet {source} introuvable")
    paragraphes = [e["paragraph"] for e in onglet["documentTab"]["body"]["content"] if "paragraph" in e]
    blocs = [b.strip().replace("\n", "\u000b") for b in texte.strip().split("\n\n") if b.strip()]
    contenu = "\n".join(blocs)
    fin = 1 + len(contenu.encode("utf-16-le")) // 2
    plage = {"startIndex": 1, "endIndex": fin + 1, "tabId": cible}
    style = {k: v for k, v in paragraphes[0]["paragraphStyle"].items() if k not in ("headingId", "direction", "tabStops", "namedStyleType")}
    requetes = [{"insertText": {"location": {"index": 1, "tabId": cible}, "text": contenu}}]
    if style:
        requetes.append({"updateParagraphStyle": {"range": plage, "paragraphStyle": style, "fields": ",".join(style)}})
    # Les morceaux de texte qui portent un lien dans la lettre source (ex. LinkedIn) gardent leur lien
    for p in paragraphes:
        for m in p["elements"]:
            morceau = m.get("textRun", {})
            if morceau.get("textStyle", {}).get("link") and morceau["content"].strip() in contenu:
                debut = 1 + len(contenu[:contenu.index(morceau["content"].strip())].encode("utf-16-le")) // 2
                longueur = len(morceau["content"].strip().encode("utf-16-le")) // 2
                requetes.append({"updateTextStyle": {"range": {"startIndex": debut, "endIndex": debut + longueur, "tabId": cible},
                                                     "textStyle": morceau["textStyle"], "fields": ",".join(morceau["textStyle"])}})
    page = onglet["documentTab"].get("documentStyle", {})
    champs = [c for c in ("marginTop", "marginBottom", "marginLeft", "marginRight", "pageSize") if c in page]
    if champs:
        requetes.append({"updateDocumentStyle": {"tabId": cible, "documentStyle": {c: page[c] for c in champs}, "fields": ",".join(champs)}})
    return requetes


def appel_file(donnees=None):
    """Lit (sans données) ou modifie (avec données) la file d'attente du script Google Sheet."""
    cles = {}
    chemin = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(chemin):
        for ligne in open(chemin, encoding="utf-8"):
            if "=" in ligne and not ligne.startswith("#"):
                cle, valeur = ligne.split("=", 1)
                cles[cle.strip()] = valeur.strip()
    adresse, mot_de_passe = cles.get("SHEET_ADRESSE"), cles.get("SHEET_CLE")
    if not adresse or not mot_de_passe:
        sys.exit("Ajoute SHEET_ADRESSE et SHEET_CLE dans le fichier .env")
    donnees = donnees or {"action": "file"}  # tout passe en POST : la clé n'apparaît jamais dans l'adresse
    requete = urllib.request.Request(adresse, data=json.dumps({"cle": mot_de_passe, **donnees}).encode(), method="POST")
    with urllib.request.urlopen(requete, timeout=60) as reponse:
        return json.loads(reponse.read().decode())


def texte_annonce(lien):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        navigateur = p.chromium.launch()
        page = navigateur.new_page(user_agent="Mozilla/5.0 (compatible; veille-emploi-personnelle)")
        page.goto(lien, timeout=60000, wait_until="load")
        page.wait_for_timeout(5000)  # laisse le JavaScript afficher l'annonce
        texte = page.locator("body").inner_text()
        navigateur.close()
    return texte


if __name__ == "__main__":
    commande = sys.argv[1] if len(sys.argv) > 1 else ""
    if commande == "file":
        resultat = appel_file()
        if "file" not in resultat:  # mot de passe refusé, ou ancienne version du script Google
            sys.exit(f"File d'attente illisible : {resultat.get('erreur', 'le script Google n est pas à jour (nouvelle version à déployer)')}")
        print(json.dumps(resultat["file"], ensure_ascii=False, indent=1))
    elif commande == "maj" and len(sys.argv) >= 4:
        valeurs = dict(zip(["Etat", "CV", "Lettre", "Note"], sys.argv[3:]))
        print(appel_file({"action": "maj_file", "lien": sys.argv[2], "valeurs": valeurs}))
    elif commande == "idees" and len(sys.argv) == 3:
        with open(sys.argv[2], encoding="utf-8") as fichier:
            print(appel_file({"action": "ajouter_activites", "activites": json.load(fichier)}))
    elif commande == "lettre" and len(sys.argv) == 6:
        with open(sys.argv[2], encoding="utf-8") as fichier:
            document = json.load(fichier)
        with open(sys.argv[5], encoding="utf-8") as fichier:
            texte = fichier.read()
        print(json.dumps(requetes_lettre(document, sys.argv[3], sys.argv[4], texte), ensure_ascii=False, separators=(",", ":")))
    elif commande == "annonce" and len(sys.argv) == 3:
        print(texte_annonce(sys.argv[2]))
    elif commande in ("dernier", "copier") and len(sys.argv) >= 3:
        with open(sys.argv[2], encoding="utf-8") as fichier:
            document = json.load(fichier)
        if commande == "dernier":
            dernier = document.get("content", document)["tabs"][-1]["tabProperties"]
            print(dernier["tabId"], dernier["title"], document.get("content", document)["revisionId"])
        elif len(sys.argv) == 5:
            print(json.dumps(requetes_copie(document, sys.argv[3], sys.argv[4]), ensure_ascii=False, separators=(",", ":")))
        else:
            sys.exit(__doc__)
    else:
        sys.exit(__doc__)
