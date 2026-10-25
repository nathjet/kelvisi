"""Alertes sur les favoris : chiffrement Web Push (RFC 8291), jeton VAPID (RFC 8292), choix et envoi des alertes."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "outils"))

import alertes  # noqa: E402
import webpush as wp  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402

# Exemple de la RFC 8291, section 5
UA_PRIVEE = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"
UA_PUBLIQUE = "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
AUTH = "BTBZMqHH6r4Tts7J_aSIgg"


def test_chiffrement_conforme_a_la_rfc_8291():
    corps = wp.chiffrer(b"When I grow up, I want to be a watermelon", UA_PUBLIQUE, AUTH,
                        cle_ephemere=wp.cle_privee("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), sel=wp.deb64("DGv6ra1nlYgDCS1FRnbzlw"))
    assert wp.b64(corps) == ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3j"
                             "l7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def dechiffrer(corps: bytes, ua_privee: str, auth: str) -> bytes:
    """Ce que fait le navigateur à la réception (côté abonné de la RFC 8291)."""
    sel, idlen = corps[:16], corps[20]
    as_public, chiffre = corps[21:21 + idlen], corps[21 + idlen:]
    privee = wp.cle_privee(ua_privee)
    ua_public = wp._point(privee.public_key())
    secret = privee.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public))
    ikm = wp._hmac(wp._hmac(wp.deb64(auth), secret), b"WebPush: info\x00" + ua_public + as_public + b"\x01")
    prk = wp._hmac(sel, ikm)
    clair = AESGCM(wp._hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]).decrypt(wp._hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12], chiffre, None)
    assert clair.endswith(b"\x02")
    return clair[:-1]


def test_jeton_vapid_signe_et_borne():
    publique, privee = wp.creer_cles()
    assert len(wp.deb64(publique)) == 65 and len(wp.deb64(privee)) == 32
    jeton = wp.jeton_vapid("https://fcm.googleapis.com/fcm/send/abc", privee, "https://nathjet.github.io/kelvisi/", maintenant=1_800_000_000)
    entete, revendications, signature = jeton.split(".")
    assert json.loads(wp.deb64(entete)) == {"typ": "JWT", "alg": "ES256"}
    assert json.loads(wp.deb64(revendications)) == {"aud": "https://fcm.googleapis.com", "exp": 1_800_000_000 + 12 * 3600, "sub": "https://nathjet.github.io/kelvisi/"}
    brute = wp.deb64(signature)
    cle = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), wp.deb64(publique))
    cle.verify(encode_dss_signature(int.from_bytes(brute[:32], "big"), int.from_bytes(brute[32:], "big")),
               f"{entete}.{revendications}".encode(), ec.ECDSA(hashes.SHA256()))


def test_envoi_d_une_notification():
    publique, privee = wp.creer_cles()
    recu = {}

    class Reponse:
        status_code = 201

    def post(url, data, timeout, headers):
        recu.update(url=url, data=data, headers=headers)
        return Reponse()

    abonnement = {"endpoint": "https://web.push.apple.com/QGuQyavXutnMH", "p256dh": UA_PUBLIQUE, "auth": AUTH}
    assert wp.envoyer(abonnement, {"titre": "Bonne visibilité prévue", "corps": "Groix : 9 m demain"}, publique, privee, "mailto:x@y.fr", post=post) == 201
    assert recu["headers"]["Content-Encoding"] == "aes128gcm" and recu["headers"]["TTL"] == "43200"
    assert recu["headers"]["Authorization"].startswith("vapid t=") and recu["headers"]["Authorization"].endswith(f", k={publique}")
    assert json.loads(dechiffrer(recu["data"], UA_PRIVEE, AUTH)) == {"titre": "Bonne visibilité prévue", "corps": "Groix : 9 m demain"}


# --- Choix des alertes ------------------------------------------------------------------------

def jour(date, classe, debut="10:00", fin="13:00", visi=9.0):
    return {"date": date, "classe": classe, "meilleur_creneau": {"debut": f"{date}T{debut}:00+02:00", "fin": f"{date}T{fin}:00+02:00", "visibilite_m": visi}}


POINTS = {
    "ref-groix": {"id": "ref-groix", "nom": "Groix", "jours": [jour("2026-10-25", "bonne"), jour("2026-10-26", "excellente", visi=12.4), jour("2026-10-27", "moyenne")]},
    "ref-glenan": {"id": "ref-glenan", "nom": "Glénan", "jours": [jour("2026-10-25", "moyenne"), jour("2026-10-26", "bonne", visi=8.2), {"date": "2026-10-27", "classe": "bonne", "meilleur_creneau": None}]},
}
A, B = "aaaa", "bbbb"
MATIN = datetime(2026, 10, 25, 7, 30, tzinfo=timezone.utc)  # 8 h 30 à Paris (heure d'hiver)


def test_choix_des_jours_a_signaler():
    alertes_ = [{"proprietaire": A, "point_id": "ref-groix", "alerte": "bonne"}, {"proprietaire": A, "point_id": "ref-glenan", "alerte": "excellente"},
                {"proprietaire": B, "point_id": "ref-glenan", "alerte": "bonne"}, {"proprietaire": B, "point_id": "ref-inconnu", "alerte": "bonne"}]
    r = alertes.a_signaler(POINTS, alertes_, set(), MATIN)
    assert [(p["id"], j["date"]) for p, j in r[A]] == [("ref-groix", "2026-10-25"), ("ref-groix", "2026-10-26")]
    assert [(p["id"], j["date"]) for p, j in r[B]] == [("ref-glenan", "2026-10-26")], "pas de créneau conseillé le 27"
    # Déjà signalé, ou créneau du jour passé : rien de nouveau
    r = alertes.a_signaler(POINTS, alertes_[:1], {(A, "ref-groix", "2026-10-26")}, datetime(2026, 10, 25, 12, 30, tzinfo=timezone.utc))
    assert r == {}


def test_message_regroupe_les_favoris():
    m = alertes.message([(POINTS["ref-groix"], POINTS["ref-groix"]["jours"][1]), (POINTS["ref-groix"], POINTS["ref-groix"]["jours"][0])], MATIN)
    assert m == {"titre": "Excellente visibilité prévue", "corps": "Groix : 9 m aujourd'hui, 12 m demain", "url": "#/spot/ref-groix", "etiquette": "kelvisi-alerte"}
    autres = [({"id": f"p{i}", "nom": f"Spot {i}"}, jour("2026-10-27", "bonne")) for i in range(5)]
    m = alertes.message(autres, MATIN)
    assert m["titre"] == "Bonne visibilité prévue" and m["url"] == "#/liste"
    assert m["corps"].splitlines() == ["Spot 0 : 9 m mardi", "Spot 1 : 9 m mardi", "Spot 2 : 9 m mardi", "et 2 autres favoris"]


class FausseBase:
    def __init__(self, cles=None):
        self.tables = {
            "cles_push": cles or [],
            "favoris": [{"proprietaire": A, "point_id": "ref-groix", "alerte": "bonne"}, {"proprietaire": B, "point_id": "ref-glenan", "alerte": "bonne"},
                        {"proprietaire": B, "point_id": "ref-groix", "alerte": None}],
            "alertes_envoyees": [{"proprietaire": A, "point_id": "ref-groix", "jour": "2026-10-25"}],
            "abonnements_push": [{"proprietaire": A, "endpoint": "https://push.test/a1", "p256dh": UA_PUBLIQUE, "auth": AUTH},
                                 {"proprietaire": A, "endpoint": "https://push.test/a2", "p256dh": UA_PUBLIQUE, "auth": AUTH},
                                 {"proprietaire": B, "endpoint": "https://push.test/b1", "p256dh": UA_PUBLIQUE, "auth": AUTH}],
        }
        self.ecrits, self.effaces = [], []

    def lire(self, chemin):
        table = chemin.split("?")[0]
        lignes = self.tables[table]
        if table == "favoris":
            lignes = [x for x in lignes if x["alerte"]]
        return [dict(x) for x in lignes]

    def ecrire(self, chemin, corps, prefer=""):
        self.ecrits.append((chemin.split("?")[0], corps))
        if chemin.startswith("cles_push"):
            self.tables["cles_push"].append(corps)

    def effacer(self, chemin):
        self.effaces.append(chemin)


def test_envoi_des_alertes_du_passage():
    base = FausseBase()
    envois = []

    def envoyer(ab, donnees, publique, privee, contact):
        envois.append((ab["endpoint"], donnees["corps"]))
        return {"https://push.test/a2": 410, "https://push.test/b1": 503}.get(ab["endpoint"], 201)

    bilan = alertes.traiter(base, {"points": list(POINTS.values())}, MATIN, "https://kelvisi.test/", envoyer=envoyer)
    assert base.ecrits[0][0] == "cles_push" and len(wp.deb64(bilan["cle_publique"])) == 65, "clés créées au premier passage"
    assert sorted(envois) == [("https://push.test/a1", "Groix : 12 m demain"), ("https://push.test/a2", "Groix : 12 m demain"), ("https://push.test/b1", "Glénan : 8 m demain")]
    assert bilan == {"cle_publique": bilan["cle_publique"], "comptes": 1, "notifications": 1, "abonnements_supprimes": 1, "hors_horaires": False,
                     "spots_prives": None}
    assert len(base.effaces) == 1 and "endpoint=eq.%22https%3A%2F%2Fpush.test%2Fa2%22" in base.effaces[0]
    # Seule l'alerte arrivée est notée comme envoyée : celle de B (service en panne) repartira au passage suivant
    assert base.ecrits[-1] == ("alertes_envoyees", [{"proprietaire": A, "point_id": "ref-groix", "jour": "2026-10-26"}])


def test_pas_d_envoi_la_nuit_et_cles_reprises():
    base = FausseBase(cles=[{"publique": "PUB", "privee": "PRIV"}])
    bilan = alertes.traiter(base, {"points": list(POINTS.values())}, datetime(2026, 10, 25, 21, 0, tzinfo=timezone.utc), "x",
                            envoyer=lambda *a: pytest.fail("aucun envoi la nuit"))
    assert bilan["hors_horaires"] and bilan["cle_publique"] == "PUB" and not base.ecrits


def test_alertes_dans_le_calcul_horaire(monkeypatch):
    import calculer_previsions as cp

    class Erreur(Exception):
        response = type("R", (), {"status_code": 404})()

    def absente(*a, **k):
        raise Erreur()

    cp.BILAN.clear()
    assert cp.envoyer_alertes("https://x.supabase.co", "sb_secret_x", {"points": []}, 1_792_918_800, traiter=absente) is None
    assert "relance supabase/schema.sql" in cp.BILAN[-1]
    ok = cp.envoyer_alertes("https://x.supabase.co", "sb_secret_x", {"points": []}, 1_792_918_800,
                            traiter=lambda *a, **k: {"cle_publique": "PUB", "comptes": 2, "notifications": 3, "abonnements_supprimes": 0, "hors_horaires": False})
    assert ok == {"cle_publique": "PUB"} and cp.BILAN[-1] == "Alertes : 3 notifications envoyées à 2 comptes"


# --- Spots privés sous alerte ------------------------------------------------------------------

LIGNE_PRIVEE = {"proprietaire": B, "id": "prive-crique", "nom": "Ma crique", "lat": 47.4912, "lon": -3.2031, "region": "atlantique",
                "orientation_deg": 270, "ouverture_deg": 90, "profondeur_m": 8, "fond": "roche", "alerte": "bonne"}


def test_prevision_des_spots_prives():
    from prevision import charger_spots
    from prevision.simulation import calme

    publics = charger_spots(Path(__file__).resolve().parent.parent / "spots" / "points.json")
    maintenant = datetime(2026, 10, 25, 10, 17, tzinfo=timezone.utc)
    demandes = []

    def recuperer(positions):
        demandes.append(positions)
        return [calme(int(maintenant.timestamp()) - 5 * 86400, jours=9) for _ in positions]

    autre = {**LIGNE_PRIVEE, "proprietaire": A, "id": "prive-voisin", "lat": 47.4888}
    invalide = {**LIGNE_PRIVEE, "id": "prive-faux", "region": "pacifique"}
    r = alertes.prevoir_spots_prives([LIGNE_PRIVEE, autre, invalide], publics, maintenant, recuperer)
    assert demandes == [[(47.49, -3.2)]], "deux spots à moins d'un kilomètre : une seule position demandée"
    assert set(r) == {(B, "prive-crique"), (A, "prive-voisin")}
    p = r[(B, "prive-crique")]
    assert p["lien"] == "#/prive/prive-crique" and len(p["jours"]) == 3
    assert set(p["jours"][0]) == {"date", "classe", "meilleur_creneau"}


def test_alertes_des_spots_prives_aux_heures_prevues():
    prive = {"id": "prive-crique", "nom": "Ma crique", "lien": "#/prive/prive-crique", "jours": [jour("2026-10-26", "bonne", visi=7.6)]}
    base = FausseBase()
    base.tables["spots_prives"] = [LIGNE_PRIVEE]
    lu = []

    def prevoir_prives(lignes):
        lu.append([l["id"] for l in lignes])
        return {(B, "prive-crique"): prive}

    envois = []
    envoyer = lambda ab, d, *a: envois.append((ab["endpoint"], d)) or 201  # noqa: E731
    # 9 h 17 à Paris : pas une heure de calcul des spots privés
    bilan = alertes.traiter(base, {"points": []}, datetime(2026, 10, 25, 8, 17, tzinfo=timezone.utc), "x", envoyer=envoyer, prevoir_prives=prevoir_prives)
    assert not lu and bilan["spots_prives"] is None
    # 11 h 17 à Paris : calculés, alerte envoyée avec un lien vers le spot privé
    bilan = alertes.traiter(base, {"points": []}, datetime(2026, 10, 25, 10, 17, tzinfo=timezone.utc), "x", envoyer=envoyer, prevoir_prives=prevoir_prives)
    assert lu == [["prive-crique"]] and bilan["spots_prives"] == 1
    assert envois == [("https://push.test/b1", {"titre": "Bonne visibilité prévue", "corps": "Ma crique : 8 m demain", "url": "#/prive/prive-crique",
                                                 "etiquette": "kelvisi-alerte"})]
    assert base.ecrits[-1] == ("alertes_envoyees", [{"proprietaire": B, "point_id": "prive-crique", "jour": "2026-10-26"}])


def test_spots_prives_illisibles_sans_bloquer_les_favoris():
    base = FausseBase()  # pas de table spots_prives : colonne alerte absente
    bilan = alertes.traiter(base, {"points": list(POINTS.values())}, MATIN.replace(hour=10, minute=17), "x",
                            envoyer=lambda *a: 201, prevoir_prives=lambda lignes: {})
    assert bilan["spots_prives"].startswith("indisponibles") and bilan["notifications"] >= 1
