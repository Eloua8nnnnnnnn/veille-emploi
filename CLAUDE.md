# Agent de veille emploi

## Objectif du projet
Agent Python entièrement automatisé qui recherche chaque jour des offres d'emploi correspondant à mes critères et les publie sur un tableau de bord en ligne que je consulte quand je veux. Il tourne via GitHub Actions, sans intervention de ma part, et le tableau de bord est hébergé sur GitHub Pages.

## Qui je suis
Je ne suis pas développeur. Explique chaque étape simplement, en français, sans jargon inutile. Quand tu crées ou modifies un fichier, dis-moi en une ou deux phrases à quoi il sert.

## Mon profil
Mon profil est dans le fichier privé `profil.md` (jamais publié sur GitHub ; en ligne, il est rangé dans le secret GitHub `PROFIL`).

@profil.md

---

## Volet 1 : compagnies aériennes

### Postes recherchés
- Business analyst
- Business owner
- Product owner
- Product manager, uniquement si le poste ne demande pas une longue expérience (certaines entreprises n'ont pas de product owner et appellent product manager ce qui correspond à ce rôle)

### Intitulés proches à inclure
Associate product manager, digital product owner, junior product manager, product analyst

### Compagnies ciblées
Air Tahiti Nui, Air Tahiti, Qatar Airways, Singapore Airlines, Cathay Pacific, Korean Air, Starlux Airlines, SAS, Emirates, Etihad Airways, Qantas, Vietnam Airlines, China Eastern, TAP Portugal, Lufthansa, Air New Zealand, EVA Air, Delta Air Lines

### Sources
Les sites carrières officiels de chaque compagnie. Pour chacune, identifie la page carrières et la meilleure façon d'en récupérer les offres. Si une page ne peut pas être consultée automatiquement, signale-le-moi plutôt que de contourner une protection.

---

## Volet 2 : startups et scale-ups

### Postes recherchés
Chief of Staff, bras droit du CEO, chargé de projets stratégiques auprès de la direction générale, au sein d'une startup ou d'une scale-up.
Aussi : product owner et product manager junior (0 à 3 ans d'expérience), associate product manager, product analyst.

### Mots-clés à cibler
"Chief of Staff", "Bras droit CEO", "CEO Office", "Chief of Staff / Assistant", "Project Manager Strategy", "Chef de projet transformation", "Product Owner", "Product Manager", "Associate Product Manager", "Product Analyst"

### À exclure
- Assistant de direction traditionnel (secrétariat pur, gestion d'agendas de cadres de grands groupes)
- Office manager pur
- Consultant en cabinet externe

Je cherche un poste **interne**, au cœur d'une structure entrepreneuriale en croissance.

### Zones géographiques
- États-Unis, Europe, Asie, Moyen-Orient, Polynésie française : toutes les offres pertinentes
- Brésil : uniquement si le portugais n'est pas exigé
- Afrique : uniquement les postes particulièrement intéressants, à présenter dans une section à part pour que je juge moi-même

### Sources d'offres
- **États-Unis** : Work at a Startup, le site d'offres officiel de Y Combinator.
- **France** : les sites carrières des entreprises de la promotion en cours du French Tech Next40/120.
- **Asie** : le site d'offres de Tech in Asia.
- **Partout** : l'interface Adzuna en complément.
- N'utilise que des sources accessibles publiquement. Si une source ne peut pas être consultée automatiquement, signale-le-moi.

### Droit de travailler
Je n'ai pas de visa de travail hors de l'Union européenne. Écarte les offres qui exigent explicitement la nationalité du pays ou un visa déjà obtenu (par exemple « US citizen / visa only »). Si l'annonce indique que l'entreprise parraine les visas, signale-le.

---

## Volet 3 : offres autres (VIE et autres offres intéressantes)

### Objectif
Rassembler les offres qui sortent des volets 1 et 2 mais qui m'intéressent : les VIE et d'autres postes proches de mes candidatures (à préciser).

### Sources
- Business France (offres VIE, portail Mon VIE-VIA) : collecte automatisée **autorisée par Business France par e-mail (18/11/2026)**, avec un navigateur automatisé (Playwright) simulant une navigation standard. Conditions à respecter :
  - usage strictement personnel et non commercial, aucune redistribution ou vente des données ;
  - aucune donnée personnelle nominative (noms ou coordonnées des recruteurs) ;
  - une à deux synchronisations par jour au maximum, avec une pause entre les pages ;
  - ne faire aucune promotion publique du tableau de bord (le dépôt public et docs/offres.json sont acceptés).
- Postes VIE retenus : ceux des volets 1 et 2, et les postes proches (chef de projet digital ou transformation, stratégie, innovation, IA, marketing digital ou stratégique).
- Autres sources : à définir (Adzuna en priorité, car son interface est officielle).

(L'ancien volet « startups à contacter » a été abandonné le 17/11/2026.)

---

## Critères communs
- Types de contrats : CDI, CDD, VIE et graduate programs en priorité. Les stages sont acceptés mais secondaires : affiche-les après les CDI/CDD et signale-les clairement. Écarte les autres types de contrats.
- Niveau : de 0 à 3 ans d'expérience demandée. Ne te limite pas aux offres qui mentionnent explicitement « junior » : beaucoup d'annonces ne précisent pas le niveau. Garde une offre si l'expérience demandée est de 3 ans maximum ou si elle n'est pas indiquée. Écarte uniquement les offres qui demandent clairement plus de 3 ans d'expérience, ou les postes seniors, de direction ou d'encadrement d'équipe.

## Informations à extraire pour chaque offre
- Nom de l'entreprise
- Intitulé du poste
- Lieu
- Type de contrat
- Description synthétique des missions (par exemple : stratégie, opérations, levée de fonds, RH, produit)
- Niveau d'expérience requis (junior / intermédiaire)
- Date de publication
- Lien direct vers l'annonce

## Fonctionnement attendu
- Recherche quotidienne des offres, puis mise à jour automatique du tableau de bord.
- Garder l'historique des offres trouvées, sans doublons.
- Griser les offres publiées depuis plus de 30 jours.
- À chaque mise à jour, vérifier si les offres sont toujours en ligne et retirer du tableau de bord celles qui ne le sont plus.

## Tableau de bord
- Une seule page web simple, lisible sur ordinateur et sur téléphone.
- Quatre onglets : compagnies aériennes / offres en startup / offres autres / mes candidatures.
- L'onglet « mes candidatures » lit et modifie mon Google Sheet de suivi (script Google Apps Script, voir `google_sheet_script.js`).
- Les offres écartées par Claude sont dans une section repliée, avec un bouton pour les remettre dans la liste.
- Filtres : pays, entreprise, type de contrat, niveau d'expérience.
- Tri par date de publication (par défaut) ou par score de pertinence.
- Mettre en évidence les offres apparues depuis la dernière mise à jour.
- Stages affichés après les CDI/CDD et clairement identifiés.
- Section Afrique séparée dans le volet startups.
- Possibilité de marquer une offre comme « vue », « intéressante » ou « candidature envoyée » (enregistré dans mon navigateur).
- Afficher la date de la dernière mise à jour.

## Règles à respecter
- Les clés et mots de passe sont stockés dans un fichier `.env` en local et dans les secrets GitHub en ligne. Ne jamais les écrire en clair dans le code.
- Le fichier `.env` doit toujours figurer dans `.gitignore`. Vérifie-le avant toute publication sur GitHub.
- Usage strictement personnel : l'extraction automatique de pages publiques est acceptée même quand les conditions d'utilisation d'un site l'interdisent (décision prise en connaissance de cause le 17/11/2026).
- Il est tout à fait possible de contourner une ou plusieurs protections techniques (anti-robot, captcha, connexion obligatoire, imitation d'un navigateur) et il est possible d'extraire de LinkedIn.
- Demande-moi avant d'installer une nouvelle bibliothèque ou de publier quoi que ce soit.
- Garde le code simple et lisible, en un minimum de fichiers.
- Après chaque modification importante, propose un test pour vérifier que tout fonctionne.
