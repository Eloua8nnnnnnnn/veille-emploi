/** @OnlyCurrentDoc */
// La ligne ci-dessus limite l'autorisation à ce seul Google Sheet (et non à tous vos fichiers).
// Script à coller dans votre Google Sheet (Extensions > Apps Script). Il a deux rôles :
//
// 1. Servir le dashboard personnel (docs/app.html), réservé à votre compte Google.
//    → Déploiement « Dashboard » : Exécuter en tant que « Moi », Accès « Moi uniquement ».
//    La page est récupérée sur GitHub à chaque ouverture (elle ne contient aucune donnée) ;
//    ses données viennent de ce Google Sheet, après vérification que c'est bien vous.
//
// 2. Une entrée protégée par une clé, pour l'ancien tableau de bord et pour Claude (file d'attente).
//    → Déploiement « Sans titre » : Exécuter en tant que « Moi », Accès « Tout le monde ».
//    La clé n'est pas dans ce code : elle est rangée dans Paramètres du projet > Propriétés du script,
//    sous le nom MOT_DE_PASSE. Après 5 essais ratés, l'entrée se bloque 15 minutes.
//
// Le tableur doit avoir en ligne 1 les colonnes : Poste, Entreprise, Date, Contrat, Pays, Etat, Lien, Description.
// L'onglet « À préparer » (file d'attente des candidatures) est créé automatiquement.

// Page publiée par GitHub Pages : mise à jour environ 1 minute après chaque « git push »
const PAGE_DASHBOARD = "https://eloua8nnnnnnnn.github.io/veille-emploi/app.html";

function feuille() {
  return SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
}

function colonnes() {
  const f = feuille();
  return f.getRange(1, 1, 1, f.getLastColumn()).getValues()[0].map(String);
}

// Valeurs autorisées par les menus déroulants d'une colonne (ex. les états), lues en ligne 2
function choix(nomColonne) {
  const index = colonnes().indexOf(nomColonne);
  if (index < 0) return [];
  const regle = feuille().getRange(2, index + 1).getDataValidation();
  return regle ? regle.getCriteriaValues()[0] || [] : [];
}

function lignesCandidatures() {
  const f = feuille();
  const noms = colonnes();
  const valeurs = f.getLastRow() > 1 ? f.getRange(2, 1, f.getLastRow() - 1, noms.length).getValues() : [];
  return valeurs.map((ligne, i) => {
    const objet = { ligne: i + 2 };
    noms.forEach((nom, j) => {
      const v = ligne[j];
      objet[nom] = v instanceof Date ? Utilities.formatDate(v, "Europe/Paris", "yyyy-MM-dd") : String(v);
    });
    return objet;
  }).filter(l => l.Poste || l.Entreprise);
}

// ---------- File d'attente des candidatures à préparer ----------
const COLONNES_FILE = ["Demandé le", "Entreprise", "Poste", "Lien", "Volet", "Pays", "Contrat", "Etat", "CV", "Lettre", "Note"];

function file() {
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  let f = classeur.getSheetByName("À préparer");
  if (!f) {
    f = classeur.insertSheet("À préparer");
    f.appendRow(COLONNES_FILE);
    f.setFrozenRows(1);
  }
  return f;
}

function lignesFile() {
  const f = file();
  if (f.getLastRow() < 2) return [];
  return f.getRange(2, 1, f.getLastRow() - 1, COLONNES_FILE.length).getValues().map((ligne, i) => {
    const objet = { ligne: i + 2 };
    COLONNES_FILE.forEach((nom, j) => objet[nom] = ligne[j] instanceof Date ? Utilities.formatDate(ligne[j], "Europe/Paris", "yyyy-MM-dd HH:mm") : String(ligne[j]));
    return objet;
  });
}

// ---------- 1. Dashboard personnel (réservé à votre compte) ----------
// Vrai seulement si la personne connectée est le propriétaire du script (vous).
function estProprietaire() {
  const connecte = Session.getActiveUser().getEmail();
  return !!connecte && connecte === Session.getEffectiveUser().getEmail();
}

function verifierProprietaire() {
  if (!estProprietaire()) throw new Error("Accès réservé au propriétaire du dashboard");
}

