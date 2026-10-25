"""Envoi de notifications Web Push, sans dépendance autre que `cryptography`.

- Chiffrement du message pour le navigateur : RFC 8291 (Web Push) avec l'encodage aes128gcm (RFC 8188).
- Signature de l'expéditeur (VAPID) : RFC 8292, jeton JWT ES256.

Les clés VAPID de Kelvisi sont une paire P-256 : la clé publique (65 octets, point non compressé)
est donnée aux navigateurs ; la clé privée (32 octets) ne quitte jamais le serveur.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

TAILLE_ENREGISTREMENT = 4096


def b64(octets: bytes) -> str:
    return base64.urlsafe_b64encode(octets).rstrip(b"=").decode()


def deb64(texte: str) -> bytes:
    texte = texte.strip()
    return base64.urlsafe_b64decode(texte + "=" * (-len(texte) % 4))


def _hmac(cle: bytes, donnees: bytes) -> bytes:
    return hmac.new(cle, donnees, hashlib.sha256).digest()


def _point(cle_publique: ec.EllipticCurvePublicKey) -> bytes:
    return cle_publique.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def creer_cles() -> tuple[str, str]:
    """Nouvelle paire VAPID : (clé publique, clé privée), en base64url."""
    privee = ec.generate_private_key(ec.SECP256R1())
    return b64(_point(privee.public_key())), b64(privee.private_numbers().private_value.to_bytes(32, "big"))


def cle_privee(texte: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(deb64(texte), "big"), ec.SECP256R1())


def chiffrer(message: bytes, p256dh: str, auth: str, *, cle_ephemere: ec.EllipticCurvePrivateKey | None = None,
             sel: bytes | None = None) -> bytes:
    """Corps chiffré (aes128gcm) destiné au navigateur abonné (clés `p256dh` et `auth` de son abonnement)."""
    ua_public = deb64(p256dh)
    secret_auth = deb64(auth)
    cle_ephemere = cle_ephemere or ec.generate_private_key(ec.SECP256R1())
    as_public = _point(cle_ephemere.public_key())
    secret = cle_ephemere.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public))
    prk_cle = _hmac(secret_auth, secret)
    ikm = _hmac(prk_cle, b"WebPush: info\x00" + ua_public + as_public + b"\x01")
    sel = sel or os.urandom(16)
    prk = _hmac(sel, ikm)
    cek = _hmac(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = _hmac(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    chiffre = AESGCM(cek).encrypt(nonce, message + b"\x02", None)  # un seul enregistrement, marqué comme le dernier
    return sel + struct.pack("!IB", TAILLE_ENREGISTREMENT, len(as_public)) + as_public + chiffre


def jeton_vapid(point_de_terminaison: str, cle_privee_b64: str, contact: str, maintenant: int | None = None) -> str:
    """Jeton JWT ES256 qui identifie Kelvisi auprès du service de notification du navigateur."""
    morceaux = urlsplit(point_de_terminaison)
    entete = {"typ": "JWT", "alg": "ES256"}
    revendications = {"aud": f"{morceaux.scheme}://{morceaux.netloc}", "exp": int(maintenant or time.time()) + 12 * 3600, "sub": contact}
    signe = f"{b64(json.dumps(entete, separators=(',', ':')).encode())}.{b64(json.dumps(revendications, separators=(',', ':')).encode())}"
    r, s = decode_dss_signature(cle_privee(cle_privee_b64).sign(signe.encode(), ec.ECDSA(hashes.SHA256())))
    return f"{signe}.{b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def envoyer(abonnement: dict, donnees: dict, cle_publique: str, cle_privee_b64: str, contact: str, *, duree_s: int = 12 * 3600,
            post=None) -> int:
    """Envoie une notification ; renvoie le code HTTP du service (201 : acceptée ; 404 ou 410 : abonnement expiré)."""
    import requests

    post = post or requests.post
    corps = chiffrer(json.dumps(donnees, ensure_ascii=False).encode(), abonnement["p256dh"], abonnement["auth"])
    r = post(abonnement["endpoint"], data=corps, timeout=20, headers={
        "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": str(duree_s), "Urgency": "normal",
        "Authorization": f"vapid t={jeton_vapid(abonnement['endpoint'], cle_privee_b64, contact)}, k={cle_publique}",
    })
    return r.status_code
