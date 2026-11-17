# Bilan des sites carrières des compagnies aériennes

Tests faits le 23 octobre 2026 : accès à la page, présence d'une protection anti-robot, règles du fichier robots.txt (les consignes que chaque site donne aux robots).

## ✅ Lisibles automatiquement (11)

| Compagnie | Page carrières | Méthode | Remarque |
|---|---|---|---|
| Etihad Airways | careers.etihad.com | Interface officielle SmartRecruiters (api.smartrecruiters.com) | La meilleure : 104 offres, données propres. Déjà des postes « Technical Product Delivery Manager », « Data Analytics Officer » |
| Lufthansa | lufthansagroup.careers | Interface publique du site (api.lufthansagroup.careers) | robots.txt autorise tout |
| Cathay Pacific | careers.cathaypacific.com/en/careers/jobs | Lecture de la page | Le site a un filtre « sponsorship » (visa parrainé) 👍 |
| Singapore Airlines | careers.singaporeair.com | Lecture de la page (outil SuccessFactors) | |
| Qatar Airways | careers.qatarairways.com/global/SearchJobs | Lecture de la page (outil Avature) | |
| Air New Zealand | careers.airnewzealand.co.nz/jobs | Lecture de la page | robots.txt interdit les adresses de recherche avec filtres : on lira la liste principale seulement |
| Emirates | emiratesgroupcareers.com/search-and-apply | Lecture de la page | robots.txt interdit la recherche par mot-clé et les pages suivantes : on ne lira que la 1re page → couverture partielle |
| China Eastern | job.ceair.com | Lecture de la page | En chinois : Claude traduira |
| Korean Air | koreanair.recruiter.co.kr | À approfondir | Page construite dynamiquement, en coréen |
| Air Tahiti Nui | airtahitinui.com/en/our-jobs | À approfondir | Peu d'offres, page simple |
| SAS | sasgroup.net/career | À approfondir | Page lisible, mais la liste d'offres n'a pas encore été localisée |

## ⛔ Protégés contre les robots (7) — on ne contourne pas

| Compagnie | Ce qui bloque |
|---|---|
| Air Tahiti | Protection Cloudflare (accès refusé) |
| Qantas | Protection Cloudflare (la page ne répond pas aux robots) |
| Delta Air Lines | Protection anti-robot sur delta.avature.net |
| TAP Portugal | Protection Cloudflare, page carrières introuvable |
| EVA Air | Accès refusé (erreur 403) |
| Vietnam Airlines | Connexion obligatoire + captcha |
| Starlux Airlines | Page carrières introuvable, captcha |

**Solutions légales pour ces 7 compagnies :**
1. Adzuna (prévu dans le volet 2) regroupe des offres de nombreux sites : on y cherchera aussi ces compagnies.
2. Créer vous-même une alerte e-mail sur leur site carrières, quand elles en proposent.

## Limite de ce bilan
J'ai vérifié les fichiers robots.txt, pas encore les conditions d'utilisation complètes de chaque site. Je le ferai pour chaque compagnie au moment d'écrire le code qui la lit.
