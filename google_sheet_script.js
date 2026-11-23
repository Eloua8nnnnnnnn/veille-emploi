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

const PAGE_DASHBOARD = "https://raw.githubusercontent.com/Eloua8nnnnnnnn/veille-emploi/main/docs/app.html";

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
    page = UrlFetchApp.fetch(PAGE_DASHBOARD).getContentText();
    try { cache.put("page", page, 300); } catch (e) {}  // gardée 5 minutes
  }
  return HtmlService.createHtmlOutput(page)
    .setTitle("Mon dashboard")
    .addMetaTag("viewport", "width=device-width, initial-scale=1, viewport-fit=cover");
}

// Fonctions appelées par la page (google.script.run) : chacune vérifie d'abord que c'est vous.
function accueil() {
  verifierProprietaire();
  return { candidatures: lignesCandidatures().length, file: lignesFile() };
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
