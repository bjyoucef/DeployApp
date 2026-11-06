import time
import requests
from concurrent.futures import ThreadPoolExecutor

OLD = "http://192.168.10.147:9042"
NEW = "http://192.168.10.148:8042"      # adapter le port
OLD_AUTH = None                          # ("user", "pass") si nécessaire
NEW_AUTH = None
WORKERS = 4                              # 2 à 4 : le NAS ne supportera pas plus
LIMIT = 3                                # test : 3 études. Mettre None pour tout copier

def make_session(auth):
    s = requests.Session()
    if auth:
        s.auth = auth
    ad = requests.adapters.HTTPAdapter(pool_connections=WORKERS, pool_maxsize=WORKERS * 2)
    s.mount("http://", ad)
    return s

old = make_session(OLD_AUTH)
new = make_session(NEW_AUTH)

def instance_ids(session, base, study_id):
    r = session.get(f"{base}/studies/{study_id}/instances", timeout=120)
    if r.status_code == 404:
        return set()
    r.raise_for_status()
    return {i["ID"] for i in r.json()}

def copy_instance(iid):
    for tentative in range(4):
        try:
            r = old.get(f"{OLD}/instances/{iid}/file", timeout=(10, 600))
            r.raise_for_status()
            p = new.post(f"{NEW}/instances", data=r.content, timeout=(10, 600))
            p.raise_for_status()
            return True
        except Exception as e:
            time.sleep(3 * (tentative + 1))
    with open("echecs.txt", "a") as f:
        f.write(iid + "\n")
    return False

def main():
    studies = old.get(f"{OLD}/studies", timeout=120).json()
    if LIMIT:
        studies = studies[:LIMIT]
    total = len(studies)
    print(f"{total} études à vérifier")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for n, sid in enumerate(studies, 1):
            try:
                src = instance_ids(old, OLD, sid)
                dst = instance_ids(new, NEW, sid)
                manquantes = list(src - dst)
                if not manquantes:
                    print(f"[{n}/{total}] {sid} déjà complète")
                    continue
                ok = sum(pool.map(copy_instance, manquantes))
                print(f"[{n}/{total}] {sid} : {ok}/{len(manquantes)} instances copiées")
            except Exception as e:
                print(f"[{n}/{total}] {sid} ERREUR : {e}")
                with open("echecs_etudes.txt", "a") as f:
                    f.write(sid + "\n")

if __name__ == "__main__":
    main()
