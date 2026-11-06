import sys
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor

# ===================== CONFIGURATION =====================
OLD = "http://192.168.10.147:9042"
NEW = "http://192.168.10.148:8042"          # adapter le port si besoin
OLD_AUTH = ("UTILISATEUR_ANCIEN", "MOT_DE_PASSE_ANCIEN")   # None si pas d'authentification
NEW_AUTH = ("UTILISATEUR_NOUVEAU", "MOT_DE_PASSE_NOUVEAU")  # None si pas d'authentification
WORKERS = 4          # 2 à 4 (le NAS ne supportera pas plus)
LIMIT = 3            # test : 3 études. Mettre None pour tout copier
LOG_FILE = "sync.log"
FAIL_FILE = "echecs.txt"
# =========================================================

lock = threading.Lock()
stats = {"copied": 0, "skipped": 0, "failed": 0}


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def make_session(auth):
    s = requests.Session()
    if auth:
        s.auth = auth
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=WORKERS, pool_maxsize=WORKERS * 2
    )
    s.mount("http://", adapter)
    return s


old = make_session(OLD_AUTH)
new = make_session(NEW_AUTH)


def get_statistics(session, base):
    r = session.get(f"{base}/statistics", timeout=60)
    r.raise_for_status()
    return r.json()


def instance_ids(session, base, study_id):
    r = session.get(f"{base}/studies/{study_id}/instances", timeout=120)
    if r.status_code == 404:
        return set()
    r.raise_for_status()
    return {i["ID"] for i in r.json()}


def copy_instance(iid):
    for attempt in range(4):
        try:
            r = old.get(f"{OLD}/instances/{iid}/file", timeout=(10, 600))
            r.raise_for_status()
            p = new.post(f"{NEW}/instances", data=r.content, timeout=(10, 600))
            p.raise_for_status()
            with lock:
                stats["copied"] += 1
            return True
        except Exception as e:
            last_error = e
            time.sleep(3 * (attempt + 1))
    with lock:
        stats["failed"] += 1
        with open(FAIL_FILE, "a", encoding="utf-8") as f:
            f.write(f"{iid}\t{last_error}\n")
    return False


def format_duration(seconds):
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}h{m:02d}m{s:02d}s"


def main():
    log("Connexion aux deux serveurs...")
    try:
        st_old = get_statistics(old, OLD)
        st_new = get_statistics(new, NEW)
    except Exception as e:
        log(f"ERREUR de connexion : {e}")
        sys.exit(1)

    total_instances_old = st_old["CountInstances"]
    log(f"Ancien : {st_old['CountStudies']} examens, {total_instances_old} instances")
    log(f"Nouveau : {st_new['CountStudies']} examens, {st_new['CountInstances']} instances")

    studies = old.get(f"{OLD}/studies", timeout=120).json()
    if LIMIT:
        studies = studies[:LIMIT]
    total = len(studies)
    log(f"{total} examens à traiter (WORKERS={WORKERS})")

    start = time.time()
    done_instances_estimate = 0  # copiées + déjà présentes

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for n, sid in enumerate(studies, 1):
            try:
                src = instance_ids(old, OLD, sid)
                dst = instance_ids(new, NEW, sid)
                missing = list(src - dst)

                with lock:
                    stats["skipped"] += len(src) - len(missing)
                done_instances_estimate += len(src) - len(missing)

                if missing:
                    for k, res in enumerate(pool.map(copy_instance, missing), 1):
                        if k % 100 == 0:
                            log(f"    étude {n}/{total} : {k}/{len(missing)} instances")
                    done_instances_estimate += len(missing)

                elapsed = time.time() - start
                pct = 100 * n / total
                eta = (elapsed / n) * (total - n)
                log(
                    f"[{n}/{total}] {pct:5.1f}% | étude {sid[:8]}... "
                    f"| {len(src)} inst. ({len(missing)} copiées) "
                    f"| total copiées={stats['copied']} déjà présentes={stats['skipped']} "
                    f"échecs={stats['failed']} | écoulé {format_duration(elapsed)} "
                    f"| restant ~{format_duration(eta)}"
                )
            except Exception as e:
                log(f"[{n}/{total}] ERREUR étude {sid} : {e}")
                with open(FAIL_FILE, "a", encoding="utf-8") as f:
                    f.write(f"STUDY\t{sid}\t{e}\n")

    log("===== TERMINÉ =====")
    log(f"Copiées : {stats['copied']} | Déjà présentes : {stats['skipped']} | Échecs : {stats['failed']}")
    log(f"Durée totale : {format_duration(time.time() - start)}")

    try:
        st_new = get_statistics(new, NEW)
        log(f"Nouveau serveur maintenant : {st_new['CountStudies']} examens, {st_new['CountInstances']} instances")
        log(f"Ancien serveur (référence) : {st_old['CountStudies']} examens, {total_instances_old} instances")
    except Exception as e:
        log(f"Impossible de lire les statistiques finales : {e}")

    if stats["failed"]:
        log(f"Des échecs sont listés dans {FAIL_FILE} : relance le script pour les reprendre.")


if __name__ == "__main__":
    main()
