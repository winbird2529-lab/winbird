from flask import Flask,render_template,request
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField,BooleanField
from flask import request, jsonify
from fastapi import FastAPI, Form, UploadFile, File
import os
import json


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
def index():
    #return "<H1> Hello flask framework 33333<H1> "
    return render_template("index.html")

@app.route("/login") 
def login():
    return render_template("login.html")  


@app.route("/DK_Home")  
def DK_Home(): 
    return render_template("DK_Home.html")
@app.route("/DK_customer")  
def DK_customer(): 
    return render_template("DK_customer.html")
@app.route("/DK_Employee")  
def DK_Employee(): 
    return render_template("DK_Employee.html")
@app.route("/DK_Beneficiary")  
def DK_Beneficiary(): 
    return render_template("DK_Beneficiary.html")

@app.route("/DK_Running")
def DK_Running():
    return render_template("DK_Running.html")

RUNNING_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'running_config.json')

@app.route("/api/running-config", methods=["GET", "POST"])
def running_config():
    if request.method == "POST":
        data = request.get_json() or {}
        try:
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
        default_config = {
            "pc_mode": "auto",
            "ey_mode": "auto",
            "dw_mode": "auto",
            "tw_mode": "auto"
        }
        if os.path.exists(RUNNING_CONFIG_FILE):
            try:
                with open(RUNNING_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_config.update(data)
            except Exception:
                pass
        return jsonify(default_config)
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


@app.route("/DK_Movement")  
def DK_Movement(): 
    return render_template("DK_Movement.html")

@app.route("/DK_showMovement")  
def DK_showMovement(): 
    return render_template("DK_showMovement.html")




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