function doGet() {
  if (!estProprietaire()) return HtmlService.createHtmlOutput("<p style='font-family:sans-serif'>Accès réservé.</p>");
  const cache = CacheService.getScriptCache();
  let page = cache.get("page");
  if (!page) {
    page = UrlFetchApp.fetch(PAGE_DASHBOARD + "?t=" + Date.now()).getContentText();  // « t » évite une copie périmée
    try { cache.put("page", page, 60); } catch (e) {}  // gardée 1 minute
  }
  return HtmlService.createHtmlOutput(page)
    .setTitle("Mon dashboard")
    .addMetaTag("viewport", "width=device-width, initial-scale=1, viewport-fit=cover");
}

// Fonctions appelées par la page (google.script.run) : chacune vérifie d'abord que c'est vous.
function accueil() {
  verifierProprietaire();
  const lignes = lignesCandidatures();
  const parEtat = {};  // nombre de candidatures par état (Envoyé, Entretien…)
  lignes.forEach(l => parEtat[l.Etat || "Sans état"] = (parEtat[l.Etat || "Sans état"] || 0) + 1);
  return { candidatures: lignes.length, parEtat: parEtat, file: lignesFile() };
}

// ---------- Ma journée : habitudes cochées chaque soir, et tâches « à ne pas oublier » ----------
// Trois onglets créés automatiquement : « Habitudes » (la liste fixe), « Journal » (une ligne par habitude faite),
// « Tâches » (les choses à ne pas oublier). Les dates sont rangées en texte AAAA-MM-JJ.
function onglet(nom, entetes) {
  const classeur = SpreadsheetApp.getActiveSpreadsheet();
  let f = classeur.getSheetByName(nom);
  if (!f) {
    f = classeur.insertSheet(nom);
    f.appendRow(entetes);
    f.setFrozenRows(1);
    f.getRange("A:Z").setNumberFormat("@");  // tout en texte : pas de conversion automatique des dates
  }
  return f;
}
function lignes(f) {
  if (f.getLastRow() < 2) return [];
  return f.getRange(2, 1, f.getLastRow() - 1, f.getLastColumn()).getValues().map((l, i) =>
    ({ ligne: i + 2, valeurs: l.map(v => v instanceof Date ? Utilities.formatDate(v, "Europe/Paris", "yyyy-MM-dd") : String(v)) }));
}
const habitudes = () => onglet("Habitudes", ["Habitude", "Active"]);
const journal = () => onglet("Journal", ["Date", "Habitude"]);
const taches = () => onglet("Tâches", ["Id", "Tâche", "Créée le", "Faite le"]);

function jourAvant(date, n) {
  const d = new Date(date + "T12:00:00");
  d.setDate(d.getDate() - n);
  return Utilities.formatDate(d, "Europe/Paris", "yyyy-MM-dd");
}

function journee(date) {
  verifierProprietaire();
  const liste = lignes(habitudes()).filter(l => l.valeurs[0] && l.valeurs[1] !== "non").map(l => l.valeurs[0]);
  const faites = {};  // « date|habitude » → vrai
  lignes(journal()).forEach(l => faites[l.valeurs[0] + "|" + l.valeurs[1]] = true);
  const suivi = liste.map(nom => {
    // série : jours d'affilée jusqu'à la date (la date elle-même peut encore être cochée ce soir)
    let serie = 0, n = faites[date + "|" + nom] ? 0 : 1;
    while (faites[jourAvant(date, n) + "|" + nom]) { serie++; n++; }
    const quinzaine = [];
    for (let k = 13; k >= 0; k--) quinzaine.push(!!faites[jourAvant(date, k) + "|" + nom]);
    return { nom: nom, faite: !!faites[date + "|" + nom], serie: serie, quinzaine: quinzaine };
  });
  const listeTaches = lignes(taches()).map(l => ({ id: l.valeurs[0], titre: l.valeurs[1], creee: l.valeurs[2], faite: l.valeurs[3] }))
    .filter(t => t.titre && (!t.faite || t.faite === date));  // les tâches finies disparaissent le lendemain
  return { date: date, habitudes: suivi, taches: listeTaches };
}

