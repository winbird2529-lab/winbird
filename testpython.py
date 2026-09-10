#เก็บข้อมูลนักเรียน
'''
name = "วทัญญู คุ้มวงศ์"
NAME ="WATHUNYOO KHUMWONG"
age =18
grade =4
status = True
score  = 80


#ตัวแปล บรรทัดเดียว name,NAME,= "วทัญญู คุ้มวงศ์","WATHUNYOO KHUMWONG"
แสดง type ตัวแปล
print (type(age))
print (type(grade))
print (type(status))

print ("ชื่อนักเรียน=",name)
print ("ชื่อภาษาอังกฤษ =",NAME)
print ("อายุ =",age,"ปี")
print ("เกรด =" ,grade)
print ("สถานะ =",status)
'''

#caseป้อนชื่อ
'''
name1=input("กรุณาป้อนชื่อ : ")
year = int(input("กรุณาปอนปีเกิดของคุณ :"))
print ("ชื่อของคุณ =:",name)
print ("ปีนี้คุณมีอายุ =",2568-year)
'''
#ปิดเคส
print ("*****************")

number1=5
number2=2
print ("ผลบวก:",number1+number2)
print ("ผลลบ:",number1-number2)
print ("ผลคูณ:",number1*number2)
print ("ผลหาร:",number1/number2)
print ("ผลหารไม่เอาเศษ:",number1//number2)
print ("เศษ:",number1%number2)
#ปิดเคส
print ("*****************")

#ตัวดำเนินการกำหนดค่า
x = 10
y = 2
Z = x+y
print (x)
print (y)
x=x+y
print ("ผลลัพท์ :",x)
x+=y  #เขียนแบบลดรูป
print ("ผลลัพท์ :",x)

#ปิดเคส
print ("*****************")
'''
#ตัวดำเนินการเปรียบเทียบ
g,h = 100,50
print (g==h)
print (g!=h)
print (g>h)
print (g>=h)
print (g<h)
print (g<=h)
#ปิดเคส
'''
print ("*****************")

#คำสั่งเงือนไข

score= int(input("ป้อนคะแนน :"))
print ("คะแนนสอบของคุณ",score)
'''
if score>=50:
    print ("คุณสอบผ่าน")
else :
    print ("คุณสอบไม่ผ่าน")
'''
if score<0:
    print ("กรอกคะแนนไม่ถูกต้อง")
elif score>=50:
    print ("คุณสอบผ่าน")
else :
    print ("คุณสอบไม่ผ่าน")
#ปิดเคส
print ("*****************")
    


    

 







