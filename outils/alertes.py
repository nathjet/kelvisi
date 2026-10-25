"""Alertes sur les favoris et les spots privés : une notification quand la visibilité prévue y devient bonne.

Chaque utilisateur choisit, sur ses favoris (points Kelvisi) et ses spots privés, d'être alerté
(colonne `alerte` des tables favoris et spots_prives : "bonne" ou "excellente"). Les prévisions des
spots privés sous alerte sont calculées ici, cinq fois par jour (8 h, 11 h, 14 h, 17 h et 20 h,
heure de Paris), et ne sont jamais publiées. À chaque calcul horaire, pour aujourd'hui et les deux jours suivants, on
cherche les favoris dont la journée atteint ce niveau avec un créneau conseillé, puis on envoie une
seule notification par compte qui les regroupe. Règles :
  - une alerte au plus par favori et par jour prévu (table alertes_envoyees) ;
  - envois seulement entre 8 h et 21 h, heure de Paris ;
  - aujourd'hui seulement si le meilleur créneau n'est pas encore passé ;
  - abonnement refusé par le service du navigateur (404, 410) : supprimé.

Les clés VAPID sont créées au premier passage et rangées dans la table cles_push, que seule la clé
secrète du serveur peut lire. La clé publique est publiée dans donnees/push.json pour l'application.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import webpush

PARIS = ZoneInfo("Europe/Paris")
RANG = {"mauvaise": 0, "moyenne": 1, "bonne": 2, "excellente": 3}
SEUIL = {"bonne": 2, "excellente": 3}
HEURE_DEBUT, HEURE_FIN = 8, 21
JOURS = 3
# Spots privés : prévision recalculée à ces heures seulement (deux appels Open-Meteo par position)
HEURES_SPOTS_PRIVES = {8, 11, 14, 17, 20}
MAX_SPOTS_PRIVES = 150
CHAMPS_PRIVES = "proprietaire,id,nom,lat,lon,region,orientation_deg,ouverture_deg,profondeur_m,fond,alerte"
JOURS_SEMAINE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _entetes(cle: str) -> dict:
    return {"apikey": cle} if cle.startswith("sb_") else {"apikey": cle, "Authorization": f"Bearer {cle}"}


class Base:
    """Accès REST à Supabase avec la clé secrète (contourne les règles d'accès, réservée au serveur)."""

    def __init__(self, url: str, cle: str, session=None):
        import requests

        self.url, self.entetes, self.http = url.rstrip("/"), _entetes(cle), session or requests.Session()

    def lire(self, chemin: str):
        r = self.http.get(f"{self.url}/rest/v1/{chemin}", headers=self.entetes, timeout=30)
        r.raise_for_status()
        return r.json()

    def ecrire(self, chemin: str, corps, prefer: str = "return=minimal"):
        r = self.http.post(f"{self.url}/rest/v1/{chemin}", json=corps, headers={**self.entetes, "Prefer": prefer}, timeout=30)
        r.raise_for_status()

    def effacer(self, chemin: str):
        r = self.http.delete(f"{self.url}/rest/v1/{chemin}", headers=self.entetes, timeout=30)
        r.raise_for_status()


def cles_vapid(base: Base, creer=webpush.creer_cles) -> tuple[str, str]:
    """Clés de notification de Kelvisi, créées au premier passage."""
    lignes = base.lire("cles_push?select=publique,privee&id=eq.1")
    if not lignes:
        publique, privee = creer()
        base.ecrire("cles_push", {"id": 1, "publique": publique, "privee": privee}, prefer="resolution=ignore-duplicates,return=minimal")
        lignes = base.lire("cles_push?select=publique,privee&id=eq.1")  # en cas de création simultanée, la première gagne
    return lignes[0]["publique"], lignes[0]["privee"]


def nom_du_jour(date: str, aujourd_hui: str) -> str:
    if date == aujourd_hui:
        return "aujourd'hui"
    j = datetime.strptime(date, "%Y-%m-%d")
    if (j - datetime.strptime(aujourd_hui, "%Y-%m-%d")).days == 1:
        return "demain"
    return JOURS_SEMAINE[j.weekday()]


def a_signaler(points: dict, alertes: list[dict], deja: set, maintenant: datetime) -> dict:
    """{proprietaire: [(point, jour)]} : favoris qui atteignent le niveau demandé et pas encore signalés."""
    local = maintenant.astimezone(PARIS)
    aujourd_hui = local.strftime("%Y-%m-%d")
    resultat = defaultdict(list)
    for a in alertes:
        point = a.get("point") or points.get(a["point_id"])
        seuil = SEUIL.get(a.get("alerte") or "")
        if not point or seuil is None:
            continue
        for jour in point.get("jours", [])[:JOURS]:
            cr = jour.get("meilleur_creneau")
            if jour["date"] < aujourd_hui or not cr or RANG.get(jour.get("classe"), -1) < seuil:
                continue
            if jour["date"] == aujourd_hui and datetime.fromisoformat(cr["fin"]) <= maintenant:
                continue
            if (a["proprietaire"], a["point_id"], jour["date"]) in deja:
                continue
            resultat[a["proprietaire"]].append((point, jour))
    return dict(resultat)


def message(liste: list, maintenant: datetime) -> dict:
    """Contenu de la notification (titre, texte, lien ouvert d'un geste)."""
    aujourd_hui = maintenant.astimezone(PARIS).strftime("%Y-%m-%d")
    par_point = defaultdict(list)
    for point, jour in liste:
        par_point[point["id"]].append((point, jour))
    lignes = []
    for groupe in par_point.values():
        point = groupe[0][0]
        jours = ", ".join(f"{round(j['meilleur_creneau']['visibilite_m'])} m {nom_du_jour(j['date'], aujourd_hui)}"
                          for _, j in sorted(groupe, key=lambda x: x[1]["date"]))
        lignes.append(f"{point['nom']} : {jours}")
    excellente = any(j.get("classe") == "excellente" for _, j in liste)
    reste = len(lignes) - 3
    return {
        "titre": "Excellente visibilité prévue" if excellente else "Bonne visibilité prévue",
        "corps": "\n".join(lignes[:3]) + (f"\net {reste} autre{'s' if reste > 1 else ''} favori{'s' if reste > 1 else ''}" if reste > 0 else ""),
        "url": (next(iter(par_point.values()))[0][0].get("lien") or f"#/spot/{next(iter(par_point))}") if len(par_point) == 1 else "#/liste",
        "etiquette": "kelvisi-alerte",
    }


def prevoir_spots_prives(lignes: list[dict], spots_publics: list, maintenant: datetime, recuperer) -> dict:
    """Prévisions des spots privés sous alerte : {(propriétaire, id): point au format du résumé}.

    `recuperer(positions)` renvoie les conditions météo de chaque position (arrondie à 0,01°,
    comme dans le navigateur). Chaque spot reprend les valeurs calées de son voisin Kelvisi.
    """
    from prevision import prevoir
    from prevision.spot import Spot, avec_reglage_voisin

    spots = []
    for ligne in lignes[:MAX_SPOTS_PRIVES]:
        try:
            spots.append((ligne, Spot(id=ligne["id"], nom=ligne["nom"], lat=float(ligne["lat"]), lon=float(ligne["lon"]),
                                      region=ligne["region"], orientation_deg=float(ligne["orientation_deg"]),
                                      ouverture_deg=float(ligne["ouverture_deg"]), profondeur_m=float(ligne["profondeur_m"]),
                                      fond=ligne["fond"], prive=True)))
        except (KeyError, TypeError, ValueError):
            continue
    positions = sorted({(round(s.lat, 2), round(s.lon, 2)) for _, s in spots})
    if not positions:
        return {}
    conditions = dict(zip(positions, recuperer(positions)))
    t = int(maintenant.timestamp())
    resultat = {}
    for ligne, spot in spots:
        try:
            p = prevoir(avec_reglage_voisin(spot, spots_publics), conditions[(round(spot.lat, 2), round(spot.lon, 2))], t, jours=JOURS)
        except Exception:
            continue
        resultat[(ligne["proprietaire"], spot.id)] = {"id": spot.id, "nom": spot.nom, "lien": f"#/prive/{spot.id}",
                                                      "jours": [{k: j.get(k) for k in ("date", "classe", "meilleur_creneau")} for j in p["jours"]]}
    return resultat


def traiter(base: Base, resume: dict, maintenant: datetime, contact: str, envoyer=webpush.envoyer, prevoir_prives=None) -> dict:
    """Envoie les alertes du passage. Renvoie un bilan sans donnée personnelle et la clé publique.

    `prevoir_prives(lignes)` calcule les prévisions des spots privés sous alerte (voir
    prevoir_spots_prives) ; sans lui, seules les alertes des favoris sont traitées.
    """
    publique, privee = cles_vapid(base)
    bilan = {"cle_publique": publique, "comptes": 0, "notifications": 0, "abonnements_supprimes": 0, "hors_horaires": False,
             "spots_prives": None}
    try:  # colonne « alerte » des spots privés présente (script SQL à jour) : l'appli peut la proposer
        base.lire("spots_prives?select=alerte&limit=1")
        bilan["alertes_spots_prives"] = True
    except Exception:
        bilan["alertes_spots_prives"] = False
    heure = maintenant.astimezone(PARIS).hour
    if not HEURE_DEBUT <= heure < HEURE_FIN:
        bilan["hors_horaires"] = True
        return bilan
    alertes = base.lire("favoris?select=proprietaire,point_id,alerte&alerte=not.is.null")
    if prevoir_prives is not None and heure in HEURES_SPOTS_PRIVES and bilan["alertes_spots_prives"]:
        try:
            lignes = base.lire(f"spots_prives?select={CHAMPS_PRIVES}&alerte=not.is.null&order=maj_le.desc")
            prevus = prevoir_prives(lignes) if lignes else {}
            bilan["spots_prives"] = len(prevus)
            alertes = alertes + [{"proprietaire": l["proprietaire"], "point_id": l["id"], "alerte": l["alerte"], "point": prevus[(l["proprietaire"], l["id"])]}
                                 for l in lignes if (l["proprietaire"], l["id"]) in prevus]
        except Exception as e:
            bilan["spots_prives"] = f"indisponibles ({type(e).__name__})"
    if not alertes:
        return bilan
    depuis = (maintenant.astimezone(PARIS) - timedelta(days=1)).strftime("%Y-%m-%d")
    deja = {(e["proprietaire"], e["point_id"], e["jour"]) for e in base.lire(f"alertes_envoyees?select=proprietaire,point_id,jour&jour=gte.{depuis}")}
    points = {p["id"]: p for p in resume["points"]}
    a_envoyer = a_signaler(points, alertes, deja, maintenant)
    if not a_envoyer:
        return bilan
    abonnements = defaultdict(list)
    for ab in base.lire("abonnements_push?select=proprietaire,endpoint,p256dh,auth"):
        abonnements[ab["proprietaire"]].append(ab)
    envoyes = []
    for proprietaire, liste in a_envoyer.items():
        if not abonnements.get(proprietaire):
            continue
        donnees = message(liste, maintenant)
        recu = False
        for ab in abonnements[proprietaire]:
            try:
                statut = envoyer(ab, donnees, publique, privee, contact)
            except Exception:
                continue
            if statut in (404, 410):
                base.effacer(f"abonnements_push?proprietaire=eq.{proprietaire}&endpoint=eq.{_echapper(ab['endpoint'])}")
                bilan["abonnements_supprimes"] += 1
            elif 200 <= statut < 300:
                recu = True
                bilan["notifications"] += 1
        if recu:
            bilan["comptes"] += 1
            envoyes += [{"proprietaire": proprietaire, "point_id": p["id"], "jour": j["date"]} for p, j in liste]
    if envoyes:
        base.ecrire("alertes_envoyees?on_conflict=proprietaire,point_id,jour", envoyes, prefer="resolution=ignore-duplicates,return=minimal")
    return bilan


def _echapper(valeur: str) -> str:
    """Valeur placée dans un filtre PostgREST (eq.) : guillemets doubles, caractères réservés encodés."""
    from urllib.parse import quote

    return quote('"' + valeur.replace('"', '\\"') + '"', safe="")


def maintenant_utc() -> datetime:
    return datetime.now(timezone.utc)