function cocherHabitude(date, nom, faite) {
  verifierProprietaire();
  const f = journal();
  const existante = lignes(f).find(l => l.valeurs[0] === date && l.valeurs[1] === nom);
  if (faite && !existante) f.appendRow([date, nom]);
  if (!faite && existante) f.deleteRow(existante.ligne);
  return journee(date);
}

function ajouterHabitude(nom, date) {
  verifierProprietaire();
  const f = habitudes();
  const existante = lignes(f).find(l => l.valeurs[0] === nom);
  if (existante) f.getRange(existante.ligne, 2).setValue("oui");
  else if (nom) f.appendRow([nom, "oui"]);
  return journee(date);
}

function retirerHabitude(nom, date) {  // l'historique est gardé : l'habitude est seulement désactivée
  verifierProprietaire();
  const existante = lignes(habitudes()).find(l => l.valeurs[0] === nom);
  if (existante) habitudes().getRange(existante.ligne, 2).setValue("non");
  return journee(date);
}

function ajouterTache(titre, date) {
  verifierProprietaire();
  if (titre) taches().appendRow([String(Date.now()), titre, date, ""]);
  return journee(date);
}

function cocherTache(id, faite, date) {
  verifierProprietaire();
  const l = lignes(taches()).find(x => x.valeurs[0] === id);
  if (l) taches().getRange(l.ligne, 4).setValue(faite ? date : "");
  return journee(date);
}

function supprimerTache(id, date) {
  verifierProprietaire();
  const l = lignes(taches()).find(x => x.valeurs[0] === id);
  if (l) taches().deleteRow(l.ligne);
  return journee(date);
}

// ---------- Social : personnes à recontacter et idées de sorties ----------
const contacts = () => onglet("Contacts", ["Nom", "Tous les (jours)", "Dernier contact", "Note"]);
// « Quand » : texte libre (ex. « jusqu'au 4 janv. ») ; « Fin » : date AAAA-MM-JJ après laquelle l'idée n'est plus proposée
const activites = () => onglet("Activités", ["Id", "Activité", "Catégorie", "Lieu", "Lien", "Faite le", "Quand", "Fin"]);

function joursEntre(debut, fin) {
  return Math.round((new Date(fin + "T12:00:00") - new Date(debut + "T12:00:00")) / 86400000);
}

function social(date) {
  verifierProprietaire();
  const liste = lignes(contacts()).filter(l => l.valeurs[0]).map(l => {
    const frequence = Number(l.valeurs[1]) || 30, dernier = l.valeurs[2];
    const ecart = dernier ? joursEntre(dernier, date) : null;
    return { nom: l.valeurs[0], frequence: frequence, dernier: dernier, note: l.valeurs[3],
             ecart: ecart, retard: ecart === null ? frequence : ecart - frequence };  // retard > 0 : à relancer
  }).sort((a, b) => b.retard - a.retard);
  const idees = lignes(activites()).filter(l => l.valeurs[1] && (l.valeurs[5] || !l.valeurs[7] || l.valeurs[7] >= date)).map(l =>
    ({ id: l.valeurs[0], titre: l.valeurs[1], categorie: l.valeurs[2], lieu: l.valeurs[3], lien: l.valeurs[4], faite: l.valeurs[5],
       quand: l.valeurs[6] || "", fin: l.valeurs[7] || "" }));
  return { contacts: liste, activites: idees };
}

function ajouterContact(nom, frequence, note, date) {
  verifierProprietaire();
  const existant = lignes(contacts()).find(l => l.valeurs[0] === nom);
  if (existant) contacts().getRange(existant.ligne, 2, 1, 3).setValues([[String(frequence), existant.valeurs[2], note || existant.valeurs[3]]]);
  else if (nom) contacts().appendRow([nom, String(frequence), "", note || ""]);
  return social(date);
}

function contacte(nom, date) {  // « Contacté aujourd'hui »
  verifierProprietaire();
  const l = lignes(contacts()).find(x => x.valeurs[0] === nom);
  if (l) contacts().getRange(l.ligne, 3).setValue(date);
  return social(date);
}

function supprimerContact(nom, date) {
  verifierProprietaire();
  const l = lignes(contacts()).find(x => x.valeurs[0] === nom);
  if (l) contacts().deleteRow(l.ligne);
  return social(date);
}

