// Réglages de l'application, à compléter avant la mise en ligne (voir GUIDE.md).

export const CONFIG = {
  // Nom (ou raison sociale) de l'éditeur et adresse de contact, affichés dans les mentions légales
  editeur: "",
  contact: "",

  // Comptes Kelvisi : projet Supabase, adresse et clé publique « publishable » (faite pour être
  // publique). Jamais la clé secrète ici : elle va uniquement dans les secrets GitHub.
  supabaseUrl: "https://sawrleydibeasqpqszps.supabase.co",
  supabaseCleAnon: "sb_publishable_-rEnKMQ2eHWrdVSrVBMJXg_Zd9Ps7St",

  // Interrupteur des comptes : true rend l'inscription obligatoire pour tout le monde.
  // À passer à true seulement quand le projet Supabase est prêt (GUIDE.md, étape 6, a à c) :
  // sinon les inscriptions échoueraient et plus personne ne pourrait utiliser l'appli.
  comptesOuverts: false,

  // Fuseau d'affichage des heures
  fuseau: "Europe/Paris",
};
