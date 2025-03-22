import datetime
import logging
import os

import requests

# Configura il logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class TorrentCleanerService:
    def __init__(self):
        self.qbittorrent_url = os.getenv("QBITTORRENT_URL")
        self.username = os.getenv("QBITTORRENT_USER")
        self.password = os.getenv("QBITTORRENT_PASS")
        self.days_old = int(os.getenv("DAYS_OLD", 90))
        self.session = None

        # Se i parametri fondamentali sono mancanti, disabilita il login
        if not self.qbittorrent_url or not self.username or not self.password:
            logger.warning("⚠️ Parametri mancanti: il servizio partirà senza connessione a qBittorrent.")
        else:
            self.login()

    def login(self):
        """ Effettua il login a qBittorrent e memorizza la sessione """
        self.session = requests.Session()
        login_data = {"username": self.username, "password": self.password}

        try:
            response = self.session.post(f"{self.qbittorrent_url}/api/v2/auth/login", data=login_data)
            if response.status_code == 200 and response.text == "Ok.":
                logger.info("✅ Login a qBittorrent riuscito!")
                return True
            else:
                logger.error("❌ Errore di login su qBittorrent: %s", response.text)
        except requests.RequestException as e:
            logger.error("⚠️ Errore di connessione a qBittorrent: %s", e)

        self.session = None
        return False

    def delete_torrent(self, torrent_hash, delete_files=True):
        """ Elimina un torrent per hash """
        if not self.session:
            logger.warning("⚠️ Nessuna sessione attiva, impossibile eliminare il torrent %s", torrent_hash)
            return False

        try:
            response = self.session.post(
                f"{self.qbittorrent_url}/api/v2/torrents/delete",
                data={"hashes": torrent_hash, "deleteFiles": str(delete_files).lower()}
            )
            if response.status_code == 200:
                logger.info("🗑️ Torrent eliminato con successo: %s", torrent_hash)
                return True
            logger.warning("⚠️ Impossibile eliminare il torrent %s - Status Code: %d", torrent_hash,
                           response.status_code)
        except requests.RequestException as e:
            logger.error("❌ Errore durante l'eliminazione del torrent %s: %s", torrent_hash, e)

        return False

    def clean_torrents(self):
        """ Controlla i torrent e applica le regole di eliminazione """
        if not self.session:
            return {"status": "error", "message": "Impossibile connettersi a qBittorrent"}

        try:
            response = self.session.get(f"{self.qbittorrent_url}/api/v2/torrents/info")
            if response.status_code != 200:
                return {"status": "error", "message": "Errore nel recupero dei torrent"}

            torrents = response.json()
            deleted_count = 0
            now = datetime.datetime.now()

            for torrent in torrents:
                torrent_hash = torrent["hash"]
                added_on = datetime.datetime.fromtimestamp(torrent["added_on"])
                days_old = (now - added_on).days
                comment = torrent.get("comment", "").strip()

                # Controlla se il torrent è completo
                if torrent["progress"] < 1.0:
                    logger.info(
                        f"⏳ Torrent '{torrent['name']}' ancora in download ({torrent['progress'] * 100:.2f}%), skip.")
                    continue

                # Criterio di eliminazione: Senza commento o troppo vecchio
                if not comment or comment == "dynamic metainfo from client":
                    logger.info(f"🚮 Eliminando torrent senza commento: {torrent['name']}")
                    if self.delete_torrent(torrent_hash):
                        deleted_count += 1
                elif days_old > self.days_old:
                    logger.info(
                        f"📅 Eliminando torrent '{torrent['name']}' con commento (aggiunto {days_old} giorni fa)")
                    if self.delete_torrent(torrent_hash):
                        deleted_count += 1

            return {"status": "success", "deleted": deleted_count}

        except requests.RequestException as e:
            logger.error("❌ Errore nel recupero dei torrent: %s", e)
            return {"status": "error", "message": "Errore nella connessione a qBittorrent"}
