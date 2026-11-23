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

Autorisations reçues par e-mail (lecture quotidienne, usage personnel, aucune rediffusion) :
- **Cathay Pacific** (20/11/2026) : careers.cathaypacific.com, une fois par jour au maximum.
- **Qantas** (20/11/2026) : accord pour careers.qantas.com. Ce site est protégé par Akamai, qui ignore le robot, mais il affiche les mêmes offres que le tableau SmartRecruiters de Qantas : le robot lit donc l'interface publique SmartRecruiters (code `QantasGroup`), une fois par jour.
- **TAP Air Portugal** (20/11/2026) : recrutamento.tap.pt, une fois par jour, sans gêner le site, informations publiques uniquement, aucune rediffusion.
- **Korean Air** (20/11/2026) : recruit.koreanair.com, une fois par jour, sans surcharger le site, offres publiques uniquement, aucune rediffusion. Le site ne publie que quelques campagnes en coréen ; Claude les juge toutes.
- **STARLUX Airlines** (20/11/2026) : careers.jx-starlux.com (interface publique du site), une fois par jour.
- **SAS** (20/11/2026) : careers.sasgroup.net, une fois par jour, sans trafic excessif.
- **Vietnam Airlines** (20/11/2026) : annonces publiques de vietnamairlines.com (« Career with us »), une fois par jour. Le portail tuyendung.vietnamairlines.com exige une connexion : non lu (contraire à leurs conditions).
- **China Eastern** (20/11/2026) : job.ceair.com, rubriques publiques (recrutement confirmé et campus), une fois par jour. Annonces en chinois, triées sur des mots chinois.
- **EVA Air** et **Delta Air Lines** (20/11/2026) : accord, mais leurs sites bloquent le robot (Akamai pour EVA, défi anti-robot AWS pour Delta) et leurs conditions interdisent de contourner ces protections. Non lus.
- **Air Tahiti** : accord du service recrutement, mais le site bloque le robot (Cloudflare). Non lu tant qu'Air Tahiti n'a pas laissé passer le robot.

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
- **États-Unis** : les offres publiques de Y Combinator (ycombinator.com/jobs ; Work at a Startup bloque les robots).
- **Fonds d'investissement** : les job boards publics (Getro) de Accel, General Catalyst, Insight, Khosla, Thrive, Craft, Techstars, Antler (Asie du Sud-Est) et MEVP (Moyen-Orient), limités aux startups jusqu'à la série C. Les fonds sur Consider (Peak XV, Monk's Hill, a16z, Sequoia…) ne sont pas encore lus. Aussi : le fil mensuel « Who is hiring? » de Hacker News.
- **LinkedIn** (partout) : recherche publique sans connexion, offres de la semaine, « Chief of Staff / Founder's Associate / Founder's Office » et « Strategy & Operations / Business Operations », à Singapour, Hong Kong, Dubaï, Abu Dhabi, Riyad, Tokyo, Séoul, Jakarta, Bangalore, New York, San Francisco, Londres, Berlin, Munich, Stockholm, Barcelone, Paris et Amsterdam. Une pause entre chaque requête ; si LinkedIn freine le robot, il s'arrête pour la journée. Claude ne garde que les startups et scale-ups.
- **France** : les sites carrières des entreprises de la promotion en cours du French Tech Next40/120. Le robot lit les 53 entreprises (sur 120, promotion 2026) dont l'outil de recrutement a une interface publique (Lever, Ashby, Greenhouse, Teamtailor, Workable, Recruitee, SmartRecruiters). Les autres utilisent Welcome to the Jungle (lu par la recherche WTTJ ci-dessous) ou leur propre site.
- **Asie et Moyen-Orient** : Tech in Asia refuse tout ce qui n'est pas un vrai navigateur (non lu). Le robot lit à la place une liste de scale-ups (Grab, Airwallex, Coupang, Careem, Tamara…) dont l'outil de recrutement a une interface publique.
- **Afrique** : une liste de scale-ups africaines (Jumia, Moniepoint, M-KOPA, Kuda, Yassir…) lues de la même façon.
- **Welcome to the Jungle** (France et étranger) : moteur de recherche public du site, offres des 30 derniers jours, entreprises de 3 000 salariés au plus (Chief of Staff, Founder's Associate, bras droit, CEO office, Strategy & Operations, Business Operations, chargé de mission direction générale).
- **Adzuna** : abandonné le 21/11/2026 (la clé gratuite ne donne que 25 appels d'essai ; l'accès quotidien est payant).
- **Alertes e-mail** : le robot lit en lecture seule (Gmail, IMAP) les alertes emploi reçues ces 4 derniers jours (LinkedIn, Welcome to the Jungle, sites carrières…). Claude en extrait les offres et choisit l'onglet. Le robot ne visite pas les sites d'origine.
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
- VIE en Europe : écartés, sauf si le poste me correspond très bien (score de Claude d'au moins 7/10). Les pays nordiques (Suède, Norvège, Danemark, Finlande, Islande) ne sont pas concernés. Ils restent repêchables dans « Écartées par Claude ».
- Autres sources : à définir.

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
- Griser les offres publiées depuis plus de 30 jours, et ne plus afficher (ni analyser) celles publiées depuis plus de 60 jours.
- À chaque mise à jour, vérifier si les offres sont toujours en ligne et retirer du tableau de bord celles qui ne le sont plus.

## Tableau de bord
- **Dashboard personnel** (`docs/app.html`, en construction) : page d'accueil « Aujourd'hui » en tuiles et un module par page (emploi, social, santé, vêtements, recettes). Il est servi par le script Google du Sheet, avec un accès réservé à mon compte Google. Ses données personnelles restent dans le Google Sheet et ne vont jamais dans le dépôt public. Claude y accède par une entrée protégée par une clé (`SHEET_CLE` dans `.env`, propriété `MOT_DE_PASSE` du script).
- **Ma journée** (accueil du dashboard) : une liste fixe d'habitudes cochée chaque soir (avec « Hier » pour cocher après minuit, séries et 14 derniers jours), et une liste « À ne pas oublier » de tâches ponctuelles. Onglets « Habitudes », « Journal » et « Tâches » du Google Sheet.
- **Social** : trois onglets pleine largeur. **Personnes** : une carte par personne, avec l'activité à faire ensemble, un rappel (« juste y penser » ou une fréquence) et les sorties prévues avec elle. **Sorties** : idées à Paris par catégorie, chacune pouvant être liée à une personne (« Avec qui ? »). Onglet **Théâtre** dans les sorties : pièces à voir, recommandations de Claude (avec « Pas pour moi », jamais reproposées) et pièces vues notées de 1 à 5 étoiles (onglet « Théâtre » du Google Sheet). Onglets « Contacts » et « Activités » du Google Sheet. Chaque lundi, une tâche Claude ajoute 6 à 8 idées tirées du programme officiel « Que faire à Paris » (opendata.paris.fr), plus 2 à 4 soirées (agendas publics) : jamais de techno ni d'électro (je n'aime pas) ; les événements passés disparaissent d'eux-mêmes.
- Tableau de bord des offres (`docs/index.html`, ci-dessous) : affiché dans le module Emploi du dashboard.
- Une seule page web simple, lisible sur ordinateur et sur téléphone.
- Quatre onglets : compagnies aériennes / offres en startup / offres autres / mes candidatures.
- L'onglet « mes candidatures » lit et modifie mon Google Sheet de suivi (script Google Apps Script, voir `google_sheet_script.js`).
- Les offres écartées par Claude sont dans une section repliée, avec un bouton pour les remettre dans la liste.
- Filtres : pays, métier (product management / Chief of Staff et autres), type de contrat, niveau d'expérience.
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
