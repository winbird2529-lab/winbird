from flask import Flask,render_template,request
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField,BooleanField
from flask import request, jsonify
from fastapi import FastAPI, Form, UploadFile, File
from datetime import datetime, date
import os
import json
import sys
if "D:\\BWAPI" not in sys.path:
    sys.path.append("D:\\BWAPI")

import mimetypes
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/javascript', '.js')
mimetypes.add_type('text/css', '.css')

class DBProxy:
    """Proxy สำหรับเรียกใช้งาน MySQL Database แบบไดนามิก ไม่ค้างเป็น None เมื่อเกิดข้อผิดพลาดในการเชื่อมต่อชั่วคราว"""
    def __getattr__(self, name):
        try:
            import connect_db
            return getattr(connect_db.db, name)
        except Exception as e:
            print(f"[DBProxy Error] {name}: {e}")
            def _dummy(*args, **kwargs):
                return None
            return _dummy
    def __bool__(self):
        try:
            import connect_db
            return True
        except Exception:
            return False

mysql_db = DBProxy()

try:
    from sql import bk as sql_BK
    sql_BK.ensure_schema_cusid()
    sql_BK.update_database_cusid("00001")
    if hasattr(sql_BK, "ensure_schema_running"):
        sql_BK.ensure_schema_running()
except Exception as _ex_init:
    print(f"[WARN] ensure_schema on app init: {_ex_init}")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mykey'
app.config['TEMPLATES_AUTO_RELOAD'] = True

class MyForm(FlaskForm):
    name = StringField ("ป้อนชื่อของคุณ")
    submit = SubmitField("บันทึก")

@app.route("/admin",methods=['GET','POST']) 
def admin():
    form = MyForm()
    return render_template("admin.html", form = form)

@app.route("/")
@app.route("/login") 
def login():
    return render_template("login.html")

@app.route("/logout")
def logout():
    return render_template("login.html")

@app.route("/select_system")
def select_system():
    return render_template("index.html")


@app.route("/DK_Home")  
def DK_Home(): 
    return render_template("DK_Home.html")


@app.route("/api/dashboard_summary")
def api_dashboard_summary():
    """สรุปข้อมูลภาพรวมระบบสำหรับหน้า Dashboard (DK_Home)"""
    summary = {
        "status": "success",
        "members": {"total": 0, "active": 0, "deceased": 0, "new_this_month": 0},
        "financial": {"today_amount": 0.0, "today_count": 0, "month_amount": 0.0, "month_count": 0, "total_amount": 0.0, "total_count": 0, "total_debt_remaining": 0.0},
        "transactions": {"total_cases": 0, "paid_cases": 0, "partial_cases": 0, "unpaid_cases": 0, "cancelled_cases": 0, "total_claim_amount": 0.0},
        "recent_movements": [],
        "recent_transactions": [],
        "deceased_collections": [],
        "monthly_chart": []
    }
    if not mysql_db:
        return jsonify(summary)

    try:
        # 1. ข้อมูลสมาชิก
        row_m = mysql_db.sql_fetchone("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 1 OR status IS NULL THEN 1 ELSE 0 END) as active,
                SUM(CASE WHEN status IN (3, 4) THEN 1 ELSE 0 END) as deceased,
                SUM(CASE WHEN date >= DATE_FORMAT(NOW(), '%Y-%m-01') THEN 1 ELSE 0 END) as new_this_month
            FROM bk_customer
        """)
        if not row_m or not row_m.get("total"):
            row_m = mysql_db.sql_fetchone("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 1 OR status IS NULL THEN 1 ELSE 0 END) as active,
                    SUM(CASE WHEN status IN (3, 4) THEN 1 ELSE 0 END) as deceased,
                    SUM(CASE WHEN date >= DATE_FORMAT(NOW(), '%Y-%m-01') THEN 1 ELSE 0 END) as new_this_month
                FROM customer
            """)
        if row_m:
            summary["members"] = {
                "total": int(row_m.get("total") or 0),
                "active": int(row_m.get("active") or 0),
                "deceased": int(row_m.get("deceased") or 0),
                "new_this_month": int(row_m.get("new_this_month") or 0)
            }

        # 2. ข้อมูลการเงิน (bk_movement)
        row_f = mysql_db.sql_fetchone("""
            SELECT
                COALESCE(SUM(CASE WHEN DATE(date) = CURDATE() AND status != 2 THEN payamount ELSE 0 END), 0) as today_amount,
                COALESCE(SUM(CASE WHEN DATE(date) = CURDATE() AND status != 2 THEN 1 ELSE 0 END), 0) as today_count,
                COALESCE(SUM(CASE WHEN date >= DATE_FORMAT(NOW(), '%Y-%m-01') AND status != 2 THEN payamount ELSE 0 END), 0) as month_amount,
                COALESCE(SUM(CASE WHEN date >= DATE_FORMAT(NOW(), '%Y-%m-01') AND status != 2 THEN 1 ELSE 0 END), 0) as month_count,
                COALESCE(SUM(CASE WHEN status != 2 THEN payamount ELSE 0 END), 0) as total_amount,
                COALESCE(SUM(CASE WHEN status != 2 THEN 1 ELSE 0 END), 0) as total_count
            FROM bk_movement
        """)
        if row_f:
            summary["financial"]["today_amount"] = float(row_f.get("today_amount") or 0)
            summary["financial"]["today_count"] = int(row_f.get("today_count") or 0)
            summary["financial"]["month_amount"] = float(row_f.get("month_amount") or 0)
            summary["financial"]["month_count"] = int(row_f.get("month_count") or 0)
            summary["financial"]["total_amount"] = float(row_f.get("total_amount") or 0)
            summary["financial"]["total_count"] = int(row_f.get("total_count") or 0)

        # 3. ข้อมูลหนี้และรายการตั้งศพ (bk_transaction + bk_transactiondetail)
        rows_tr = mysql_db.sql_fetchall("""
            SELECT 
                t.docid,
                t.status,
                COALESCE(SUM(td.amount), 0) as total_claim,
                COALESCE(SUM(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2))), 0) as total_paid
            FROM bk_transaction t
            LEFT JOIN bk_transactiondetail td ON t.docid = td.docid
            GROUP BY t.docid, t.status
        """)
        if rows_tr:
            tot_cases = len(rows_tr)
            paid_cases = 0
            part_cases = 0
            unpaid_cases = 0
            cancel_cases = 0
            tot_claim = 0.0
            tot_debt_remain = 0.0

            for r in rows_tr:
                st = int(r.get("status") or 1)
                tc = float(r.get("total_claim") or 0)
                tp = float(r.get("total_paid") or 0)
                if st == 2:
                    cancel_cases += 1
                else:
                    tot_claim += tc
                    remain = tc - tp
                    if remain > 0:
                        tot_debt_remain += remain
                    if tp > 0 and remain <= 0:
                        paid_cases += 1
                    elif tp > 0 and remain > 0:
                        part_cases += 1
                    else:
                        unpaid_cases += 1

            summary["transactions"] = {
                "total_cases": tot_cases,
                "paid_cases": paid_cases,
                "partial_cases": part_cases,
                "unpaid_cases": unpaid_cases,
                "cancelled_cases": cancel_cases,
                "total_claim_amount": tot_claim
            }
            summary["financial"]["total_debt_remaining"] = tot_debt_remain

        # 4. รายการรับเงินล่าสุด 5 รายการ
        rows_rec_m = mysql_db.sql_fetchall("""
            SELECT docidmove, date, Idcustomer, prefix, name, lastname, payamount, pay_type, status
            FROM bk_movement
            ORDER BY date DESC, docidmove DESC
            LIMIT 5
        """)
        if rows_rec_m:
            for r in rows_rec_m:
                summary["recent_movements"].append({
                    "docidmove": r.get("docidmove"),
                    "date": r.get("date").strftime("%Y-%m-%d") if r.get("date") and hasattr(r.get("date"), "strftime") else str(r.get("date") or ""),
                    "Idcustomer": r.get("Idcustomer") or "",
                    "fullname": f"{r.get('prefix') or ''}{r.get('name') or ''} {r.get('lastname') or ''}".strip(),
                    "payamount": float(r.get("payamount") or 0),
                    "pay_type": r.get("pay_type") or "เงินสด",
                    "status": int(r.get("status") or 1)
                })

        # 5. ข้อมูลสถานะการจัดเก็บหนี้รายศพ (ครบ / ไม่ครบ - ไม่นำรายการยกเลิกมาแสดง)
        rows_dec = mysql_db.sql_fetchall("""
            SELECT t.docid, t.date, t.Idcustomer, t.prefix, t.name, t.lastname, t.dateend, t.numberend, t.status,
                   COALESCE(SUM(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2))), 0.00) as paid_amount,
                   COALESCE(SUM(td.amount), 0.00) as claim_amount,
                   COUNT(td.Idcustomer) as total_members,
                   SUM(CASE WHEN COALESCE(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)), 0.00) >= td.amount THEN 1 ELSE 0 END) as count_paid,
                   SUM(CASE WHEN td.amount > COALESCE(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)), 0.00) THEN 1 ELSE 0 END) as count_remain
            FROM bk_transaction t
            LEFT JOIN bk_transactiondetail td ON t.docid = td.docid
            WHERE t.status != 2
            GROUP BY t.docid, t.date, t.Idcustomer, t.prefix, t.name, t.lastname, t.dateend, t.numberend, t.status
            ORDER BY t.date DESC, t.docid DESC
        """)
        if rows_dec:
            for r in rows_dec:
                st = int(r.get("status") or 1)
                if st == 2:
                    continue

                tot_c = float(r.get("claim_amount") or 0)
                tot_p = float(r.get("paid_amount") or 0)
                remain = max(0.0, tot_c - tot_p)
                pct = round((tot_p / tot_c * 100), 1) if tot_c > 0 else 0

                if tot_p > 0 and remain <= 0:
                    p_status = "paid"
                    status_text = "เก็บครบแล้ว"
                elif tot_p > 0 and remain > 0:
                    p_status = "partial"
                    status_text = "ยังไม่ครบ"
                else:
                    p_status = "unpaid"
                    status_text = "ยังไม่เริ่มเก็บ"

                item_dec = {
                    "docid": r.get("docid"),
                    "date": r.get("date").strftime("%Y-%m-%d") if r.get("date") and hasattr(r.get("date"), "strftime") else str(r.get("date") or ""),
                    "Idcustomer": r.get("Idcustomer") or "",
                    "fullname": f"{r.get('prefix') or ''}{r.get('name') or ''} {r.get('lastname') or ''}".strip(),
                    "dateend": r.get("dateend").strftime("%Y-%m-%d") if r.get("dateend") and hasattr(r.get("dateend"), "strftime") else str(r.get("dateend") or ""),
                    "numberend": r.get("numberend") or "-",
                    "claim_amount": tot_c,
                    "paid_amount": tot_p,
                    "remain_amount": remain,
                    "progress_percent": pct,
                    "payment_status": p_status,
                    "status_text": status_text,
                    "count_paid": int(r.get("count_paid") or 0),
                    "count_remain": int(r.get("count_remain") or 0),
                    "total_members": int(r.get("total_members") or 0),
                    "status": st
                }
                summary["deceased_collections"].append(item_dec)
                if len(summary["recent_transactions"]) < 5:
                    summary["recent_transactions"].append(item_dec)

        # 6. กราฟยอดรับชำระย้อนหลัง 6 เดือน
        rows_ch = mysql_db.sql_fetchall("""
            SELECT 
                DATE_FORMAT(date, '%Y-%m') as ym,
                SUM(payamount) as total,
                COUNT(*) as count
            FROM bk_movement
            WHERE status != 2 AND date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
            GROUP BY ym
            ORDER BY ym ASC
        """)
        if rows_ch:
            for r in rows_ch:
                summary["monthly_chart"].append({
                    "ym": r.get("ym"),
                    "total": float(r.get("total") or 0),
                    "count": int(r.get("count") or 0)
                })

    except Exception as e:
        print(f"[ERROR] api_dashboard_summary: {e}")

    return jsonify(summary)


@app.route("/DK_Constant")  
def DK_Constant(): 
    if mysql_db:
        try:
            from sql import bk as sql_BK
            sql_BK.update_database_cusid("00001")
        except Exception:
            pass
    return render_template("DK_Constant.html")


@app.route("/api/update_cusid", methods=["GET", "POST"])
def api_update_cusid():
    new_cusid = request.args.get("cusid") or "00001"
    if request.is_json:
        data = request.get_json() or {}
        new_cusid = data.get("cusid") or new_cusid
    try:
        from sql import bk as sql_BK
        res = sql_BK.update_database_cusid(new_cusid)
        return jsonify({"error": "0", "status": "success", "message": f"Updated cusid = {new_cusid} across all tables", "details": res})
    except Exception as e:
        return jsonify({"error": "1", "message": str(e)}), 500


@app.route("/api/constant", methods=["GET", "POST"])
def api_constant_proxy():
    import urllib.request
    FASTAPI_URL = "http://localhost:8000"
    if request.method == "POST":
        req_data = request.get_json() or {}
        try:
            req = urllib.request.Request(
                f"{FASTAPI_URL}/constant/save",
                data=json.dumps(req_data).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2) as res:
                return jsonify(json.loads(res.read().decode("utf-8")))
        except Exception as ex:
            return jsonify({"status": "error", "error": "1", "message": f"เซิร์ฟเวอร์ API (FastAPI พอร์ต 8000) ปิดอยู่: {ex}"}), 503
    else:
        try:
            with urllib.request.urlopen(f"{FASTAPI_URL}/constant", timeout=1) as res:
                return jsonify(json.loads(res.read().decode("utf-8")))
        except Exception as ex:
            return jsonify({"status": "error", "error": "1", "message": f"เซิร์ฟเวอร์ API (FastAPI พอร์ต 8000) ปิดอยู่: {ex}", "data": None}), 503




