/** @OnlyCurrentDoc */
// La ligne ci-dessus limite l'autorisation à ce seul Google Sheet (et non à tous vos fichiers).
// Script à coller dans votre Google Sheet (Extensions > Apps Script).
// Il permet au tableau de bord de lire vos candidatures, d'en ajouter et de changer leur état.
// Le tableur doit avoir en ligne 1 les colonnes : Poste, Entreprise, Date, Contrat, Pays, Etat, Lien, Description.
// Il gère aussi la file d'attente « À préparer » (onglet créé automatiquement) : le bouton « Préparer ma candidature »
// y ajoute l'offre, et Claude y note l'avancement et les liens du CV et de la lettre.

const MOT_DE_PASSE = "remplacez-moi"; // choisissez un mot de passe ; vous le saisirez une fois dans le tableau de bord

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

function reponse(donnees) {
  return ContentService.createTextOutput(JSON.stringify(donnees)).setMimeType(ContentService.MimeType.JSON);
}

// Lecture : renvoie toutes les candidatures et les choix des menus déroulants
function doGet(e) {
  if (e.parameter.cle !== MOT_DE_PASSE) return reponse({ erreur: "Mot de passe incorrect" });
  if (e.parameter.action === "file") return reponse({ file: lignesFile() });
  const f = feuille();
  const noms = colonnes();
  const valeurs = f.getLastRow() > 1 ? f.getRange(2, 1, f.getLastRow() - 1, noms.length).getValues() : [];
  const lignes = valeurs.map((ligne, i) => {
    const objet = { ligne: i + 2 };
    noms.forEach((nom, j) => {
      const v = ligne[j];
      objet[nom] = v instanceof Date ? Utilities.formatDate(v, "Europe/Paris", "yyyy-MM-dd") : String(v);
    });
    return objet;
  }).filter(l => l.Poste || l.Entreprise);
  return reponse({ lignes: lignes, etats: choix("Etat"), contrats: choix("Contrat") });
}

// Écriture : ajoute une candidature, ou modifie une case d'une ligne existante
function doPost(e) {
  const demande = JSON.parse(e.postData.contents);
  if (demande.cle !== MOT_DE_PASSE) return reponse({ erreur: "Mot de passe incorrect" });
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
    const f = file();
    const l = lignesFile().find(x => x.Lien === demande.lien);
    if (!l) return reponse({ erreur: "Offre absente de la file" });
    Object.entries(demande.valeurs).forEach(([nom, valeur]) => {
      const index = COLONNES_FILE.indexOf(nom);
      if (index >= 0 && nom !== "Lien") f.getRange(l.ligne, index + 1).setValue(valeur);
    });
    return reponse({ ok: true });
  }
  return reponse({ erreur: "Action inconnue" });
}