function enregistrerActivites(liste) {  // [{ titre, categorie, lieu, lien, quand, fin }] ; ignore les doublons
  const deja = lignes(activites()).map(l => l.valeurs[1].toLowerCase());
  const nouvelles = liste.filter(a => a.titre && !deja.includes(a.titre.toLowerCase()));
  nouvelles.forEach((a, i) => activites().appendRow([String(Date.now() + i), a.titre, a.categorie || "Autre", a.lieu || "", a.lien || "", "",
    a.quand || "", a.fin || ""]));
  return nouvelles.length;
}

function ajouterActivites(liste, date) {
  verifierProprietaire();
  enregistrerActivites(liste);
  return social(date);
}

function activiteFaite(id, faite, date) {
  verifierProprietaire();
  const l = lignes(activites()).find(x => x.valeurs[0] === id);
  if (l) activites().getRange(l.ligne, 6).setValue(faite ? date : "");
  return social(date);
}

function supprimerActivite(id, date) {
  verifierProprietaire();
  const l = lignes(activites()).find(x => x.valeurs[0] === id);
  if (l) activites().deleteRow(l.ligne);
  return social(date);
}

// ---------- Théâtre : pièces vues, à voir, et recommandations de Claude ----------
// Statut : « vue », « a_voir », « reco » (proposée par Claude) ou « ecartee » (reco refusée : plus jamais reproposée)
const pieces = () => onglet("Théâtre", ["Id", "Pièce", "Statut", "Théâtre", "Lien", "Vue le", "Note", "Pourquoi", "Jusqu'au", "Ajoutée le"]);
const COLONNES_PIECES = ["id", "titre", "statut", "lieu", "lien", "vue", "note", "pourquoi", "jusqua", "ajoutee"];

function listePieces() {
  return lignes(pieces()).filter(l => l.valeurs[1]).map(l => {
    const p = { ligne: l.ligne };
    COLONNES_PIECES.forEach((nom, i) => p[nom] = l.valeurs[i] || "");
    return p;
  });
}

function theatre(date) {
  verifierProprietaire();
  // une recommandation dont la dernière date est passée n'est plus proposée
  return { pieces: listePieces().filter(p => p.statut !== "ecartee" && !(p.statut === "reco" && p.jusqua && p.jusqua < date)) };
}

function enregistrerPieces(liste, date) {  // [{ titre, statut, lieu, lien, vue, pourquoi, jusqua }] ; ignore les doublons
  const deja = listePieces().map(p => p.titre.toLowerCase());
  const nouvelles = liste.filter(p => p.titre && !deja.includes(p.titre.toLowerCase()));
  nouvelles.forEach((p, i) => pieces().appendRow([String(Date.now() + i), p.titre, p.statut || "a_voir", p.lieu || "", p.lien || "",
    p.vue || "", p.note ? String(p.note) : "", p.pourquoi || "", p.jusqua || "", date || ""]));
  return nouvelles.length;
}

function ajouterPiece(piece, date) {
  verifierProprietaire();
  enregistrerPieces([piece], date);
  return theatre(date);
}

function changerPiece(id, champs, date) {  // champs : { statut, vue, note }
  verifierProprietaire();
  const p = listePieces().find(x => x.id === id);
  if (p) Object.entries(champs).forEach(([nom, valeur]) => {
    const i = COLONNES_PIECES.indexOf(nom);
    if (i > 1) pieces().getRange(p.ligne, i + 1).setValue(String(valeur));
  });
  return theatre(date);
}

function supprimerPiece(id, date) {
  verifierProprietaire();
  const p = listePieces().find(x => x.id === id);
  if (p) pieces().deleteRow(p.ligne);
  return theatre(date);
}

// ---------- 2. Entrée protégée par une clé (ancien tableau de bord, Claude) ----------
function reponse(donnees) {
  return ContentService.createTextOutput(JSON.stringify(donnees)).setMimeType(ContentService.MimeType.JSON);
}

