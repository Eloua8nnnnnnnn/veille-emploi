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
Les sites carrières officiels de chaque compagnie. Pour chacune, identifie la page carrières et la meilleure façon légale d'en récupérer les offres. Si une page ne peut pas être consultée automatiquement, signale-le-moi plutôt que de contourner une protection.

---

## Volet 2 : startups et scale-ups

### Postes recherchés
Chief of Staff, bras droit du CEO, chargé de projets stratégiques auprès de la direction générale, au sein d'une startup ou d'une scale-up.

### Mots-clés à cibler
"Chief of Staff", "Bras droit CEO", "CEO Office", "Chief of Staff / Assistant", "Project Manager Strategy", "Chef de projet transformation"

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
- N'utilise que des sources légales et accessibles. Si une source ne peut pas être consultée automatiquement, signale-le-moi.

### Droit de travailler
Je n'ai pas de visa de travail hors de l'Union européenne. Écarte les offres qui exigent explicitement la nationalité du pays ou un visa déjà obtenu (par exemple « US citizen / visa only »). Si l'annonce indique que l'entreprise parraine les visas, signale-le.

---

## Volet 3 : startups à contacter

### Objectif
Beaucoup de postes de Chief of Staff ne sont jamais publiés. Ce volet repère les startups qui sont au bon moment pour recruter un bras droit, afin que je puisse écrire directement à leur dirigeant, même sans offre publiée.

### Sources des levées de fonds
- **France** : le bilan hebdomadaire des levées de fonds publié par Maddyness.
- **Asie du Sud-Est** : DealStreetAsia et Tech in Asia, qui couvrent les levées de fonds de la région.
- **Inde** : les récapitulatifs de levées de fonds publiés par la presse spécialisée indienne.
- **Moyen-Orient** : Wamda, qui publie chaque mois le bilan des levées de fonds de la région.
- **États-Unis** : les startups Y Combinator ayant annoncé une levée récente.

### Critères de sélection
- Levée de fonds annoncée dans les 12 derniers mois.
- Stade de financement : de l'amorçage (seed) à la série B. Écarte les séries C et au-delà, ainsi que les entreprises sans aucune levée.
- Taille : entre 15 et 200 salariés quand l'information est disponible.
- Nombre d'offres d'emploi ouvertes : plus il est élevé, plus l'entreprise est en croissance. Indique ce nombre quand tu peux le trouver.
- Mêmes zones géographiques que le volet 2.

### Informations à afficher pour chaque startup
- Nom, pays et ville
- Secteur et description en une phrase
- Montant, stade et date de la dernière levée
- Taille de l'équipe, si disponible
- Nombre d'offres d'emploi ouvertes, si disponible
- Nom du dirigeant, uniquement s'il figure dans l'annonce de la levée
- Lien vers le site de l'entreprise et vers l'article annonçant la levée

---

## Critères communs
- Types de contrats : CDI et CDD en priorité. Les stages sont acceptés mais secondaires : affiche-les après les CDI/CDD et signale-les clairement. Écarte les autres types de contrats.
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
- Trois onglets : compagnies aériennes / offres en startup / startups à contacter.
- Dans l'onglet « startups à contacter », trier par date de levée (les plus récentes en premier) et permettre de marquer une startup comme « contactée ».
- Filtres : pays, entreprise, type de contrat, niveau d'expérience.
- Tri par date de publication, les plus récentes en premier.
- Mettre en évidence les offres apparues depuis la dernière mise à jour.
- Stages affichés après les CDI/CDD et clairement identifiés.
- Section Afrique séparée dans le volet startups.
- Possibilité de marquer une offre comme « vue », « intéressante » ou « candidature envoyée » (enregistré dans mon navigateur).
- Afficher la date de la dernière mise à jour.

## Règles à respecter
- Les clés et mots de passe sont stockés dans un fichier `.env` en local et dans les secrets GitHub en ligne. Ne jamais les écrire en clair dans le code.
- Le fichier `.env` doit toujours figurer dans `.gitignore`. Vérifie-le avant toute publication sur GitHub.
- Ne jamais extraire automatiquement de pages LinkedIn ou de sites qui l'interdisent dans leurs conditions d'utilisation.
- Demande-moi avant d'installer une nouvelle bibliothèque ou de publier quoi que ce soit.
- Garde le code simple et lisible, en un minimum de fichiers.
- Après chaque modification importante, propose un test pour vérifier que tout fonctionne.
