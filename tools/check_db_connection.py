"""Find out why the portal cannot reach the online database.   python tools/check_db_connection.py

If SUPABASE_URL and SUPABASE_SERVICE_KEY are set it simply tests the web API route. Otherwise it reads DATABASE_URL
(from .env or the environment, never prints the password) and tests, step by step:
  1. the name resolves to an address      4. the Postgres server answers the start of its protocol
  2. a TCP connection opens               5. a full login with psycopg (30 second limit)
  3. a control: does a port that should be CLOSED also "open"? (that means a firewall/proxy is in the way)
"""
import os
import socket
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402  (loads .env)


def step(n, text):
    print(f"\n[{n}] {text}")


def main() -> None:
    import database as db
    if db.use_rest():
        print(f"Using the Supabase web API (HTTPS): {config.SUPABASE_URL}  (DATABASE_URL is ignored)")
        t = time.time()
        try:
            conn = db.get_conn()
            row = conn.execute("SELECT current_database() AS database, current_user AS role, "
                               "(SELECT COUNT(*) FROM candidates) AS candidates").fetchone()
            print(f"  OK in {time.time() - t:.2f}s: {dict(row)}")
            print("  The portal can read and write Supabase. If candidates is a number, the tables exist too.")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED after {time.time() - t:.1f}s: {exc}")
        return
    url = config.DATABASE_URL
    if not url:
        sys.exit("DATABASE_URL is empty. Put it in .env (see supabase/README.md).")
    if "YOUR-PASSWORD" in url or "[" in url.split("@")[0]:
        sys.exit("PROBLEM: DATABASE_URL still contains the placeholder [YOUR-PASSWORD]. Replace it (brackets included) "
                 "with your real database password, then run this again.")
    u = urlparse(url)
    host, port = u.hostname, u.port or 5432
    print(f"Host {host}  port {port}  user {u.username}  database {u.path.lstrip('/')}")

    step(1, "DNS")
    try:
        addrs = sorted({a[4][0] for a in socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)})
        print("  OK:", ", ".join(addrs))
    except OSError as exc:
        sys.exit(f"  FAILED: {exc}\n  -> the name does not resolve. Check the host in DATABASE_URL, your DNS or VPN.")
    ip = next((a for a in addrs if ":" not in a), addrs[0])

    step(2, f"TCP connect to {ip}:{port}")
    t = time.time()
    try:
        s = socket.create_connection((ip, port), timeout=10)
        print(f"  OK in {time.time() - t:.2f}s")
    except OSError as exc:
        sys.exit(f"  FAILED: {exc}\n  -> the port is blocked on your network.")

    step(3, "Control: a port that should be closed (59999)")
    try:
        socket.create_connection((ip, 59999), timeout=6).close()
        print("  It CONNECTED. Something between you and the internet (campus/office firewall, proxy, antivirus) accepts"
              "\n  every connection and then drops the real traffic. That is why step 2 'worked'.")
    except OSError as exc:
        print(f"  Refused/timed out as expected ({type(exc).__name__}): the path to the server is genuine.")

    step(4, "Does a Postgres server answer? (sends the standard SSL request)")
    try:
        s.settimeout(10)
        s.sendall(bytes([0, 0, 0, 8, 4, 210, 22, 47]))
        reply = s.recv(1)
        print("  Reply:", reply, "-> yes, a Postgres server answered" if reply in (b"S", b"N") else "-> unexpected reply")
    except OSError as exc:
        print(f"  NO ANSWER ({type(exc).__name__}). The connection opens but Postgres traffic is dropped on the way."
              "\n  -> try another network (phone hotspot) or switch off antivirus/firewall 'web protection'.")
    finally:
        s.close()

    step(5, "Full login with psycopg")
    try:
        import psycopg
    except ImportError:
        sys.exit('  psycopg is not installed:  pip install "psycopg[binary]"')
    t = time.time()
    try:
        with psycopg.connect(url, connect_timeout=30, prepare_threshold=None) as c:
            print(f"  OK in {time.time() - t:.2f}s:", c.execute("select current_database(), current_user").fetchone())
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).strip().splitlines()[0]
        print(f"  FAILED after {time.time() - t:.1f}s: {type(exc).__name__}: {msg}")
        low = msg.lower()
        if "password" in low:
            print("  -> wrong password (reset it in Supabase > Project settings > Database).")
        elif "tenant" in low or "user not found" in low:
            print("  -> wrong username/project or region; copy the pooler string from the Supabase Connect button again.")
        elif "timeout" in low:
            print("  -> still timing out: see steps 3 and 4 above.")


if __name__ == "__main__":
    main()
