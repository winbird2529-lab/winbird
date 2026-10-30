import pymysql

HOST = "192.168.1.180"
USER = 'root'
PASS = '1234'
DATABASE = 'dk_test'

_CACHED_CONFIG = None

def _get_connection():
    global _CACHED_CONFIG
    if _CACHED_CONFIG:
        try:
            return pymysql.connect(
                host=_CACHED_CONFIG["host"],
                user=_CACHED_CONFIG["user"],
                passwd=_CACHED_CONFIG["passwd"],
                db=_CACHED_CONFIG["db"],
                port=_CACHED_CONFIG.get("port", 3306),
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=2
            )
        except Exception:
            _CACHED_CONFIG = None

    candidates = [
        (HOST, USER, PASS, DATABASE, 3306, 5),
        ("127.0.0.1", USER, PASS, DATABASE, 3306, 2),
        ("localhost", USER, PASS, DATABASE, 3306, 2),
        (HOST, "root", "", DATABASE, 3306, 5),
        ("127.0.0.1", "root", "", DATABASE, 3306, 2),
        ("localhost", "root", "", DATABASE, 3306, 2),
        ("127.0.0.1", "root", "root", DATABASE, 3306, 2),
    ]
    last_err = None
    for h, u, p, d, port, timeout in candidates:
        try:
            conn = pymysql.connect(
                host=h, user=u, passwd=p, db=d, port=port,
                charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=timeout
            )
            _CACHED_CONFIG = {"host": h, "user": u, "passwd": p, "db": d, "port": port}
            print(f"[DB CONNECT SUCCESS] Connected to MySQL at {h}:{port} (db: {d})")
            return conn
        except Exception as e:
            last_err = e
    raise last_err

class db:

    @staticmethod
    def execute(sql, params=None):
        return db.sql_commit(sql, params)

    @staticmethod
    def sql_execute(sql, params=None):
        return db.sql_commit(sql, params)

    @staticmethod
    def sql_fetchall(sql, params=None):
        conn = None
        try:
            conn = _get_connection()
            with conn.cursor() as cur:
                if params:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                return cur.fetchall()
        except Exception as e:
            print(f"[ERROR] sql_fetchall: {e}")
            return None
        finally:
            if conn and conn.open:
                conn.close()

    @staticmethod
    def sql_fetchone(sql, params=None):
        conn = None
        try:
            conn = _get_connection()
            with conn.cursor() as cur:
                if params:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                return cur.fetchone()
        except Exception as e:
            print(f"[ERROR] sql_fetchone: {e}")
            return None
        finally:
            if conn and conn.open:
                conn.close()

    @staticmethod
    def sql_commit(sql, params=None):
        conn = None
        try:
            conn = _get_connection()
            with conn.cursor() as cur:
                if params:
                    cur.execute(sql, params)
                else:
                    cur.execute(sql)
                conn.commit()
                return True
        except Exception as e:
            print(f"[ERROR] sql_commit: {e}")
            return False
        finally:
            if conn and conn.open:
                conn.close()

    @staticmethod
    def sql_run_commit(sql):
        conn = None
        try:
            conn = _get_connection()
            with conn.cursor() as cur:
                cur.execute(sql)
                conn.commit()
                return True
        except Exception as e:
            print(f"[ERROR] sql_run_commit: {e}")
            return False
        finally:
            if conn and conn.open:
                conn.close()