@app.route("/DK_customer")  
def DK_customer(): 
    return render_template("DK_customer.html")

@app.route("/delete_customer/<idcustomer>", methods=["DELETE", "POST", "GET"])
@app.route("/api/delete_customer/<idcustomer>", methods=["DELETE", "POST", "GET"])
def app_delete_customer(idcustomer):
    try:
        from sql import bk as sql_BK
        return jsonify(sql_BK.delete_customer(idcustomer))
    except Exception as e:
        return jsonify({"error": "1", "message": str(e)}), 500

@app.route("/DK_Employee")  
def DK_Employee(): 
    return render_template("DK_Employee.html")
@app.route("/DK_Beneficiary")  
def DK_Beneficiary(): 
    return render_template("DK_Beneficiary.html")

RUNNING_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'running_config.json')

def get_default_running_list():
    """รายการเลขที่เอกสารและค่าคงที่ยอดเงินมาตรฐาน 7 รายการหลัก (Fallback ป้องกันหน้าว่าง)"""
    return [
        {"Id": 1, "id": 1, "docid": "PC", "docId": "PC", "IdRunning": "000000", "name": "ทะเบียนสมาชิก", "mode": "auto", "category": "running"},
        {"Id": 2, "id": 2, "docid": "EY", "docId": "EY", "IdRunning": "000", "name": "ทะเบียนเจ้าหน้าที่", "mode": "auto", "category": "running"},
        {"Id": 3, "id": 3, "docid": "DW", "docId": "DW", "IdRunning": "000000", "name": "เอกสารตั้งหนี้สงเคราะห์", "mode": "auto", "category": "running"},
        {"Id": 4, "id": 4, "docid": "TR", "docId": "TR", "IdRunning": "000000", "name": "ใบเสร็จรับเงิน", "mode": "auto", "category": "running"},
        {"Id": 6, "id": 6, "docid": None, "docId": None, "IdRunning": "50.00", "name": "ค่าสมัครสมาชิก", "mode": "manual", "category": "money"},
        {"Id": 7, "id": 7, "docid": None, "docId": None, "IdRunning": "100.00", "name": "เงินสงเคราะห์ล่วงหน้า", "mode": "manual", "category": "money"},
        {"Id": 8, "id": 8, "docid": None, "docId": None, "IdRunning": "20.00", "name": "ค่าบำรุงรายปี", "mode": "manual", "category": "money"}
    ]

def fetch_running_data_safe():
    """ดึงข้อมูล bk_running จากฐานข้อมูล MySQL อย่างปลอดภัย พร้อม Auto-migration และ Fallback เสมอ"""
    # 1. เรียก ensure_schema_running ผ่าน sql_BK หากมี
    try:
        from sql import bk as sql_BK
        if hasattr(sql_BK, "ensure_schema_running"):
            sql_BK.ensure_schema_running()
    except Exception as e_ens:
        print(f"[WARN] ensure_schema_running in fetch_running_data_safe: {e_ens}")

    # 2. ตรวจสอบตารางและคอลัมน์โดยตรงผ่าน mysql_db
    if mysql_db:
        try:
            # ตรวจสอบและเพิ่มคอลัมน์อัตโนมัติหากยังไม่มี
            try:
                raw_cols = mysql_db.sql_fetchall("SHOW COLUMNS FROM bk_running") or []
                cols = [str(c.get("Field") or c.get("field") or "").lower() for c in raw_cols]
                if cols:
                    if "name" not in cols:
                        mysql_db.sql_commit("ALTER TABLE bk_running ADD COLUMN name VARCHAR(100) DEFAULT ''")
                    if "mode" not in cols:
                        mysql_db.sql_commit("ALTER TABLE bk_running ADD COLUMN mode VARCHAR(20) DEFAULT 'auto'")
                    if "category" not in cols:
                        mysql_db.sql_commit("ALTER TABLE bk_running ADD COLUMN category VARCHAR(20) DEFAULT 'running'")
                    if "cusid" not in cols:
                        mysql_db.sql_commit("ALTER TABLE bk_running ADD COLUMN cusid VARCHAR(50) DEFAULT '00001'")
            except Exception as e_col:
                print(f"[WARN] check columns bk_running: {e_col}")

            # ดึงข้อมูลด้วย SELECT * ปลอดภัยที่สุด ไม่เกิดข้อผิดพลาดกรณีฟิลด์ไม่ตรง
            rows = mysql_db.sql_fetchall("SELECT * FROM bk_running ORDER BY Id ASC")
            if not rows:
                rows = mysql_db.sql_fetchall("SELECT * FROM running ORDER BY Id ASC")

            if rows:
                normalized = []
                for r in rows:
                    item = dict(r)
                    item_id = int(item.get("Id") or item.get("id") or 0)
                    doc = item.get("docid") or item.get("docId") or item.get("doc_id") or ""
                    run = str(item.get("IdRunning") or item.get("id_running") or item.get("idrunning") or "")
                    name = item.get("name") or (f"เอกสาร {doc}" if doc else f"รายการ {item_id}")
                    mode = item.get("mode") or "auto"
                    if item_id in [6, 7, 8]:
                        cat = "money"
                    elif item.get("category"):
                        cat = item.get("category")
                    else:
                        cat = "money" if not doc else "running"

                    normalized.append({
                        "Id": item_id,
                        "id": item_id,
                        "docid": None if cat == "money" else doc,
                        "docId": None if cat == "money" else doc,
                        "IdRunning": run,
                        "id_running": run,
                        "name": name,
                        "mode": mode,
                        "category": cat
                    })
                return normalized
        except Exception as e_q:
            print(f"[ERROR] fetch bk_running query: {e_q}")

    # Fallback: คืนค่ารายการเริ่มต้น 7 รายการหลักเสมอ
    defaults = get_default_running_list()
    if mysql_db:
        try:
            row_c = mysql_db.sql_fetchone("SELECT cusid_prefix, cusid_latest, fee_register, fee_deceased, fee_yearly FROM bk_constant WHERE id = 1 LIMIT 1")
            if row_c:
                for it in defaults:
                    if it["Id"] == 1 and row_c.get("cusid_prefix"):
                        it["docid"] = row_c.get("cusid_prefix")
                        it["docId"] = row_c.get("cusid_prefix")
                        if row_c.get("cusid_latest"):
                            it["IdRunning"] = str(row_c.get("cusid_latest"))
                    elif it["Id"] == 6 and row_c.get("fee_register") is not None:
                        it["IdRunning"] = f"{float(row_c.get('fee_register')):.2f}"
                    elif it["Id"] == 7 and row_c.get("fee_deceased") is not None:
                        it["IdRunning"] = f"{float(row_c.get('fee_deceased')):.2f}"
                    elif it["Id"] == 8 and row_c.get("fee_yearly") is not None:
                        it["IdRunning"] = f"{float(row_c.get('fee_yearly')):.2f}"
        except Exception:
            pass
    return defaults

@app.route("/get-running", methods=["GET"])
@app.route("/api/get-running", methods=["GET"])
def get_running_endpoint():
    """API ส่งคืนเลข Running และ Prefix สำหรับแบบฟอร์มต่างๆ รองรับทั้ง port 5000 และ fallback"""
    item_id = request.args.get("id") or request.args.get("Id") or 1
    try:
        item_id = int(item_id)
    except Exception:
        item_id = 1

    # 1. ค้นหาโดยตรงจาก MySQL bk_running
    if mysql_db:
        try:
            row = mysql_db.sql_fetchone("SELECT * FROM bk_running WHERE Id = %s", (item_id,))
            if not row:
                row = mysql_db.sql_fetchone("SELECT * FROM running WHERE Id = %s", (item_id,))
            if row:
                doc = row.get("docId") or row.get("docid") or ""
                id_run = str(row.get("IdRunning") or row.get("id_running") or "")
                return jsonify({"error": "0", "docId": doc, "docid": doc, "IdRunning": id_run})
        except Exception as e:
            print(f"[WARN] Flask get-running DB error: {e}")

    # 2. Fallback จาก fetch_running_data_safe
    all_data = fetch_running_data_safe()
    for it in all_data:
        if int(it.get("Id") or it.get("id") or 0) == item_id:
            doc = it.get("docid") or it.get("docId") or ""
            id_run = str(it.get("IdRunning") or it.get("id_running") or "")
            return jsonify({"error": "0", "docId": doc, "docid": doc, "IdRunning": id_run})

    return jsonify({"error": "1", "message": "ไม่พบข้อมูล", "docId": "", "IdRunning": "000000"}), 404

@app.route("/running", methods=["GET", "POST"])
def running_alias():
    return api_running()

@app.route("/api/debug-db", methods=["GET"])
def api_debug_db():
    import traceback
    result = {}
    try:
        import connect_db
        result["db"] = connect_db.DATABASE
        result["tables"] = connect_db.db.sql_fetchall("SHOW TABLES")
        result["bk_tran_dw8"] = connect_db.db.sql_fetchall("SELECT * FROM bk_transaction WHERE docid LIKE '%DW000008%'")
        result["bk_trandetail_dw8"] = connect_db.db.sql_fetchall("SELECT * FROM bk_transactiondetail WHERE docid LIKE '%DW000008%' LIMIT 10")
        result["bk_trandetail_count"] = connect_db.db.sql_fetchone("SELECT COUNT(*) as c FROM bk_transactiondetail")
        result["bk_trandetail_distinct_docid"] = connect_db.db.sql_fetchall("SELECT DISTINCT docid, COUNT(*) as c FROM bk_transactiondetail GROUP BY docid LIMIT 20")
        try:
            result["trandetail_dw8"] = connect_db.db.sql_fetchall("SELECT * FROM transactiondetail WHERE docid LIKE '%DW000008%' LIMIT 10")
        except Exception as e:
            result["trandetail_err"] = str(e)
    except Exception as e:
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
    return jsonify(result)

@app.route("/DK_Running")
def DK_Running():
    return render_template("DK_Running.html")


@app.route("/api/running", methods=["GET", "POST"])
def api_running():
    """Proxy ตรงไปยังเซิร์ฟเวอร์ FastAPI (พอร์ต 8000) เท่านั้น หาก API ปิดอยู่จะไม่ดึงหรือบันทึกข้อมูล"""
    import urllib.request
    FASTAPI_URL = "http://localhost:8000"
    if request.method == "POST":
        req_data = request.get_json() or {}
        try:
            req = urllib.request.Request(
                f"{FASTAPI_URL}/running/save",
                data=json.dumps(req_data).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2) as res:
                return jsonify(json.loads(res.read().decode("utf-8")))
        except Exception as ex:
            return jsonify({"status": "error", "error": "1", "message": f"เซิร์ฟเวอร์ API (FastAPI พอร์ต 8000) ปิดอยู่: {ex}"}), 503
    else:
        try:
            with urllib.request.urlopen(f"{FASTAPI_URL}/running", timeout=1) as res:
                return jsonify(json.loads(res.read().decode("utf-8")))
        except Exception as ex:
            return jsonify({"status": "error", "error": "1", "message": f"เซิร์ฟเวอร์ API (FastAPI พอร์ต 8000) ปิดอยู่: {ex}", "data": [], "results": []}), 503


