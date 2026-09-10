#Type Coversion
x = 10
y = 3.14
z = "20" #คือ str

#บวกเลข
result = x+int(z) #แปลง z เป็นstr
result = str(x)+(z) #แปลง x เป็นstr
print(type(x))
print(type(y))
print(type(z))
print(result)


# บวกเลข 
z=float(z)
# 10+3.14 = 13.14
# "10" + "20" ="1020" => result

z=z+50
# string => int 
# int => string

#string => float
#float => string

# int => float
# float => int
print(z)