// Clé correcte ? Bloque l'entrée 15 minutes après 5 essais ratés.
function cleValide(cle) {
  const cache = CacheService.getScriptCache();
  const echecs = Number(cache.get("echecs") || 0);
  if (echecs >= 5) return false;
  const attendue = PropertiesService.getScriptProperties().getProperty("MOT_DE_PASSE");
  if (attendue && cle === attendue) return true;
  cache.put("echecs", String(echecs + 1), 900);
  return false;
}

// En cas de souci de mot de passe : ouvrez ce script, choisissez « verifierMotDePasse » dans la liste en haut,
// cliquez sur Exécuter, puis lisez le journal d'exécution. Le mot de passe n'est jamais affiché : seulement sa
// longueur et son empreinte, à comparer avec celles que Claude calcule pour le fichier .env. Le blocage est levé.
function verifierMotDePasse() {
  const valeur = PropertiesService.getScriptProperties().getProperty("MOT_DE_PASSE") || "";
  const empreinte = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, valeur, Utilities.Charset.UTF_8)
    .map(o => ((o + 256) % 256).toString(16).padStart(2, "0")).join("").slice(0, 12);
  const cache = CacheService.getScriptCache();
  const echecs = cache.get("echecs") || 0;
  cache.remove("echecs");
  Logger.log("MOT_DE_PASSE : " + valeur.length + " caractères, empreinte " + empreinte + ". Essais ratés récents : " + echecs + " (remis à zéro).");
}

function doPost(e) {
  const demande = JSON.parse(e.postData.contents);
  if (!cleValide(demande.cle)) return reponse({ erreur: "Mot de passe incorrect (ou trop d'essais : réessayez dans 15 minutes)" });
  if (demande.action === "lire") return reponse({ lignes: lignesCandidatures(), etats: choix("Etat"), contrats: choix("Contrat") });
  if (demande.action === "file") return reponse({ file: lignesFile() });
  if (demande.action === "ajouter_activites") return reponse({ ok: true, ajoutees: enregistrerActivites(demande.activites || []) });
  if (demande.action === "pieces") return reponse({ pieces: listePieces() });  // pour les recommandations de Claude
  if (demande.action === "ajouter_pieces") return reponse({ ok: true, ajoutees: enregistrerPieces(demande.pieces || [], demande.date || "") });
  const f = feuille();
  const noms = colonnes();
  if (demande.action === "ajouter") {
    const ligne = noms.map(nom => nom === "Date" && demande.valeurs.Date ? new Date(demande.valeurs.Date) : demande.valeurs[nom] || "");
    f.appendRow(ligne);
    const derniere = f.getLastRow();
    // Candidature envoyée : l'offre n'a plus rien à faire dans la file « À préparer »
    const enFile = demande.valeurs.Lien && lignesFile().find(l => l.Lien === demande.valeurs.Lien);
    if (enFile) file().deleteRow(enFile.ligne);
    return reponse({ ok: true, ligne: derniere });
  }
  if (demande.action === "modifier") {
    const index = noms.indexOf(demande.colonne);
    if (index < 0 || demande.ligne < 2) return reponse({ erreur: "Case introuvable" });
    f.getRange(demande.ligne, index + 1).setValue(demande.valeur);
    return reponse({ ok: true });
  }
  if (demande.action === "preparer") {  // ajoute une offre à la file (une seule fois par lien)
    const deja = lignesFile().find(l => l.Lien === demande.offre.Lien);
    if (deja) return reponse({ ok: true, deja: true, etat: deja.Etat });
    file().appendRow(COLONNES_FILE.map(nom => nom === "Demandé le" ? new Date() : nom === "Etat" ? "En attente" : demande.offre[nom] || ""));
    return reponse({ ok: true });
  }
  if (demande.action === "maj_file") {  // Claude note l'avancement : Etat, CV, Lettre, Note
    const ff = file();
    const l = lignesFile().find(x => x.Lien === demande.lien);
    if (!l) return reponse({ erreur: "Offre absente de la file" });
    Object.entries(demande.valeurs).forEach(([nom, valeur]) => {
      const index = COLONNES_FILE.indexOf(nom);
      if (index >= 0 && nom !== "Lien") ff.getRange(l.ligne, index + 1).setValue(valeur);
    });
    return reponse({ ok: true });
  }
  return reponse({ erreur: "Action inconnue" });
}
