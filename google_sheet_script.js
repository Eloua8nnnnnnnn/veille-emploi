/** @OnlyCurrentDoc */
// La ligne ci-dessus limite l'autorisation à ce seul Google Sheet (et non à tous vos fichiers).
// Script à coller dans votre Google Sheet (Extensions > Apps Script).
// Il permet au tableau de bord de lire vos candidatures, d'en ajouter et de changer leur état.
// Le tableur doit avoir en ligne 1 les colonnes : Poste, Entreprise, Date, Contrat, Pays, Etat, Lien, Description.

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

function reponse(donnees) {
  return ContentService.createTextOutput(JSON.stringify(donnees)).setMimeType(ContentService.MimeType.JSON);
}

// Lecture : renvoie toutes les candidatures et les choix des menus déroulants
function doGet(e) {
  if (e.parameter.cle !== MOT_DE_PASSE) return reponse({ erreur: "Mot de passe incorrect" });
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
    return reponse({ ok: true, ligne: f.getLastRow() });
  }
  if (demande.action === "modifier") {
    const index = noms.indexOf(demande.colonne);
    if (index < 0 || demande.ligne < 2) return reponse({ erreur: "Case introuvable" });
    f.getRange(demande.ligne, index + 1).setValue(demande.valeur);
    return reponse({ ok: true });
  }
  return reponse({ erreur: "Action inconnue" });
}