@app.route("/api/running/add", methods=["POST"])
def api_add_running():
    """เพิ่มประเภทเอกสาร Running หรือรายการยอดเงินใหม่ลงในฐานข้อมูล bk_running"""
    if not mysql_db:
        return jsonify({"status": "error", "message": "ไม่สามารถเชื่อมต่อฐานข้อมูลได้"}), 500
    try:
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        docid = (data.get("docid") or "").strip()
        id_running = (data.get("IdRunning") or "000000").strip()
        mode = data.get("mode") or "auto"
        category = data.get("category") or ("running" if docid else "money")

        if not name:
            return jsonify({"status": "error", "message": "กรุณาระบุชื่อรายการ"}), 400

        cusid = (data.get("cusid") or "").strip()
        if not cusid and mysql_db:
            try:
                row_c = mysql_db.sql_fetchone("SELECT cusid, tax_id FROM bk_constant WHERE id = 1 LIMIT 1")
                if row_c:
                    cusid = (row_c.get("cusid") or row_c.get("tax_id") or "").strip()
            except Exception:
                pass

        try:
            sql = "INSERT INTO bk_running (docid, IdRunning, name, mode, category, cusid) VALUES (%s, %s, %s, %s, %s, %s)"
            mysql_db.sql_commit(sql, (docid if docid else None, id_running, name, mode, category, cusid))
        except Exception:
            sql = "INSERT INTO bk_running (docid, IdRunning, name, mode, category) VALUES (%s, %s, %s, %s, %s)"
            mysql_db.sql_commit(sql, (docid if docid else None, id_running, name, mode, category))

        return jsonify({"status": "success", "message": "เพิ่มรายการลงฐานข้อมูลเรียบร้อยแล้ว"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/running/<int:item_id>", methods=["DELETE"])
def api_delete_running(item_id):
    """ลบรายการออกจากฐานข้อมูล bk_running"""
    if not mysql_db:
        return jsonify({"status": "error", "message": "ไม่สามารถเชื่อมต่อฐานข้อมูลได้"}), 500
    try:
        if item_id in [1, 2, 3, 4, 5, 6, 7, 8]:
            return jsonify({"status": "error", "message": "ไม่สามารถลบรายการหลักของระบบได้"}), 400
        mysql_db.sql_commit("DELETE FROM bk_running WHERE Id = %s", (item_id,))
        return jsonify({"status": "success", "message": "ลบรายการเรียบร้อยแล้ว"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/running-config", methods=["GET", "POST"])
def running_config():
    if request.method == "POST":
        data = request.get_json() or {}
        try:
            # 1. บันทึกลงฐานข้อมูล bk_running ในฟิลด์ mode
            if mysql_db:
                mode_map = {
                    "pc_mode": 1,
                    "ey_mode": 2,
                    "dw_mode": 3,
                    "tw_mode": 4
                }
                for key, run_id in mode_map.items():
                    if key in data:
                        mysql_db.sql_commit("UPDATE bk_running SET mode = %s WHERE Id = %s", (data[key], run_id))

            # 2. บันทึกลงไฟล์สำรอง
            current = {}
            if os.path.exists(RUNNING_CONFIG_FILE):
                try:
                    with open(RUNNING_CONFIG_FILE, "r", encoding="utf-8") as f:
                        current = json.load(f)
                except Exception:
                    pass
            current.update(data)
            with open(RUNNING_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
            return jsonify({"status": "success", "data": current})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        # ดึงโหมดจากตาราง bk_running ในฐานข้อมูล
        default_config = {
            "pc_mode": "auto",
            "ey_mode": "auto",
            "dw_mode": "auto",
            "tw_mode": "auto"
        }
        if mysql_db:
            try:
                rows = mysql_db.sql_fetchall("SELECT Id, docid, mode FROM bk_running")
                if rows:
                    for r in rows:
                        m = r.get("mode") or "auto"
                        rid = r.get("Id")
                        doc = (r.get("docid") or "").upper()
                        if rid == 1 or doc == "PC": default_config["pc_mode"] = m
                        elif rid == 2 or doc == "EY": default_config["ey_mode"] = m
                        elif rid == 3 or doc == "DW": default_config["dw_mode"] = m
                        elif rid == 4 or doc in ["TR", "TW"]: default_config["tw_mode"] = m
                    return jsonify(default_config)
            except Exception as e:
                print(f"[WARN] running-config DB fetch error: {e}")

        # Fallback ไฟล์สำรอง
        if os.path.exists(RUNNING_CONFIG_FILE):
            try:
                with open(RUNNING_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_config.update(data)
            except Exception:
                pass
        return jsonify(default_config)

# ============================================================
# ระบบฐานข้อมูลและจัดการผู้ใช้งาน (login table)
# ============================================================


USER_PERMISSIONS_FILE = os.path.join(os.path.dirname(__file__), 'user_permissions.json')

def load_user_permissions():
    """ดึงข้อมูลผู้ใช้จากตาราง bk_login ใน MySQL (หากไม่ได้จะ fallback ไปไฟล์ JSON)"""
    if mysql_db:
        try:
            sql = "SELECT id, COALESCE(idlogin, LPAD(id, 3, '0')) as idlogin, username, password, fullname, empid, role, status, permissions, userid, useredit, created_at, updated_at FROM bk_login ORDER BY id ASC"
            rows = mysql_db.sql_fetchall(sql)
            if rows is None:
                rows = mysql_db.sql_fetchall("SELECT id, username, password, fullname, empid, role, status, permissions, userid, useredit, created_at, updated_at FROM login ORDER BY id ASC")
            if rows is not None and len(rows) > 0:
                result = []
                for r in rows:
                    item = dict(r)
                    if "idlogin" not in item or not item["idlogin"]:
                        item["idlogin"] = f"{item['id']:03d}" if isinstance(item.get("id"), int) else str(item.get("id") or "")
                    perms = item.get("permissions")
                    if perms and isinstance(perms, str):
                        try:
                            item["permissions"] = json.loads(perms)
                        except Exception:
                            item["permissions"] = [p.strip() for p in perms.split(",") if p.strip()]
                    elif not perms:
                        item["permissions"] = []
                    
                    if item.get("created_at") and hasattr(item["created_at"], "isoformat"):
                        item["created_at"] = item["created_at"].isoformat()
                    if item.get("updated_at") and hasattr(item["updated_at"], "isoformat"):
                        item["updated_at"] = item["updated_at"].isoformat()
                    result.append(item)
                return result
        except Exception as e:
            print(f"[WARN] Failed to load from MySQL bk_login table: {e}")

    default_users = [
        {
            "id": "1",
            "idlogin": "001",
            "username": "admin",
            "password": "password123",
            "fullname": "ผู้ดูแลระบบสูงสุด",
            "empid": "001",
            "role": "admin",
            "status": "active",
            "permissions": ["running", "customer", "employee", "beneficiary", "deceased", "transaction", "movement", "view_customer", "view_employee", "view_movement", "view_transaction", "view_person", "permission", "template"],
            "userid": "system",
            "useredit": "",
            "updated_at": "2026-09-26T00:00:00Z"
        },
        {
            "id": "2",
            "idlogin": "002",
            "username": "staff01",
            "password": "password123",
            "fullname": "นางสาวเพ็ญศรี ปฏิบัติงาน",
            "empid": "002",
            "role": "staff",
            "status": "active",
            "permissions": ["customer", "employee", "beneficiary", "deceased", "transaction", "movement", "view_customer", "view_employee", "view_movement", "view_transaction", "view_person"],
            "userid": "admin",
            "useredit": "",
            "updated_at": "2026-09-26T00:00:00Z"
        },
        {
            "id": "3",
            "idlogin": "003",
            "username": "user01",
            "password": "password123",
            "fullname": "นายวิชัย สุขสมบูรณ์",
            "empid": "003",
            "role": "member",
            "status": "active",
            "permissions": ["view_movement", "view_transaction", "view_person"],
            "userid": "admin",
            "useredit": "staff01",
            "updated_at": "2026-09-26T00:00:00Z"
        }
    ]
    if os.path.exists(USER_PERMISSIONS_FILE):
        try:
            with open(USER_PERMISSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default_users

def save_user_permissions_file(data):
    with open(USER_PERMISSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_user_permission_to_db(payload):
    """บันทึกหรืออัปเดตลงตาราง bk_login ใน MySQL พร้อมฟิลด์ idlogin"""
    if not mysql_db:
        return False
    try:
        user_id = payload.get("id")
        idlogin = (payload.get("idlogin") or "").strip()
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        fullname = (payload.get("fullname") or "").strip()
        empid = (payload.get("empid") or payload.get("cusid") or "").strip()
        role = payload.get("role") or "staff"
        status = payload.get("status") or "active"
        perms = payload.get("permissions") or []
        perms_str = json.dumps(perms, ensure_ascii=False) if isinstance(perms, list) else str(perms)
        userid = (payload.get("userid") or payload.get("current_operator") or "admin").strip()
        useredit = (payload.get("useredit") or "").strip()

        if not idlogin and empid:
            idlogin = empid

        cusid = (payload.get("cusid") or "").strip()
        login_op = (payload.get("login") or payload.get("current_operator") or useredit or userid or "admin").strip()
        if not cusid and mysql_db:
            try:
                row_c = mysql_db.sql_fetchone("SELECT cusid, tax_id FROM bk_constant WHERE id = 1 LIMIT 1")
                if row_c:
                    cusid = (row_c.get("cusid") or row_c.get("tax_id") or "").strip()
            except Exception:
                pass

        existing = None
        if user_id and str(user_id).isdigit():
            existing = mysql_db.sql_fetchone("SELECT * FROM bk_login WHERE id = %s", (int(user_id),))
        if not existing and idlogin:
            existing = mysql_db.sql_fetchone("SELECT * FROM bk_login WHERE idlogin = %s", (idlogin,))
        if not existing and username:
            existing = mysql_db.sql_fetchone("SELECT * FROM bk_login WHERE username = %s", (username,))

        if existing:
            actual_id = existing["id"]
            actual_useredit = useredit if useredit else (payload.get("current_operator") or "admin")
            actual_idlogin = idlogin if idlogin else (existing.get("idlogin") or f"{actual_id:03d}")
            try:
                if password:
                    sql = """
                        UPDATE bk_login 
                        SET idlogin = %s, username = %s, password = %s, fullname = %s, empid = %s, role = %s, status = %s, permissions = %s, useredit = %s,
                            cusid = COALESCE(NULLIF(%s, ''), cusid)
                        WHERE id = %s
                    """
                    mysql_db.sql_commit(sql, (actual_idlogin, username, password, fullname, empid, role, status, perms_str, actual_useredit, cusid, actual_id))
                else:
                    sql = """
                        UPDATE bk_login 
                        SET idlogin = %s, username = %s, fullname = %s, empid = %s, role = %s, status = %s, permissions = %s, useredit = %s,
                            cusid = COALESCE(NULLIF(%s, ''), cusid)
                        WHERE id = %s
                    """
                    mysql_db.sql_commit(sql, (actual_idlogin, username, fullname, empid, role, status, perms_str, actual_useredit, cusid, actual_id))
            except Exception:
                if password:
                    sql = """
                        UPDATE bk_login 
                        SET idlogin = %s, username = %s, password = %s, fullname = %s, empid = %s, role = %s, status = %s, permissions = %s, useredit = %s 
                        WHERE id = %s
                    """
                    mysql_db.sql_commit(sql, (actual_idlogin, username, password, fullname, empid, role, status, perms_str, actual_useredit, actual_id))
                else:
                    sql = """
                        UPDATE bk_login 
                        SET idlogin = %s, username = %s, fullname = %s, empid = %s, role = %s, status = %s, permissions = %s, useredit = %s 
                        WHERE id = %s
                    """
                    mysql_db.sql_commit(sql, (actual_idlogin, username, fullname, empid, role, status, perms_str, actual_useredit, actual_id))
        else:
            if not idlogin:
                max_row = mysql_db.sql_fetchone("SELECT COALESCE(MAX(id), 0) + 1 as next_id FROM bk_login")
                next_num = max_row["next_id"] if max_row else 1
                idlogin = f"{next_num:03d}"
            try:
                sql = """
                    INSERT INTO bk_login (idlogin, username, password, fullname, empid, role, status, permissions, userid, useredit, cusid) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                mysql_db.sql_commit(sql, (idlogin, username, password, fullname, empid, role, status, perms_str, userid, useredit, cusid))
            except Exception:
                sql = """
                    INSERT INTO bk_login (idlogin, username, password, fullname, empid, role, status, permissions, userid, useredit) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                mysql_db.sql_commit(sql, (idlogin, username, password, fullname, empid, role, status, perms_str, userid, useredit))
        return True
    except Exception as e:
        print(f"[ERROR] save_user_permission_to_db: {e}")
        return False

def delete_user_permission_from_db(user_id):
    """ลบผู้ใช้ออกจากตาราง bk_login ใน MySQL"""
    if not mysql_db:
        return False
    try:
        if str(user_id).isdigit():
            mysql_db.sql_commit("DELETE FROM bk_login WHERE id = %s OR idlogin = %s", (int(user_id), str(user_id)))
        else:
            mysql_db.sql_commit("DELETE FROM bk_login WHERE idlogin = %s OR username = %s", (str(user_id), str(user_id)))
        return True
    except Exception as e:
        print(f"[ERROR] delete_user_permission_from_db: {e}")
        return False

@app.route("/api/roles", methods=["GET"])
def api_get_roles():
    """ดึงข้อมูลระดับบทบาท (Role) จากตาราง bk_role ใน MySQL"""
    default_roles = [
        {
            "role_code": "CEO",
            "role_name": "👔 CEO (ผู้บริหารระดับสูง)",
            "description": "ดูรายงานทั้งหมด ภาพรวมสถิติ การเงิน และความเคลื่อนไหว",
            "default_permissions": ["customer", "employee", "beneficiary", "deceased", "transaction", "movement", "view_customer", "view_employee", "view_movement", "view_transaction", "template"]
        },
        {
            "role_code": "admin",
            "role_name": "👑 admin (ผู้ดูแลระบบสูงสุด)",
            "description": "สิทธิ์เต็มทุกเมนู จัดการข้อมูล กำหนดสิทธิ์ผู้ใช้งาน และตั้งค่าระบบ",
            "default_permissions": ["running", "customer", "employee", "beneficiary", "deceased", "transaction", "movement", "view_customer", "view_employee", "view_movement", "view_transaction", "permission", "template"]
        },
        {
            "role_code": "user",
            "role_name": "👤 user (ผู้ใช้งานทั่วไป / เจ้าหน้าที่)",
            "description": "บันทึกข้อมูลสมาชิก ทำรายการ และดูรายงานทั่วไป",
            "default_permissions": ["customer", "employee", "beneficiary", "deceased", "transaction", "movement", "view_customer", "view_employee", "view_movement", "view_transaction"]
        }
    ]
    if mysql_db:
        try:
            sql = "SELECT id, role_code, role_name, description, default_permissions FROM bk_role ORDER BY id ASC"
            rows = mysql_db.sql_fetchall(sql)
            if rows:
                result = []
                for r in rows:
                    item = dict(r)
                    perms = item.get("default_permissions")
                    if perms and isinstance(perms, str):
                        try:
                            item["default_permissions"] = json.loads(perms)
                        except Exception:
                            item["default_permissions"] = [p.strip() for p in perms.split(",") if p.strip()]
                    elif not perms:
                        item["default_permissions"] = []
                    result.append(item)
                return jsonify({"status": "success", "data": result})
        except Exception as e:
            print(f"[WARN] Failed to load from bk_role: {e}")
    return jsonify({"status": "success", "data": default_roles})

@app.route("/api/user-permissions", methods=["GET"])
def api_get_user_permissions():
    users = load_user_permissions()
    return jsonify({"status": "success", "data": users})

@app.route("/api/user-permissions/save", methods=["POST"])
def api_save_user_permission():
    payload = request.get_json() or {}
    current_operator = payload.get("current_operator") or "admin"
    
    # 1. บันทึกลงตาราง bk_login ใน MySQL
    db_success = save_user_permission_to_db(payload)

    # 2. บันทึกลงไฟล์สำรอง
    users = load_user_permissions()
    user_id = str(payload.get("id") or "")
    idlogin = str(payload.get("idlogin") or "")
    found = False
    for i, u in enumerate(users):
        if str(u.get("id")) == user_id or (idlogin and str(u.get("idlogin")) == idlogin) or u.get("username") == payload.get("username"):
            payload["userid"] = u.get("userid") or payload.get("userid") or current_operator
            payload["useredit"] = payload.get("useredit") or current_operator
            users[i] = payload
            found = True
            break

    if not found:
        if not payload.get("id"):
            payload["id"] = str(len(users) + 1)
        if not payload.get("idlogin"):
            payload["idlogin"] = f"{len(users) + 1:03d}"
        payload["userid"] = payload.get("userid") or current_operator
        payload["useredit"] = payload.get("useredit") or ""
        users.append(payload)

    save_user_permissions_file(users)
    return jsonify({
        "status": "success",
        "message": "บันทึกลงตาราง bk_login ในฐานข้อมูลเรียบร้อยแล้ว",
        "data": payload,
        "db_saved": db_success
    })

@app.route("/api/user-permissions/<user_id>", methods=["DELETE"])
def api_delete_user_permission(user_id):
    # 1. ลบจากตาราง bk_login ใน MySQL
    delete_user_permission_from_db(user_id)

    # 2. ลบจากไฟล์สำรอง
    users = load_user_permissions()
    users = [u for u in users if str(u.get("id")) != str(user_id) and str(u.get("idlogin")) != str(user_id) and str(u.get("username")) != str(user_id)]
    save_user_permissions_file(users)
    return jsonify({"status": "success", "message": "ลบข้อมูลจากตาราง bk_login เรียบร้อยแล้ว"})

@app.route("/api/login", methods=["POST"])
def api_auth_login():
    """ตรวจสอบการเข้าสู่ระบบเทียบกับตาราง bk_login ในฐานข้อมูล"""
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"status": "error", "message": "กรุณากรอกชื่อผู้ใช้และรหัสผ่าน"}), 400

    # 1. ค้นหาจาก MySQL bk_login table
    if mysql_db:
        try:
            sql = "SELECT id, idlogin, username, password, fullname, empid, role, status, permissions FROM bk_login WHERE username = %s OR idlogin = %s"
            user = mysql_db.sql_fetchone(sql, (username, username))
            if not user:
                user = mysql_db.sql_fetchone("SELECT id, username, password, fullname, empid, role, status, permissions FROM login WHERE username = %s", (username,))
            if user:
                if user.get("password") != password:
                    return jsonify({"status": "error", "message": "รหัสผ่านไม่ถูกต้อง"}), 401
                if user.get("status") != "active":
                    return jsonify({"status": "error", "message": "บัญชีผู้ใช้นี้ถูกระงับการใช้งาน กรุณาติดต่อผู้ดูแลระบบ"}), 403

                perms = user.get("permissions")
                if perms and isinstance(perms, str):
                    try:
                        perms = json.loads(perms)
                    except Exception:
                        perms = [p.strip() for p in perms.split(",") if p.strip()]
                elif not perms:
                    perms = []

                return jsonify({
                    "status": "success",
                    "message": "เข้าสู่ระบบสำเร็จ",
                    "user": {
                        "id": user["id"],
                        "idlogin": user.get("idlogin") or f"{user['id']:03d}",
                        "username": user["username"],
                        "fullname": user["fullname"],
                        "empid": user.get("empid") or "",
                        "role": user.get("role") or "staff",
                        "permissions": perms
                    }
                })
        except Exception as e:
            print(f"[ERROR] api_auth_login MySQL: {e}")

    # 2. Fallback ตรวจสอบจาก memory / default users
    users = load_user_permissions()
    for u in users:
        if u.get("username") == username:
            if u.get("password") == password:
                if u.get("status") == "active":
                    return jsonify({"status": "success", "message": "เข้าสู่ระบบสำเร็จ", "user": u})
                return jsonify({"status": "error", "message": "บัญชีผู้ใช้นี้ถูกระงับการใช้งาน"}), 403
            return jsonify({"status": "error", "message": "รหัสผ่านไม่ถูกต้อง"}), 401

    return jsonify({"status": "error", "message": "ไม่พบชื่อผู้ใช้งานนี้ในระบบ"}), 404


@app.route("/DK_vendor")  
def DK_vendor(): 
    return render_template("DK_vendor.html")
@app.route("/DK_Editcustomer")
def DK_Editcustomer():
    return render_template("DK_Editcustomer.html")
@app.route("/DK_Editemployee")
def DK_Editemployee():
    return render_template("DK_Editemployee.html")

@app.route("/DK_customerDeceased")
def DK_customerDeceased():
    return render_template("DK_customerDeceased.html")



@app.route("/DK_EditcustomerDeceased")
def DK_EditcustomerDeceased():
    return render_template("DK_EditcustomerDeceased.html")

@app.route("/DK_fromvendor")  
def DK_fromvendor(): 
    return render_template("DK_fromvendor.html")
@app.route("/DK_fromcustomer")  
def DK_fromcustomer(): 
    return render_template("DK_fromcustomer.html")

@app.route("/DK_fromemployee")  
def DK_fromemployee(): 
    return render_template("DK_fromemployee.html")


@app.route("/DK_fromDeceased")  
def DK_fromDeceased(): 
    return render_template("DK_fromDeceased.html")

@app.route("/DK_Transaction")  
def DK_Transaction(): 
    return render_template("DK_Transaction.html")

@app.route("/api/transaction", methods=["GET"])
@app.route("/api/Viwetransaction", methods=["GET"])
@app.route("/Viwetransaction", methods=["GET"])
@app.route("/viwetransaction", methods=["GET"])
def api_get_transaction():
    """ดึงข้อมูลรายการตั้งสมาชิกเสียชีวิตพร้อมสถานะการรับชำระเงิน"""
    if mysql_db:
        try:
            sql = """
                SELECT 
                    t.docid,
                    t.docid as docId,
                    t.date as doc_date,
                    t.Idcustomer,
                    t.prefix,
                    t.name,
                    t.lastname,
                    t.Idcard,
                    t.dateend,
                    t.numberend,
                    t.amount as fee_per_member,
                    COALESCE(t.status, 1) as status,
                    COUNT(td.Idcustomer) as total_members,
                    COALESCE(SUM(td.amount), 0) as total_amount,
                    COALESCE(SUM(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2))), 0.00) as total_paid,
                    COALESCE(SUM(td.amount - COALESCE(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)), 0.00)), 0.00) as total_remain,
                    SUM(CASE WHEN COALESCE(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)), 0.00) >= td.amount THEN 1 ELSE 0 END) as count_paid,
                    SUM(CASE WHEN td.amount > COALESCE(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)), 0.00) THEN 1 ELSE 0 END) as count_remain
                FROM bk_transaction t
                LEFT JOIN bk_transactiondetail td ON t.docid = td.docid
                GROUP BY t.docid, t.date, t.Idcustomer, t.prefix, t.name, t.lastname, t.Idcard, t.dateend, t.numberend, t.amount, t.status
                ORDER BY t.date DESC, t.docid DESC
            """
            rows = mysql_db.sql_fetchall(sql)
            results = []
            for r in (rows or []):
                doc_status = int(r.get("status") or 1)
                tot_amt = float(r.get("total_amount") or 0)
                tot_paid = float(r.get("total_paid") or 0)
                tot_remain = float(r.get("total_remain") or 0)
                cnt_paid = int(r.get("count_paid") or 0)
                cnt_remain = int(r.get("count_remain") or 0)
                tot_members = int(r.get("total_members") or 0)

                if doc_status == 2:
                    payment_status = "cancelled"
                    status_text = "ยกเลิกรายการ"
                elif tot_paid > 0 and tot_remain > 0:
                    payment_status = "partial"
                    status_text = "รับชำระบางส่วน"
                elif tot_paid > 0 and tot_remain <= 0:
                    payment_status = "paid"
                    status_text = "รับชำระครบแล้ว"
                else:
                    payment_status = "unpaid"
                    status_text = "ยังไม่ได้รับชำระ"

                results.append({
                    "docid": r.get("docid"),
                    "docId": r.get("docid"),
                    "doc_date": r.get("doc_date").strftime("%Y-%m-%d") if r.get("doc_date") and hasattr(r.get("doc_date"), "strftime") else str(r.get("doc_date") or ""),
                    "Idcustomer": r.get("Idcustomer") or "",
                    "prefix": r.get("prefix") or "",
                    "name": r.get("name") or "",
                    "lastname": r.get("lastname") or "",
                    "Idcard": r.get("Idcard") or "",
                    "dateend": r.get("dateend").strftime("%Y-%m-%d") if r.get("dateend") and hasattr(r.get("dateend"), "strftime") else str(r.get("dateend") or ""),
                    "numberend": r.get("numberend") or "-",
                    "status": doc_status,
                    "payment_status": payment_status,
                    "status_text": status_text,
                    "fee_per_member": float(r.get("fee_per_member") or 0),
                    "total_members": tot_members,
                    "total_amount": tot_amt,
                    "total_paid": tot_paid,
                    "total_remain": tot_remain,
                    "count_paid": cnt_paid,
                    "count_remain": cnt_remain
                })
            return jsonify({"error": "0", "results": results})
        except Exception as e:
            print(f"[ERROR] api_get_transaction: {e}")
            return jsonify({"error": "1", "message": str(e), "results": []}), 500
    return jsonify({"error": "1", "message": "ฐานข้อมูลไม่พร้อมใช้งาน", "results": []}), 500

def get_transaction1_data(docid):
    """ฟังก์ชันดึงข้อมูลเอกสารตั้งหนี้และรายละเอียดสมาชิกจากฐานข้อมูล (bk_transaction + bk_transactiondetail)"""
    if not mysql_db:
        return None
    try:
        clean_docid = str(docid or "").strip()
        if not clean_docid:
            return None
        sql_header = """
            SELECT docid, date, amount, Idcustomer, prefix, name, lastname, Idcard, dateend, numberend, status
            FROM bk_transaction
            WHERE LOWER(TRIM(docid)) = LOWER(TRIM(%s))
               OR LOWER(TRIM(numberend)) = LOWER(TRIM(%s))
            ORDER BY CASE WHEN LOWER(TRIM(docid)) = LOWER(TRIM(%s)) THEN 0 ELSE 1 END
            LIMIT 1
        """
        header = mysql_db.sql_fetchone(sql_header, (clean_docid, clean_docid, clean_docid))
        if not header:
            return None

        h_dict = dict(header)
        actual_docid = h_dict.get("docid") or clean_docid
        h_dict["amount"] = float(h_dict.get("amount") or 0)
        h_dict["status"] = int(h_dict.get("status") or 1)
        if h_dict.get("date") and hasattr(h_dict["date"], "strftime"):
            h_dict["date"] = h_dict["date"].strftime("%Y-%m-%d")
        else:
            h_dict["date"] = str(h_dict.get("date") or "")
        if h_dict.get("dateend") and hasattr(h_dict["dateend"], "strftime"):
            h_dict["dateend"] = h_dict["dateend"].strftime("%Y-%m-%d")
        else:
            h_dict["dateend"] = str(h_dict.get("dateend") or "")

        numend_val = str(h_dict.get("numberend") or "")

        raw_details = None
        try:
            sql_detail = """
                SELECT 
                    td.docid, 
                    td.Idcustomer, 
                    COALESCE(NULLIF(td.prefix, ''), c.prefix, '') as prefix, 
                    COALESCE(NULLIF(td.name, ''), c.name, '') as name, 
                    COALESCE(NULLIF(td.lastname, ''), c.lastname, '') as lastname, 
                    COALESCE(NULLIF(td.numberend, ''), %s, '') as numberend, 
                    td.amount, 
                    COALESCE(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)), 0.00) as payamount, 
                    COALESCE(td.status, 1) as status
                FROM bk_transactiondetail td
                LEFT JOIN bk_customer c ON td.Idcustomer = c.Idcustomer
                WHERE LOWER(TRIM(td.docid)) = LOWER(TRIM(%s))
                ORDER BY td.Idcustomer ASC
            """
            raw_details = mysql_db.sql_fetchall(sql_detail, (numend_val, actual_docid))
        except Exception as ex_join:
            print(f"[WARN] get_transaction1_data join error: {ex_join}")
            raw_details = None

        if raw_details is None:
            sql_detail_fallback = """
                SELECT 
                    docid, 
                    Idcustomer, 
                    COALESCE(prefix, '') as prefix, 
                    COALESCE(name, '') as name, 
                    COALESCE(lastname, '') as lastname, 
                    COALESCE(NULLIF(numberend, ''), %s, '') as numberend, 
                    amount, 
                    COALESCE(CAST(NULLIF(payamount, '') AS DECIMAL(10,2)), 0.00) as payamount, 
                    COALESCE(status, 1) as status
                FROM bk_transactiondetail
                WHERE LOWER(TRIM(docid)) = LOWER(TRIM(%s))
                ORDER BY Idcustomer ASC
            """
            raw_details = mysql_db.sql_fetchall(sql_detail_fallback, (numend_val, actual_docid)) or []

        details = []
        fee_default = h_dict.get("amount") or 0.0
        for r in (raw_details or []):
            item = dict(r)
            item["amount"] = float(item.get("amount") or fee_default)
            item["payamount"] = float(item.get("payamount") or 0.0)
            item["status"] = int(item.get("status") or 1)
            details.append(item)

        h_dict["details"] = details
        return h_dict
    except Exception as e:
        print(f"[ERROR] get_transaction1_data: {e}")
        return None

@app.route("/api/transaction1/<path:docid>", methods=["GET"])
@app.route("/transaction1/<path:docid>", methods=["GET"])
def api_get_transaction1_by_id(docid):
    """ดึงข้อมูลเอกสารตั้งหนี้และตารางคำนวณรายละเอียดสมาชิก (bk_transaction + bk_transactiondetail)"""
    data = get_transaction1_data(docid)
    if not data:
        return jsonify({"error": "1", "message": f"ไม่พบเอกสาร {docid}"}), 404
    return jsonify({
        "error": "0",
        "results": data
    })

@app.route("/DK_showTransaction")  
def DK_showTransaction(): 
    return render_template("DK_showTransaction.html")



@app.route("/DK_EditTransaction")  
def DK_EditTransaction(): 
    return render_template("DK_EditTransaction.html")

@app.route("/DK_cancelTransaction")  
def DK_cancelTransaction(): 
    return render_template("DK_cancelTransaction.html")


@app.route("/DK_Viwecustomer")  
def DK_Viwecustomer(): 
    return render_template("DK_Viwecustomer.html")

@app.route("/DK_Viweemployee")  
def DK_Viweemployee(): 
    return render_template("DK_Viweemployee.html")

@app.route("/DK_ViweMovement")
def DK_ViweMovement():
    return render_template("DK_ViweMovement.html")

@app.route("/DK_ViweTransaction")
def DK_ViweTransaction():
    docid = request.args.get("docid") or request.args.get("docId") or request.args.get("id") or request.args.get("numberend") or request.args.get("numend") or ""
    initial_data = None
    if docid:
        initial_data = get_transaction1_data(docid)
    return render_template("DK_ViweTransaction.html", initial_data=initial_data)

@app.route("/api/person_debt_summary", methods=["GET"])
def api_person_debt_summary():
    """ดึงข้อมูลสรุปภาระหนี้เงินสงเคราะห์รายบุคคลของสมาชิกทุกคน (ค้างกี่ศพ, ยอดค้างชำระ)"""
    if not mysql_db:
        return jsonify({"error": "1", "message": "ฐานข้อมูลไม่พร้อมใช้งาน", "results": []}), 500
    try:
        search_kw = (request.args.get("search") or "").strip().lower()
        filter_status = (request.args.get("status") or "all").strip().lower()
        idcustomer_param = (request.args.get("idcustomer") or "").strip()

        # ดึงสมาชิกพร้อมข้อมูลสรุปยอดหนี้รายศพ (เฉพาะเอกสารตั้งหนี้ที่ไม่ถูกยกเลิก status != 2)
        sql = """
            SELECT 
                c.Idcustomer,
                COALESCE(c.prefix, '') as prefix,
                COALESCE(c.name, '') as name,
                COALESCE(c.lastname, '') as lastname,
                COALESCE(c.Idcard, '') as Idcard,
                COALESCE(c.Tel, '') as Tel,
                COALESCE(c.date, '') as register_date,
                COALESCE(c.status, 1) as member_status,
                COUNT(t.docid) as total_cases,
                SUM(CASE WHEN t.docid IS NOT NULL AND COALESCE(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)), 0.00) >= td.amount THEN 1 ELSE 0 END) as count_paid_cases,
                SUM(CASE WHEN t.docid IS NOT NULL AND td.amount > COALESCE(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)), 0.00) THEN 1 ELSE 0 END) as count_unpaid_cases,
                COALESCE(SUM(CASE WHEN t.docid IS NOT NULL THEN td.amount ELSE 0.00 END), 0.00) as total_amount,
                COALESCE(SUM(CASE WHEN t.docid IS NOT NULL THEN CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)) ELSE 0.00 END), 0.00) as total_paid,
                COALESCE(SUM(CASE WHEN t.docid IS NOT NULL THEN (td.amount - COALESCE(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)), 0.00)) ELSE 0.00 END), 0.00) as total_remain
            FROM bk_customer c
            LEFT JOIN bk_transactiondetail td ON c.Idcustomer = td.Idcustomer
            LEFT JOIN bk_transaction t ON td.docid = t.docid AND t.status != 2
            GROUP BY c.Idcustomer, c.prefix, c.name, c.lastname, c.Idcard, c.Tel, c.date, c.status
            ORDER BY count_unpaid_cases DESC, c.Idcustomer ASC
        """
        rows = mysql_db.sql_fetchall(sql) or []
        results = []
        for r in rows:
            tot_cases = int(r.get("total_cases") or 0)
            cnt_paid = int(r.get("count_paid_cases") or 0)
            cnt_unpaid = int(r.get("count_unpaid_cases") or 0)
            tot_amt = float(r.get("total_amount") or 0)
            tot_p = float(r.get("total_paid") or 0)
            tot_rem = float(r.get("total_remain") or 0)

            cust_id = str(r.get("Idcustomer") or "")
            prefix = str(r.get("prefix") or "")
            name = str(r.get("name") or "")
            lastname = str(r.get("lastname") or "")
            fullname = f"{prefix}{name} {lastname}".strip()
            idcard = str(r.get("Idcard") or "")
            tel = str(r.get("Tel") or "")
            reg_date = r.get("register_date")
            if reg_date and hasattr(reg_date, "strftime"):
                reg_date_str = reg_date.strftime("%Y-%m-%d")
            else:
                reg_date_str = str(reg_date or "")

            if idcustomer_param and cust_id.lower() != idcustomer_param.lower():
                continue

            if search_kw:
                combined = f"{cust_id} {fullname} {idcard} {tel}".lower()
                if search_kw not in combined:
                    continue

            if filter_status == "unpaid" and cnt_unpaid <= 0:
                continue
            if filter_status == "paid" and (cnt_unpaid > 0 or tot_cases == 0):
                continue

            results.append({
                "Idcustomer": cust_id,
                "prefix": prefix,
                "name": name,
                "lastname": lastname,
                "fullname": fullname,
                "Idcard": idcard,
                "Tel": tel,
                "register_date": reg_date_str,
                "member_status": int(r.get("member_status") or 1),
                "total_cases": tot_cases,
                "count_paid_cases": cnt_paid,
                "count_unpaid_cases": cnt_unpaid,
                "total_amount": tot_amt,
                "total_paid": tot_p,
                "total_remain": tot_rem
            })

        return jsonify({"error": "0", "results": results, "total": len(results)})
    except Exception as e:
        print(f"[ERROR] api_person_debt_summary: {e}")
        return jsonify({"error": "1", "message": str(e), "results": []}), 500


@app.route("/api/person_debt_detail/<idcustomer>", methods=["GET"])
def api_person_debt_detail(idcustomer):
    """ดึงรายละเอียดรายการศพทั้งหมดของสมาชิกรายนั้นๆ พร้อมสถานะการชำระและยอดค้างแต่ละศพ"""
    if not mysql_db:
        return jsonify({"error": "1", "message": "ฐานข้อมูลไม่พร้อมใช้งาน"}), 500
    try:
        clean_id = str(idcustomer or "").strip()
        if not clean_id:
            return jsonify({"error": "1", "message": "ไม่ได้ระบุรหัสสมาชิก"}), 400

        # ข้อมูลสมาชิก
        cust_row = mysql_db.sql_fetchone("""
            SELECT Idcustomer, prefix, name, lastname, Idcard, Tel, date, status
            FROM bk_customer
            WHERE LOWER(TRIM(Idcustomer)) = LOWER(TRIM(%s))
            LIMIT 1
        """, (clean_id,))
        if not cust_row:
            cust_row = mysql_db.sql_fetchone("""
                SELECT Idcustomer, prefix, name, lastname, Idcard, Tel, date, status
                FROM customer
                WHERE LOWER(TRIM(Idcustomer)) = LOWER(TRIM(%s))
                LIMIT 1
            """, (clean_id,))

        if not cust_row:
            return jsonify({"error": "1", "message": f"ไม่พบข้อมูลสมาชิก {clean_id}"}), 404

        cust_data = dict(cust_row)
        reg_d = cust_data.get("date")
        cust_data["register_date"] = reg_d.strftime("%Y-%m-%d") if reg_d and hasattr(reg_d, "strftime") else str(reg_d or "")
        cust_data["fullname"] = f"{cust_data.get('prefix') or ''}{cust_data.get('name') or ''} {cust_data.get('lastname') or ''}".strip()

        # รายการศพทั้งหมดที่ถูกเรียกเก็บ (เฉพาะ t.status != 2)
        sql_cases = """
            SELECT 
                td.docid,
                t.date as doc_date,
                t.numberend,
                t.dateend,
                t.Idcustomer as deceased_id,
                COALESCE(t.prefix, '') as deceased_prefix,
                COALESCE(t.name, '') as deceased_name,
                COALESCE(t.lastname, '') as deceased_lastname,
                td.amount,
                COALESCE(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)), 0.00) as payamount,
                GREATEST(0.00, td.amount - COALESCE(CAST(NULLIF(td.payamount, '') AS DECIMAL(10,2)), 0.00)) as remain,
                COALESCE(t.status, 1) as case_status
            FROM bk_transactiondetail td
            JOIN bk_transaction t ON td.docid = t.docid AND t.status != 2
            WHERE LOWER(TRIM(td.Idcustomer)) = LOWER(TRIM(%s))
            ORDER BY t.date DESC, t.docid DESC
        """
        case_rows = mysql_db.sql_fetchall(sql_cases, (clean_id,)) or []

        cases = []
        tot_cases = 0
        cnt_paid = 0
        cnt_unpaid = 0
        sum_billed = 0.0
        sum_paid = 0.0
        sum_remain = 0.0

        for r in case_rows:
            amt = float(r.get("amount") or 0)
            paid = float(r.get("payamount") or 0)
            remain = float(r.get("remain") or 0)
            is_paid = (remain <= 0)
            is_partial = (paid > 0 and remain > 0)

            tot_cases += 1
            sum_billed += amt
            sum_paid += paid
            sum_remain += remain

            if is_paid:
                cnt_paid += 1
                status_code = "paid"
                status_name = "ชำระแล้ว"
            elif is_partial:
                cnt_unpaid += 1
                status_code = "partial"
                status_name = "ชำระบางส่วน"
            else:
                cnt_unpaid += 1
                status_code = "unpaid"
                status_name = "ค้างชำระ"

            doc_d = r.get("doc_date")
            doc_date_str = doc_d.strftime("%Y-%m-%d") if doc_d and hasattr(doc_d, "strftime") else str(doc_d or "")

            date_e = r.get("dateend")
            dateend_str = date_e.strftime("%Y-%m-%d") if date_e and hasattr(date_e, "strftime") else str(date_e or "")

            dec_prefix = str(r.get("deceased_prefix") or "")
            dec_name = str(r.get("deceased_name") or "")
            dec_last = str(r.get("deceased_lastname") or "")
            dec_fullname = f"{dec_prefix}{dec_name} {dec_last}".strip()

            cases.append({
                "docid": r.get("docid"),
                "doc_date": doc_date_str,
                "numberend": r.get("numberend") or "-",
                "dateend": dateend_str,
                "deceased_id": r.get("deceased_id") or "",
                "deceased_name": dec_fullname,
                "amount": amt,
                "payamount": paid,
                "remain": remain,
                "status_code": status_code,
                "status_name": status_name
            })

        summary = {
            "total_cases": tot_cases,
            "count_paid_cases": cnt_paid,
            "count_unpaid_cases": cnt_unpaid,
            "total_amount": sum_billed,
            "total_paid": sum_paid,
            "total_remain": sum_remain
        }

        return jsonify({
            "error": "0",
            "customer": cust_data,
            "summary": summary,
            "cases": cases
        })
    except Exception as e:
        print(f"[ERROR] api_person_debt_detail: {e}")
        return jsonify({"error": "1", "message": str(e)}), 500


@app.route("/DK_Viweperson")
def DK_Viweperson():
    idcustomer = request.args.get("idcustomer") or request.args.get("id") or request.args.get("Idcustomer") or ""
    return render_template("DK_Viweperson.html", selected_idcustomer=idcustomer)




@app.route("/DK_Movement")  
def DK_Movement(): 
    return render_template("DK_Movement.html")

@app.route("/DK_showMovement")  
def DK_showMovement(): 
    return render_template("DK_showMovement.html")


@app.route("/DK_fromUserPermission")  
def DK_fromUserPermission(): 
    return render_template("DK_fromUserPermission.html")

@app.route("/DK_tempagemaster")  
def DK_tempagemaster(): 
    return render_template("DK_tempagemaster.html")


# ==========================================
# GL_PERIOD DATABASE SCHEMA & APIs (รอบบัญชี)
# ==========================================
def get_gl_period_table_name():
    """หาชื่อตารางที่แท้จริงในฐานข้อมูล ไม่ว่าจะชื่อ gl_period หรือ GL_Period"""
    if not mysql_db:
        return "gl_period"
    try:
        tables = mysql_db.sql_fetchall("SHOW TABLES") or []
        for t in tables:
            for val in t.values():
                if str(val).lower() == "gl_period":
                    return str(val)
    except Exception as e:
        print(f"[WARN] get_gl_period_table_name error: {e}")
    return "gl_period"

def db_execute_commit(sql, params=None):
    """รันคำสั่ง SQL COMMIT พร้อมคืนค่า (is_success, error_message) อย่างปลอดภัย"""
    conn = None
    try:
        import connect_db
        conn = connect_db._get_connection()
        with conn.cursor() as cur:
            if params:
                cur.execute(sql, params)
            else:
                cur.execute(sql)
            conn.commit()
            return True, None
    except Exception as e:
        print(f"[ERROR] db_execute_commit: {e} | SQL: {sql}")
        return False, str(e)
    finally:
        if conn and hasattr(conn, "open") and conn.open:
            try:
                conn.close()
            except Exception:
                pass

def ensure_schema_gl_period():
    """ตรวจสอบและสร้าง/อัปเดตโครงสร้างตาราง gl_period (กำหนดให้อยู่ในรูปแบบ 1 แถวเท่านั้น), gl_period_config, gl_chart ในฐานข้อมูล"""
    if not mysql_db:
        return
    try:
        now_thai_year = datetime.now().year + 543
        check = mysql_db.sql_fetchall("SHOW TABLES LIKE 'gl_period'")
        if not check:
            check = mysql_db.sql_fetchall("SHOW TABLES LIKE 'GL_Period'")
        if not check:
            mysql_db.sql_commit("""
                CREATE TABLE IF NOT EXISTS GL_Period (
                    CurentYear VARCHAR(50) NOT NULL PRIMARY KEY DEFAULT '2569',
                    PeriodPerYear INT NOT NULL DEFAULT 12,
                    AC_ProfitLose VARCHAR(50) DEFAULT NULL,
                    AC_ProfitACC VARCHAR(50) DEFAULT NULL,
                    AC_CostSale VARCHAR(50) DEFAULT NULL,
                    AC_CostProduct VARCHAR(50) DEFAULT NULL,
                    BookBuy VARCHAR(50) DEFAULT NULL,
                    BookGL VARCHAR(50) DEFAULT NULL,
                    Period_1 DATETIME DEFAULT NULL,
                    Period_2 DATETIME DEFAULT NULL,
                    Period_3 DATETIME DEFAULT NULL,
                    Period_4 DATETIME DEFAULT NULL,
                    Period_5 DATETIME DEFAULT NULL,
                    Period_6 DATETIME DEFAULT NULL,
                    Period_7 DATETIME DEFAULT NULL,
                    Period_8 DATETIME DEFAULT NULL,
                    Period_9 DATETIME DEFAULT NULL,
                    Period_10 DATETIME DEFAULT NULL,
                    Period_11 DATETIME DEFAULT NULL,
                    Period_12 DATETIME DEFAULT NULL,
                    Period_13 DATETIME DEFAULT NULL,
                    AmountTrans REAL DEFAULT NULL,
                    USERCREATE VARCHAR(20) DEFAULT NULL,
                    DATECREATE DATETIME DEFAULT NULL,
                    ST1 INT DEFAULT 1,
                    ST2 INT DEFAULT 1,
                    ST3 INT DEFAULT 1,
                    ST4 INT DEFAULT 1,
                    ST5 INT DEFAULT 1,
                    ST6 INT DEFAULT 1,
                    ST7 INT DEFAULT 1,
                    ST8 INT DEFAULT 1,
                    ST9 INT DEFAULT 1,
                    ST10 INT DEFAULT 1,
                    ST11 INT DEFAULT 1,
                    ST12 INT DEFAULT 1,
                    DepId VARCHAR(10) DEFAULT NULL,
                    acc_group VARCHAR(20) DEFAULT '01',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            print("[SCHEMA] Created table GL_Period successfully (Standard 37 Columns Schema)")
        else:
            existing_cols = [str(c.get("Field") or c.get("field") or "").lower() for c in (mysql_db.sql_fetchall("SHOW COLUMNS FROM gl_period") or mysql_db.sql_fetchall("SHOW COLUMNS FROM GL_Period") or [])]
            col_defs = {
                "PeriodPerYear": "INT NOT NULL DEFAULT 12",
                "AC_ProfitLose": "VARCHAR(50) DEFAULT NULL",
                "AC_ProfitACC": "VARCHAR(50) DEFAULT NULL",
                "AC_CostSale": "VARCHAR(50) DEFAULT NULL",
                "AC_CostProduct": "VARCHAR(50) DEFAULT NULL",
                "BookBuy": "VARCHAR(50) DEFAULT NULL",
                "BookGL": "VARCHAR(50) DEFAULT NULL",
                "CurentYear": "VARCHAR(50) NOT NULL DEFAULT '2569'",
                "AmountTrans": "REAL DEFAULT NULL",
                "USERCREATE": "VARCHAR(20) DEFAULT NULL",
                "DATECREATE": "DATETIME DEFAULT NULL",
                "DepId": "VARCHAR(10) DEFAULT NULL",
                "year_be": "INT(11) DEFAULT 2569",
                "year": "INT(11) DEFAULT 2569",
                "end_year_be": "INT(11) DEFAULT 2569",
                "total_periods": "INT(11) DEFAULT 12",
                "acc_group": "VARCHAR(20) DEFAULT '01'",
                "profit_loss_acc": "VARCHAR(50) DEFAULT '3800'",
                "retained_earnings_acc": "VARCHAR(50) DEFAULT '3700'",
                "retained_earnings_name": "VARCHAR(150) DEFAULT 'กำไรสะสม'",
                "cusid": "VARCHAR(50) DEFAULT '00001'",
                "periods_json": "LONGTEXT DEFAULT NULL"
            }
            for i in range(1, 14):
                col_defs[f"Period_{i}"] = "DATETIME DEFAULT NULL"
            for i in range(1, 13):
                col_defs[f"ST{i}"] = "INT DEFAULT 1"
                col_defs[f"day{i}"] = "INT(11) DEFAULT NULL"
                col_defs[f"month{i}"] = "INT(11) DEFAULT NULL"
                col_defs[f"year{i}"] = "INT(11) DEFAULT NULL"
                col_defs[f"can_edit{i}"] = "TINYINT(1) DEFAULT 1"
                col_defs[f"date{i}"] = "DATE DEFAULT NULL"

            # ลบ profit_loss_name ออก ไม่ต้องเก็บลงฐานข้อมูล
            if "profit_loss_name" in existing_cols:
                try:
                    mysql_db.sql_commit("ALTER TABLE gl_period DROP COLUMN profit_loss_name")
                    print("[SCHEMA] Dropped column 'profit_loss_name' from gl_period (ไม่ต้องเก็บลงฐาน)")
                except Exception as ex_drop:
                    print(f"[WARN] Drop profit_loss_name error: {ex_drop}")

            for col, dtype in col_defs.items():
                if col.lower() not in existing_cols:
                    try:
                        mysql_db.sql_commit(f"ALTER TABLE gl_period ADD COLUMN {col} {dtype}")
                        print(f"[SCHEMA] Added missing column '{col}' to gl_period")
                    except Exception as ex_c:
                        print(f"[WARN] Failed to add column {col} to gl_period: {ex_c}")

        actual_tbl = get_gl_period_table_name()
        cols_now = [str(c.get("Field") or c.get("field") or "").lower() for c in (mysql_db.sql_fetchall(f"SHOW COLUMNS FROM {actual_tbl}") or [])]
        existing_row = mysql_db.sql_fetchone(f"SELECT * FROM {actual_tbl} LIMIT 1")
        if existing_row:
            # ตรวจสอบแถวเดิมที่มี หาก DepId เป็น '00001' หรือว่าง ให้แก้เป็น '01' (กลุ่มบัญชี)
            if "depid" in cols_now:
                dep_val = str(existing_row.get("DepId") or existing_row.get("depid") or "")
                if dep_val in ["00001", "", "None", "null"] or not dep_val:
                    grp = str(existing_row.get("acc_group") or "01")
                    if "id" in cols_now and existing_row.get("id"):
                        db_execute_commit(f"UPDATE {actual_tbl} SET DepId = %s WHERE id = %s", (grp, existing_row["id"]))
                    elif "CurentYear" in existing_row and existing_row.get("CurentYear"):
                        db_execute_commit(f"UPDATE {actual_tbl} SET DepId = %s WHERE CurentYear = %s", (grp, existing_row["CurentYear"]))
                    else:
                        db_execute_commit(f"UPDATE {actual_tbl} SET DepId = %s", (grp,))

        # ตรวจสอบและสร้างตาราง gl_chart (ผังบัญชี)
        mysql_db.sql_commit("""
            CREATE TABLE IF NOT EXISTS gl_chart (
                acc_code VARCHAR(50) NOT NULL PRIMARY KEY,
                acc_name VARCHAR(200) NOT NULL,
                acc_type VARCHAR(50) NOT NULL DEFAULT 'สินทรัพย์',
                acc_category_no INT NOT NULL DEFAULT 1,
                branch_code VARCHAR(20) NOT NULL DEFAULT '01',
                branch_name VARCHAR(150) NOT NULL DEFAULT 'สถาบันการเงิน',
                acc_group VARCHAR(20) NOT NULL DEFAULT '01',
                acc_group_name VARCHAR(150) NOT NULL DEFAULT 'บัญชี 1',
                balance_side VARCHAR(20) NOT NULL DEFAULT 'debit',
                opening_balance DECIMAL(15,2) NOT NULL DEFAULT 0.00,
                status TINYINT(1) NOT NULL DEFAULT 1,
                cusid VARCHAR(50) DEFAULT '00001'
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)

        chart_cols = [str(c.get("Field") or c.get("field") or "").lower() for c in (mysql_db.sql_fetchall("SHOW COLUMNS FROM gl_chart") or [])]
        extra_chart_cols = {
            "acc_category_no": "INT NOT NULL DEFAULT 1",
            "branch_code": "VARCHAR(20) NOT NULL DEFAULT '01'",
            "branch_name": "VARCHAR(150) NOT NULL DEFAULT 'สถาบันการเงิน'",
            "acc_group_name": "VARCHAR(150) NOT NULL DEFAULT 'บัญชี 1'",
            "balance_side": "VARCHAR(20) NOT NULL DEFAULT 'debit'",
            "opening_balance": "DECIMAL(15,2) NOT NULL DEFAULT 0.00"
        }
        for c_name, c_def in extra_chart_cols.items():
            if c_name.lower() not in chart_cols:
                try:
                    mysql_db.sql_commit(f"ALTER TABLE gl_chart ADD COLUMN {c_name} {c_def}")
                except Exception:
                    pass

    except Exception as e:
        print(f"[WARN] ensure_schema_gl_period error: {e}")

try:
    ensure_schema_gl_period()
except Exception as _ex_schema_init:
    print(f"[WARN] Initial ensure_schema_gl_period call failed: {_ex_schema_init}")

def normalize_be_year(raw_val, default_be=None):
    """แปลงค่าปีให้เป็น พ.ศ. (เช่น 2569) เสมอ โดยไม่บวก 543 ซ้ำซ้อน และซ่อมค่าปีที่เพี้ยน"""
    if default_be is None:
        default_be = datetime.now().year + 543
    try:
        y = int(str(raw_val).strip())
        if 2450 <= y <= 2700:
            return y
        if 1950 <= y <= 2150:
            return y + 543
    except Exception:
        pass
    return int(default_be)

def get_max_days_in_month(month_no, be_year):
    """คืนค่าจำนวนวันสูงสุดของเดือนนั้นๆ (คำนวณปีอธิกสุรทินจากปี ค.ศ.)"""
    ce_y = int(be_year) - 543 if int(be_year) > 2400 else int(be_year)
    m = int(month_no)
    if m == 2:
        is_leap = (ce_y % 4 == 0 and ce_y % 100 != 0) or (ce_y % 400 == 0)
        return 29 if is_leap else 28
    if m in (4, 6, 9, 11):
        return 30
    return 31

def is_valid_period_year(raw_val):
    """ตรวจสอบว่าค่าปีอยู่ในเกณฑ์ปกติ (ค.ศ. 1950-2150 หรือ พ.ศ. 2450-2700)"""
    try:
        y = int(str(raw_val).strip())
        return (1950 <= y <= 2150) or (2450 <= y <= 2700)
    except Exception:
        return False

def get_gl_period_record(target_year_param=None):
    """ฟังก์ชันกลางสำหรับดึงข้อมูลรอบบัญชี gl_period (1 Row) พร้อมแปลงวันที่ทั้ง 12 งวดให้สมบูรณ์เป็น พ.ศ. เสมอ"""
    thai_months = [
        (1, "มกราคม", 31),
        (2, "กุมภาพันธ์", 28),
        (3, "มีนาคม", 31),
        (4, "เมษายน", 30),
        (5, "พฤษภาคม", 31),
        (6, "มิถุนายน", 30),
        (7, "กรกฎาคม", 31),
        (8, "สิงหาคม", 31),
        (9, "กันยายน", 30),
        (10, "ตุลาคม", 31),
        (11, "พฤศจิกายน", 30),
        (12, "ธันวาคม", 31)
    ]
    now_be = datetime.now().year + 543
    actual_tbl = get_gl_period_table_name()
    row = mysql_db.sql_fetchone(f"SELECT * FROM {actual_tbl} LIMIT 1") if mysql_db else None

    # ถ้ายังไม่มีข้อมูลในฐานข้อมูล (row เป็น None หรือว่าง) ให้แสดง form เปล่า ทั้งหมด
    if not row or not any(row.values()):
        periods_empty = []
        for m_no, m_name, def_days in thai_months:
            periods_empty.append({
                "period_no": m_no,
                "day": "",
                "month": m_no,
                "month_name": m_name,
                "year": "",
                "can_edit": False,
                "thai_date": "",
                "ad_date": "",
                "date": ""
            })
        return {
            "row": None,
            "exists": False,
            "year": "",
            "db_year": "",
            "total_periods": "",
            "acc_group": "",
            "profit_loss_acc": "",
            "retained_earnings_acc": "",
            "retained_earnings_name": "",
            "periods": periods_empty
        }

    db_year = normalize_be_year(row.get("CurentYear") or row.get("year_be") or row.get("year"), now_be)
    target_year = normalize_be_year(target_year_param, db_year) if (target_year_param and str(target_year_param).isdigit()) else db_year

    acc_group = str(row.get("DepId") or row.get("depid") or row.get("acc_group") or "01")
    profit_loss_acc = str(row.get("AC_ProfitLose") or row.get("ac_profitlose") or row.get("profit_loss_acc") or "3800")
    retained_earnings_acc = str(row.get("AC_ProfitACC") or row.get("ac_profitacc") or row.get("retained_earnings_acc") or "3700")
    retained_earnings_name = str(row.get("retained_earnings_name") or "กำไรสะสม")
    total_periods = int(row.get("PeriodPerYear") or row.get("periodperyear") or row.get("total_periods") or 12)

    # ดึงงวดจาก periods_json
    p_map = {}
    if row.get("periods_json"):
        try:
            pj = json.loads(row["periods_json"])
            if isinstance(pj, list):
                for p in pj:
                    p_no = int(p.get("period_no") or 0)
                    if 1 <= p_no <= 12:
                        p_map[p_no] = p
        except Exception as e_pj:
            print(f"[WARN] Failed to parse periods_json: {e_pj}")

    periods_12 = []
    needs_db_repair = False

    for m_no, m_name, def_days in thai_months:
        p_data = p_map.get(m_no, {})
        d_val = None
        mo_val = None
        y_val = None
        raw_d = None
        year_corrupted = False

        # 1. ตรวจสอบวันที่จากคอลัมน์มาตรฐาน Period_1..12 เป็นอันดับแรก
        if row.get(f"Period_{m_no}"):
            raw_d = row.get(f"Period_{m_no}")
        elif row.get(f"period_{m_no}"):
            raw_d = row.get(f"period_{m_no}")
        elif p_data.get("date"):
            raw_d = p_data.get("date")
        elif row.get(f"date{m_no}"):
            raw_d = row.get(f"date{m_no}")
        elif m_no == 1 and row.get("date"):
            raw_d = row.get("date")
        elif m_no == 12 and row.get("end_date"):
            raw_d = row.get("end_date")

        if raw_d:
            if hasattr(raw_d, "year") and hasattr(raw_d, "month") and hasattr(raw_d, "day"):
                if is_valid_period_year(raw_d.year):
                    d_val = raw_d.day
                    mo_val = raw_d.month
                    y_val = normalize_be_year(raw_d.year, target_year)
                else:
                    year_corrupted = True
            elif isinstance(raw_d, str) and "-" in raw_d:
                parts = raw_d.strip().split("-")
                if len(parts) >= 3:
                    try:
                        c_y = int(parts[0])
                        if is_valid_period_year(c_y):
                            mo_val = int(parts[1])
                            d_val = int(parts[2].split()[0].split("T")[0])
                            y_val = normalize_be_year(c_y, target_year)
                        else:
                            year_corrupted = True
                    except Exception:
                        year_corrupted = True
            elif isinstance(raw_d, str) and "/" in raw_d:
                parts = raw_d.strip().split("/")
                if len(parts) >= 3:
                    try:
                        c_y = int(parts[2])
                        if is_valid_period_year(c_y):
                            d_val = int(parts[0])
                            mo_val = int(parts[1])
                            y_val = normalize_be_year(c_y, target_year)
                        else:
                            year_corrupted = True
                    except Exception:
                        year_corrupted = True

        # 2. ถ้าค่าปีเพี้ยน (เช่น 1086, 1629 จากบั๊กเก่าที่ส่งวัน=31 ในเดือนที่มี 28/30 วัน) ให้รีเซ็ตเป็นวันสิ้นเดือนของงวดนั้นในปี พ.ศ. ปัจจุบัน
        if year_corrupted:
            needs_db_repair = True
            y_val = target_year
            mo_val = m_no
            d_val = get_max_days_in_month(m_no, target_year)
        else:
            if not y_val:
                cand_y = p_data.get("year") or row.get(f"year{m_no}")
                if cand_y and is_valid_period_year(cand_y):
                    y_val = normalize_be_year(cand_y, target_year)
                else:
                    if cand_y:
                        needs_db_repair = True
                    y_val = target_year

            if not mo_val:
                if p_data.get("month"):
                    mo_val = int(p_data.get("month"))
                elif row.get(f"month{m_no}"):
                    mo_val = int(row.get(f"month{m_no}"))
                elif m_no == 1 and row.get("month"):
                    mo_val = int(row.get("month"))
                elif m_no == 12 and row.get("end_month"):
                    mo_val = int(row.get("end_month"))
                else:
                    mo_val = m_no

            if not d_val:
                if p_data.get("day"):
                    d_val = int(p_data.get("day"))
                elif row.get(f"day{m_no}"):
                    d_val = int(row.get(f"day{m_no}"))
                elif m_no == 1 and row.get("day"):
                    d_val = int(row.get("day"))
                elif m_no == 12 and row.get("end_day"):
                    d_val = int(row.get("end_day"))
                else:
                    d_val = get_max_days_in_month(mo_val, y_val)

        be_y = normalize_be_year(y_val, target_year)
        ce_y = be_y - 543
        mo_int = max(1, min(12, int(mo_val)))
        max_d = get_max_days_in_month(mo_int, be_y)
        d_int = max(1, min(max_d, int(d_val)))

        can_e = True
        if f"ST{m_no}" in row and row[f"ST{m_no}"] is not None:
            can_e = row[f"ST{m_no}"] not in [False, 0, "0", "false"]
        elif f"st{m_no}" in row and row[f"st{m_no}"] is not None:
            can_e = row[f"st{m_no}"] not in [False, 0, "0", "false"]
        elif "can_edit" in p_data:
            can_e = p_data["can_edit"] not in [False, 0, "0", "false"]
        elif f"can_edit{m_no}" in row and row[f"can_edit{m_no}"] is not None:
            can_e = row[f"can_edit{m_no}"] not in [False, 0, "0", "false"]

        thai_d = f"{d_int:02d}/{mo_int:02d}/{be_y}"
        ad_d = f"{ce_y:04d}-{mo_int:02d}-{d_int:02d}"

        periods_12.append({
            "period_no": m_no,
            "day": d_int,
            "month": mo_int,
            "month_name": m_name,
            "year": be_y,
            "can_edit": bool(can_e),
            "thai_date": thai_d,
            "ad_date": ad_d,
            "date": ad_d
        })

    # ซ่อมข้อมูลในฐานข้อมูลอัตโนมัติหากพบปีที่เพี้ยน (เช่น 1086, 1629)
    if needs_db_repair and mysql_db:
        try:
            col_rows = mysql_db.sql_fetchall(f"SHOW COLUMNS FROM {actual_tbl}") or []
            cols = [str(c.get("Field") or c.get("field") or "").lower() for c in col_rows]
            repair_fields = {}
            if "periods_json" in cols:
                repair_fields["periods_json"] = json.dumps(periods_12, ensure_ascii=False)
            for p in periods_12:
                p_no = p["period_no"]
                if f"period_{p_no}" in cols:
                    repair_fields[f"Period_{p_no}"] = f"{p['ad_date']} 00:00:00"
                if f"day{p_no}" in cols:
                    repair_fields[f"day{p_no}"] = p["day"]
                if f"month{p_no}" in cols:
                    repair_fields[f"month{p_no}"] = p["month"]
                if f"year{p_no}" in cols:
                    repair_fields[f"year{p_no}"] = p["year"]
                if f"date{p_no}" in cols:
                    repair_fields[f"date{p_no}"] = p["ad_date"]
            if repair_fields:
                set_str = ", ".join([f"{k} = %s" for k in repair_fields.keys()])
                db_execute_commit(f"UPDATE {actual_tbl} SET {set_str}", tuple(repair_fields.values()))
        except Exception as e_rep:
            print(f"[WARN] Auto-repair gl_period dates warning: {e_rep}")

    return {
        "row": row,
        "year": target_year,
        "db_year": db_year,
        "total_periods": total_periods,
        "acc_group": acc_group,
        "profit_loss_acc": profit_loss_acc,
        "retained_earnings_acc": retained_earnings_acc,
        "retained_earnings_name": retained_earnings_name,
        "periods": periods_12
    }

@app.route("/GL_Period")  
def GL_Period(): 
    ensure_schema_gl_period()
    data = get_gl_period_record()
    return render_template(
        "GL_Period.html",
        row=data["row"],
        year=data["year"],
        total_periods=data["total_periods"],
        acc_group=data["acc_group"],
        profit_loss_acc=data["profit_loss_acc"],
        retained_earnings_acc=data["retained_earnings_acc"],
        retained_earnings_name=data["retained_earnings_name"],
        periods=data["periods"],
        day1=data["periods"][0]["day"],
        month1=data["periods"][0]["month"],
        year1=data["periods"][0]["year"],
        thai_date1=data["periods"][0]["thai_date"],
        ad_date1=data["periods"][0]["ad_date"]
    )

@app.route("/api/gl_chart", methods=["GET"])
def api_get_gl_chart():
    """ดึงรายชื่อผังบัญชีสำหรับหน้า GL_AccountChart และ Modal ค้นหาผังบัญชี"""
    ensure_schema_gl_period()
    if not mysql_db:
        return jsonify({"error": "1", "message": "ฐานข้อมูลไม่พร้อมใช้งาน", "results": []}), 500
    try:
        kw = (request.args.get("q") or request.args.get("search") or "").strip().lower()
        acc_type = (request.args.get("type") or "").strip()
        sql = """
            SELECT acc_code, acc_name, acc_type,
                   COALESCE(acc_category_no, 1) AS acc_category_no,
                   COALESCE(branch_code, '01') AS branch_code,
                   COALESCE(branch_name, 'สถาบันการเงิน') AS branch_name,
                   COALESCE(acc_group, '01') AS acc_group,
                   COALESCE(acc_group_name, 'บัญชี 1') AS acc_group_name,
                   COALESCE(balance_side, 'debit') AS balance_side,
                   COALESCE(opening_balance, 0.00) AS opening_balance
            FROM gl_chart
            WHERE status = 1
        """
        params = []
        if kw:
            sql += " AND (LOWER(acc_code) LIKE %s OR LOWER(acc_name) LIKE %s)"
            params.extend([f"%{kw}%", f"%{kw}%"])
        if acc_type:
            sql += " AND acc_type = %s"
            params.append(acc_type)
        sql += " ORDER BY acc_code ASC"
        rows = mysql_db.sql_fetchall(sql, tuple(params) if params else None) or []
        for r in rows:
            if r.get("opening_balance") is not None:
                r["opening_balance"] = float(r["opening_balance"])
        return jsonify({"error": "0", "results": rows})
    except Exception as e:
        print(f"[ERROR] api_get_gl_chart: {e}")
        return jsonify({"error": "1", "message": str(e), "results": []}), 500

@app.route("/api/gl_chart/save", methods=["POST"])
def api_save_gl_chart():
    """บันทึก (เพิ่ม / แก้ไข) ข้อมูลผังบัญชีลงตาราง gl_chart"""
    ensure_schema_gl_period()
    if not mysql_db:
        return jsonify({"error": "1", "message": "ฐานข้อมูลไม่พร้อมใช้งาน"}), 500
    try:
        data = request.get_json(force=True) or {}
        mode = (data.get("mode") or "save").strip().lower()
        orig_code = (data.get("original_acc_code") or "").strip()
        acc_code = (data.get("acc_code") or "").strip()
        acc_name = (data.get("acc_name") or "").strip()
        branch_code = (data.get("branch_code") or "01").strip()
        branch_name = (data.get("branch_name") or "สถาบันการเงิน").strip()
        acc_category_no = int(data.get("acc_category_no") or 1)
        cat_map = {1: "สินทรัพย์", 2: "หนี้สิน", 3: "ทุน", 4: "รายได้", 5: "ค่าใช้จ่าย"}
        acc_type = (data.get("acc_type") or cat_map.get(acc_category_no, "สินทรัพย์")).strip()
        acc_group = (data.get("acc_group") or "01").strip()
        acc_group_name = (data.get("acc_group_name") or "บัญชี 1").strip()
        balance_side = (data.get("balance_side") or "debit").strip()
        try:
            opening_balance = float(str(data.get("opening_balance") or 0).replace(",", ""))
        except Exception:
            opening_balance = 0.0

        if not acc_code:
            return jsonify({"error": "1", "message": "กรุณาระบุเลขที่บัญชี"}), 400
        if not acc_name:
            return jsonify({"error": "1", "message": "กรุณาระบุชื่อบัญชี(ไทย)"}), 400

        existing = mysql_db.sql_fetchone("SELECT acc_code, status FROM gl_chart WHERE acc_code = %s", (acc_code,))
        if mode == "add" and existing and int(existing.get("status") or 0) == 1:
            return jsonify({"error": "1", "message": f"เลขที่บัญชี {acc_code} มีอยู่ในระบบแล้ว (ห้ามกำหนดซ้ำกัน)"}), 400

        if mode == "edit" and orig_code and orig_code != acc_code:
            if existing and int(existing.get("status") or 0) == 1:
                return jsonify({"error": "1", "message": f"เลขที่บัญชี {acc_code} มีอยู่ในระบบแล้ว (ห้ามกำหนดซ้ำกัน)"}), 400
            sql_upd = """
                UPDATE gl_chart
                SET acc_code=%s, acc_name=%s, acc_type=%s, acc_category_no=%s,
                    branch_code=%s, branch_name=%s, acc_group=%s, acc_group_name=%s,
                    balance_side=%s, opening_balance=%s, status=1
                WHERE acc_code=%s
            """
            ok, err = db_execute_commit(sql_upd, (
                acc_code, acc_name, acc_type, acc_category_no,
                branch_code, branch_name, acc_group, acc_group_name,
                balance_side, opening_balance, orig_code
            ))
        elif existing:
            sql_upd = """
                UPDATE gl_chart
                SET acc_name=%s, acc_type=%s, acc_category_no=%s,
                    branch_code=%s, branch_name=%s, acc_group=%s, acc_group_name=%s,
                    balance_side=%s, opening_balance=%s, status=1
                WHERE acc_code=%s
            """
            ok, err = db_execute_commit(sql_upd, (
                acc_name, acc_type, acc_category_no,
                branch_code, branch_name, acc_group, acc_group_name,
                balance_side, opening_balance, acc_code
            ))
        else:
            sql_ins = """
                INSERT INTO gl_chart
                (acc_code, acc_name, acc_type, acc_category_no, branch_code, branch_name,
                 acc_group, acc_group_name, balance_side, opening_balance, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            """
            ok, err = db_execute_commit(sql_ins, (
                acc_code, acc_name, acc_type, acc_category_no, branch_code, branch_name,
                acc_group, acc_group_name, balance_side, opening_balance
            ))

        if not ok:
            return jsonify({"error": "1", "message": f"บันทึกไม่สำเร็จ: {err}"}), 500

        return jsonify({"error": "0", "message": "บันทึกผังบัญชีเรียบร้อยแล้ว", "acc_code": acc_code})
    except Exception as e:
        print(f"[ERROR] api_save_gl_chart: {e}")
        return jsonify({"error": "1", "message": str(e)}), 500

@app.route("/api/gl_chart/delete", methods=["POST"])
def api_delete_gl_chart():
    """ลบข้อมูลผังบัญชีออกจากตาราง gl_chart"""
    ensure_schema_gl_period()
    if not mysql_db:
        return jsonify({"error": "1", "message": "ฐานข้อมูลไม่พร้อมใช้งาน"}), 500
    try:
        data = request.get_json(force=True) or {}
        acc_code = (data.get("acc_code") or "").strip()
        if not acc_code:
            return jsonify({"error": "1", "message": "ไม่พบเลขที่บัญชีที่ต้องการลบ"}), 400
        ok, err = db_execute_commit("DELETE FROM gl_chart WHERE acc_code = %s", (acc_code,))
        if not ok:
            return jsonify({"error": "1", "message": f"ลบไม่สำเร็จ: {err}"}), 500
        return jsonify({"error": "0", "message": f"ลบผังบัญชี {acc_code} เรียบร้อยแล้ว"})
    except Exception as e:
        print(f"[ERROR] api_delete_gl_chart: {e}")
        return jsonify({"error": "1", "message": str(e)}), 500

@app.route("/api/gl_period", methods=["GET"])
def api_get_gl_period():
    """ดึงข้อมูลงวดรอบบัญชีจากตาราง gl_period (ใช้ฐานข้อมูล 1 แถวเท่านั้น) พร้อมค่าคงที่และ 12 งวดเสมอ"""
    ensure_schema_gl_period()
    if not mysql_db:
        return jsonify({"error": "1", "message": "ฐานข้อมูลไม่พร้อมใช้งาน"}), 500

    try:
        year_param = request.args.get("year") or request.args.get("year_be")
        data = get_gl_period_record(year_param)
        return jsonify({
            "error": "0",
            "exists": bool(data["row"]),
            "year": data["year"],
            "db_year": data["db_year"],
            "CurentYear": str(data["db_year"]) if data["db_year"] else "",
            "PeriodPerYear": data["total_periods"],
            "total_periods": data["total_periods"],
            "DepId": data["acc_group"],
            "acc_group": data["acc_group"],
            "AC_ProfitLose": data["profit_loss_acc"],
            "profit_loss_acc": data["profit_loss_acc"],
            "AC_ProfitACC": data["retained_earnings_acc"],
            "retained_earnings_acc": data["retained_earnings_acc"],
            "retained_earnings_name": data["retained_earnings_name"],
            "available_years": [data["db_year"]] if data["db_year"] else [],
            "periods": data["periods"]
        })
    except Exception as e:
        print(f"[ERROR] api_get_gl_period: {e}")
        return jsonify({"error": "1", "message": str(e)}), 500


@app.route("/api/gl_period/update", methods=["POST", "PUT"])
@app.route("/api/gl_period/save", methods=["POST"])
def api_save_gl_period():
    """อัปเดต/บันทึกข้อมูลรอบบัญชี gl_period (ใช้คำสั่ง UPDATE แถวเดิม 1 Row เท่านั้น ห้าม INSERT ใหม่)"""
    ensure_schema_gl_period()
    if not mysql_db:
        return jsonify({"error": "1", "message": "ฐานข้อมูลไม่พร้อมใช้งาน"}), 500

    try:
        data = request.get_json(force=True) or {}
        year_be = normalize_be_year(data.get("CurentYear") or data.get("curentyear") or data.get("year") or data.get("year_be"), datetime.now().year + 543)
        total_periods = int(data.get("PeriodPerYear") or data.get("periodperyear") or data.get("total_periods") or 12)
        cusid = str(data.get("cusid") or "00001").strip()
        periods = data.get("periods") or []

        acc_group = str(data.get("DepId") or data.get("depid") or data.get("acc_group") or "01").strip()
        profit_loss_acc = str(data.get("AC_ProfitLose") or data.get("ac_profitlose") or data.get("profit_loss_acc") or "3800").strip()
        retained_earnings_acc = str(data.get("AC_ProfitACC") or data.get("ac_profitacc") or data.get("retained_earnings_acc") or "3700").strip()
        retained_earnings_name = str(data.get("retained_earnings_name") or "กำไรสะสม").strip()

        actual_tbl = get_gl_period_table_name()
        col_rows = mysql_db.sql_fetchall(f"SHOW COLUMNS FROM {actual_tbl}") or []
        cols = [str(c.get("Field") or c.get("field") or "").lower() for c in col_rows]
        pk_col = None
        for c in col_rows:
            if (c.get("Key") or c.get("key")) == "PRI":
                pk_col = c.get("Field") or c.get("field")
                break

        # ตรวจสอบแถวเดิมในตาราง (ใช้ 1 Row เท่านั้น)
        existing_row = mysql_db.sql_fetchone(f"SELECT * FROM {actual_tbl} LIMIT 1")

        # เตรียมค่าที่จะบันทึก
        fields_dict = {}
        if "curentyear" in cols: fields_dict["CurentYear"] = str(year_be)
        elif "currentyear" in cols: fields_dict["CurrentYear"] = str(year_be)

        if "periodperyear" in cols: fields_dict["PeriodPerYear"] = total_periods
        elif "period_per_year" in cols: fields_dict["period_per_year"] = total_periods

        if "ac_profitlose" in cols: fields_dict["AC_ProfitLose"] = profit_loss_acc
        if "ac_profitacc" in cols: fields_dict["AC_ProfitACC"] = retained_earnings_acc

        if "depid" in cols: fields_dict["DepId"] = acc_group
        elif "dep_id" in cols: fields_dict["dep_id"] = acc_group

        if "usercreate" in cols: fields_dict["USERCREATE"] = (data.get("login") or "admin")[:20]
        if "datecreate" in cols: fields_dict["DATECREATE"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if "year_be" in cols: fields_dict["year_be"] = year_be
        if "year" in cols: fields_dict["year"] = year_be
        if "end_year_be" in cols: fields_dict["end_year_be"] = year_be
        if "total_periods" in cols: fields_dict["total_periods"] = total_periods
        if "status" in cols: fields_dict["status"] = 1
        if "acc_group" in cols: fields_dict["acc_group"] = acc_group
        if "profit_loss_acc" in cols: fields_dict["profit_loss_acc"] = profit_loss_acc
        if "retained_earnings_acc" in cols: fields_dict["retained_earnings_acc"] = retained_earnings_acc
        if "retained_earnings_name" in cols: fields_dict["retained_earnings_name"] = retained_earnings_name
        if "cusid" in cols: fields_dict["cusid"] = cusid

        normalized_periods = []
        # บันทึก Period_1..12, ST1..12, day, month, year, can_edit, date
        for idx, p in enumerate(periods):
            p_no = int(p.get("period_no") or (idx + 1))
            if 1 <= p_no <= 12:
                p_year = normalize_be_year(p.get("year"), year_be)
                p_month = max(1, min(12, int(p.get("month") or p_no)))
                max_d = get_max_days_in_month(p_month, p_year)
                p_day = max(1, min(max_d, int(p.get("day") or max_d)))
                p_can_edit = 1 if p.get("can_edit") in [True, 1, "1", "true"] else 0
                ce_yr = p_year - 543
                end_d_str = f"{ce_yr:04d}-{p_month:02d}-{p_day:02d}"

                normalized_periods.append({
                    "period_no": p_no,
                    "day": p_day,
                    "month": p_month,
                    "month_name": p.get("month_name") or "",
                    "year": p_year,
                    "date": end_d_str,
                    "can_edit": p_can_edit
                })

                if f"period_{p_no}" in cols: fields_dict[f"Period_{p_no}"] = f"{end_d_str} 00:00:00"
                if f"st{p_no}" in cols: fields_dict[f"ST{p_no}"] = p_can_edit
                if f"day{p_no}" in cols: fields_dict[f"day{p_no}"] = p_day
                if f"month{p_no}" in cols: fields_dict[f"month{p_no}"] = p_month
                if f"year{p_no}" in cols: fields_dict[f"year{p_no}"] = p_year
                if f"can_edit{p_no}" in cols: fields_dict[f"can_edit{p_no}"] = p_can_edit
                if f"date{p_no}" in cols: fields_dict[f"date{p_no}"] = end_d_str

        if "periods_json" in cols:
            fields_dict["periods_json"] = json.dumps(normalized_periods if normalized_periods else periods, ensure_ascii=False)

        if "period_13" in cols and "Period_12" in fields_dict:
            fields_dict["Period_13"] = fields_dict["Period_12"]

        if normalized_periods:
            first_p = normalized_periods[0]
            last_p = normalized_periods[-1] if len(normalized_periods) >= 12 else normalized_periods[0]
            if "day1" in cols: fields_dict["day1"] = first_p["day"]
            if "month1" in cols: fields_dict["month1"] = first_p["month"]
            if "year1" in cols: fields_dict["year1"] = first_p["year"]
            if "date1" in cols: fields_dict["date1"] = first_p["date"]
            if "date" in cols: fields_dict["date"] = first_p["date"]
            if "day" in cols: fields_dict["day"] = first_p["day"]
            if "end_day" in cols: fields_dict["end_day"] = last_p["day"]
            if "month" in cols: fields_dict["month"] = first_p["month"]
            if "end_month" in cols: fields_dict["end_month"] = last_p["month"]
            if "end_month_name" in cols: fields_dict["end_month_name"] = str(last_p.get("month_name") or "ธันวาคม")
            if "period_no" in cols: fields_dict["period_no"] = 1
            if "period" in cols: fields_dict["period"] = 1
            if "end_date" in cols: fields_dict["end_date"] = last_p["date"]

        if existing_row:
            set_clauses = [f"{k} = %s" for k in fields_dict.keys()]
            vals = list(fields_dict.values())

            if "id" in cols and existing_row.get("id") is not None:
                sql_upd = f"UPDATE {actual_tbl} SET {', '.join(set_clauses)} WHERE id = %s"
                vals.append(existing_row["id"])
            elif pk_col and existing_row.get(pk_col) is not None:
                sql_upd = f"UPDATE {actual_tbl} SET {', '.join(set_clauses)} WHERE {pk_col} = %s"
                vals.append(existing_row[pk_col])
            elif "CurentYear" in existing_row and existing_row.get("CurentYear") is not None:
                sql_upd = f"UPDATE {actual_tbl} SET {', '.join(set_clauses)} WHERE CurentYear = %s"
                vals.append(existing_row["CurentYear"])
            elif "curentyear" in existing_row and existing_row.get("curentyear") is not None:
                sql_upd = f"UPDATE {actual_tbl} SET {', '.join(set_clauses)} WHERE curentyear = %s"
                vals.append(existing_row["curentyear"])
            elif "DepId" in existing_row and existing_row.get("DepId") is not None:
                sql_upd = f"UPDATE {actual_tbl} SET {', '.join(set_clauses)} WHERE DepId = %s"
                vals.append(existing_row["DepId"])
            else:
                sql_upd = f"UPDATE {actual_tbl} SET {', '.join(set_clauses)}"

            success, err_msg = db_execute_commit(sql_upd, tuple(vals))
            if not success:
                print(f"[ERROR] UPDATE {actual_tbl} failed: {err_msg}")
                return jsonify({"error": "1", "message": f"ไม่สามารถ UPDATE ข้อมูลลงตาราง {actual_tbl} ได้: {err_msg}"}), 500
        else:
            if "id" in cols:
                fields_dict["id"] = 1
            col_names = list(fields_dict.keys())
            placeholders = ["%s"] * len(col_names)
            sql_ins = f"INSERT INTO {actual_tbl} ({', '.join(col_names)}) VALUES ({', '.join(placeholders)})"
            success, err_msg = db_execute_commit(sql_ins, tuple(fields_dict.values()))
            if not success:
                print(f"[ERROR] INSERT INTO {actual_tbl} failed: {err_msg}")
                return jsonify({"error": "1", "message": f"ไม่สามารถ INSERT ข้อมูลลงตาราง {actual_tbl} ได้: {err_msg}"}), 500

        return jsonify({
            "error": "0",
            "status": "success",
            "message": f"บันทึกข้อมูลงวดรอบบัญชีปี {year_be} ลงในฐานข้อมูลเรียบร้อยแล้ว (1 แถว)",
            "year": year_be,
            "count": 1
        })

    except Exception as e:
        print(f"[ERROR] api_save_gl_period: {e}")
        return jsonify({"error": "1", "message": str(e)}), 500

@app.route("/GL_AccountChart")  
def GL_AccountChart(): 
    return render_template("GL_AccountChart.html")

@app.route("/GL_Book")  
def GL_Book(): 
    return render_template("GL_Book.html")

@app.route("/GL_tran")  
def GL_tran(): 
    return render_template("GL_tran.html")

@app.route("/GL_tranEdit")  
def GL_tranEdit(): 
    return render_template("GL_tranEdit.html")

@app.route("/GL_Pattern")  
def GL_Pattern(): 
    return render_template("GL_Pattern.html")


#@app.route("/user/<name>/<age>")
#def member(name,age):
    #return"<h1> ชื่อสมาชิก : {} , อายุ : {} <h1>".format(name[0],age)

@app.route("/DK_Test")  
def DK_Test(): 
    return render_template("DK_Test.html")

@app.route("/fromdate")  
def fromdate(): 
    return render_template("fromdate.html")

@app.route("/form")  
def form(): 
    return render_template("form.html")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )