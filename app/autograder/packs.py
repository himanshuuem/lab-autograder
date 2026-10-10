"""Questions and requirement checks for the Object Oriented Programming lab sheets.

Each sheet's questions say what classes must do, not what the program prints, so they are
graded by checks (see checks.py). A pack lists a sheet's questions with their checks;
installing it on an assignment sets that assignment's questions (POST /assignments/{id}/checks).

A check is (id, what it verifies, how):
  how = a tab-separated spec for the Java harness (generic checks in checks.JAVA_HARNESS),
        or None for the checks run in Python on the source and output (src:, out:, py:).
Class, method and field names in specs are case-insensitive regexes, so `employee|emp`
accepts a class called Emp too.
"""
from __future__ import annotations

T = "\t"


def spec(*parts) -> str:
    return T.join(str(p) for p in parts)


# Names students use for the same thing
EMP = "employee|emp"
MGR = "manager|mgr"
DEV = "developer|dev"
BAL = "bal!min|over|limit|interest|rate"

CHECKS: dict[str, tuple[str, str | None]] = {
    # ------------------------------------------------------------- Assignment 2 (constructors)
    "a2:bank_fields": ("has fields for account number, holder name and balance",
                       spec("fields", "acc|num|no;name|holder;bal", "account number;holder name;balance")),
    "a2:bank_deposit": ("depositing 500 into a balance of 1000 gives 1500",
                        spec("bank", "bank|account", f"{BAL}=1000", "dep|credit|add", 500, BAL, 1500)),
    "a2:bank_withdraw": ("withdrawing 300 from a balance of 1000 leaves 700",
                         spec("bank", "bank|account", f"{BAL}=1000", "withdraw|draw|debit", 300, BAL, 700)),
    "a2:bank_display": ("has a method to display the balance",
                        spec("method", "bank|account", "display|show|print|balance|get")),
    "a2:student_fields": ("has fields for name, roll number and CGPA",
                          spec("fields", "name;roll;cgpa|gpa|cg|grade", "name;roll number;CGPA")),
    "a2:student_ctor": ("has a parameterized constructor (name, roll number, CGPA…)",
                        spec("ctorparams", "student|stud", 3)),
    "a2:rect_ctors": ("has the three constructors: (), (side) and (length, breadth)",
                      spec("ctorsig", "rect", ";num;num,num")),
    "a2:rect_default": ("new Rectangle() has area 1 (length = breadth = 1)",
                        spec("ctorvalue", "rect", "", "area", 1, 0.5)),
    "a2:rect_square": ("new Rectangle(4) has area 16 (length = breadth)",
                       spec("ctorvalue", "rect", "len=4", "area", 16, 0.5)),
    "a2:rect_area": ("new Rectangle(4, 5) has area 20",
                     spec("ctorvalue", "rect", "len=4;br=5", "area", 20, 0.5)),
    "a2:rect_perimeter": ("new Rectangle(4, 5) has perimeter 18",
                          spec("ctorvalue", "rect", "len=4;br=5", "perim|peri", 18, 0.5)),
    "a2:emp_ctors": ("has the three constructors: (), (name) and (name, salary)",
                     spec("ctorsig", EMP, ";text;text,num")),
    "src:this_call": ("one constructor calls another with this(...)", None),
    "a2:phone_fields": ("has fields for brand, model and price",
                        spec("fields", "brand;model;price|cost", "brand;model;price")),
    "a2:phone_copy": ("has a copy constructor that copies the price",
                      spec("copyctor", "mobile|phone", "price|cost")),
    "py:discount15": ("shows a price and the same price with 15% off", None),

    # ------------------------------------------------------------- Assignment 3 (overloading)
    "a3:result_overloads": ("has calculateResult(int,int,int), (int,int,int,int) and (double,double,double)",
                            spec("methodsig", "result", "calc|result", "int,int,int;int,int,int,int;double,double,double")),
    "a3:result_3int": ("calculateResult(70, 80, 90) gives total 240 and average 80",
                       spec("calc", "result", "calc|result", "70,80,90", "240,80")),
    "a3:result_4int": ("calculateResult(70, 80, 90, 100) gives total 340 and average 85",
                       spec("calc", "result", "calc|result", "70,80,90,100", "340,85")),
    "a3:result_3dbl": ("calculateResult(70.5, 80.5, 90.5) gives total 241.5 and average 80.5",
                       spec("calc", "result", "calc|result", "70.5,80.5,90.5", "241.5,80.5")),
    "a3:display_overloads": ("has show(int), show(long), show(float) and show(double)",
                             spec("methodsig", "display|disp", "show", "int;long;float;double")),
    "out:char_as_int": ("show('A') prints 65: the char goes to show(int)", None),
    "a3:calc_overloads": ("has calculate(int, double) and calculate(double, int)",
                          spec("methodsig", "", "calc", "int,double;double,int")),
    "src:explicit_cast": ("changes the call so it isn't ambiguous: calculate((double) 10, 20) or calculate(10, 20.0)", None),
    "a3:student_ctors": ("has Student(), (roll, name), (roll, name, dept) and (roll, name, dept, cgpa)",
                         spec("ctorsig", "student|stud", ";num,text;num,text,text;num,text,text,num")),
    "a3:student_fields": ("has fields for roll number, name, department and CGPA",
                          spec("fields", "roll;name;dep|branch;cgpa|gpa|cg", "roll number;name;department;CGPA")),
    "a3:number_ctors": ("has Number(int), Number(long) and Number(double)",
                        spec("ctorsig", "number|num", "int;long;double")),
    "src:number_char": ("creates new Number('A')", None),

    # ------------------------------------------------------------- Assignment 4 (inheritance)
    "a4:mgr_extends_emp": ("Manager extends Employee", spec("extends", MGR, EMP)),
    "a4:salary_private": ("salary is private in Employee", spec("modifier", EMP, "sal", "private")),
    "a4:dept_protected": ("department is protected in Employee", spec("modifier", EMP, "dep", "protected")),
    "a4:company_public": ("company name is public in Employee", spec("modifier", EMP, "comp|org", "public")),
    "a4:mgr_fields": ("Manager has designation and number of team members",
                      spec("fields", "desig|post|role;team|member|size", "designation;number of team members")),
    "a4:emp_ctor_default": ("Employee has a no-argument constructor", spec("ctorsig", EMP, "")),
    "a4:emp_ctor_param": ("Employee has a parameterized constructor", spec("ctorparams", EMP, 1)),
    "a4:mgr_ctor_param": ("Manager has a parameterized constructor", spec("ctorparams", MGR, 1)),
    "src:super_args": ("a constructor passes values up with super(...)", None),
    "src:super_call": ("calls the superclass constructor with super()", None),
    "a4:display_manager": ("Manager has a method to display all details",
                           spec("method", MGR, "disp|show|print|detail")),
    "out:ctor_order": ("prints the Employee constructor message before the Manager one", None),
    "a4:circle_shape": ("Circle extends Shape", spec("extends", "circle", "shape")),
    "a4:rect_shape": ("Rectangle extends Shape", spec("extends", "rect", "shape")),
    "a4:tri_shape": ("Triangle extends Shape", spec("extends", "tri", "shape")),
    "a4:area_overridden": ("area() is overridden in Circle, Rectangle and Triangle",
                           spec("overrides", "shape", "area", 3)),
    "out:lines:3": ("prints at least three lines", None),
    "a4:cyl_circle": ("Cylinder extends Circle", spec("extends", "cyl", "circle")),
    "a4:cone_cyl": ("Cone extends Cylinder", spec("extends", "cone", "cyl")),
    "a4:circle_info": ("Circle has a static info() method", spec("static", "circle", "info", "method")),
    "a4:cyl_overrides": ("Cylinder overrides area()", spec("overrides", "circle", "area", 1)),
    "a4:cyl_surface": ("a cylinder of radius 3, height 5 has surface area 150.8",
                       spec("value", "cyl", "rad|^r$=3;hei|^h$=5", "surf|area", 150.8, 1.5)),
    "src:super_method": ("uses super.area() (or another super.method())", None),
    "a4:emp3_subclasses": ("PermanentEmployee, ContractEmployee and Intern override calculateSalary()",
                           spec("overrides", EMP, "sal|pay", 3)),
    "src:employee_array": ("keeps the employees in an Employee[] array", None),
    "out:lines:3:loop": ("calling calculateSalary() in a loop prints at least three lines", None),
    "a4:role_overridden": ("displayRole() is overridden in Manager and Developer",
                           spec("overrides", EMP, "role", 2)),
    "a4:policy_hidden": ("static companyPolicy() is redefined (hidden) in a subclass",
                         spec("hides", EMP, "polic")),
    "a4:intern_extends": ("an Intern subclass is added", spec("extends", "intern", EMP)),
    "out:role_messages": ("prints \"Manager manages the team\" and \"Developer develops software\"", None),
    "out:general_policy": ("an Employee reference calls the general companyPolicy()", None),

    # ------------------------------------------------------------- Assignment 4, 3rd and 4th part (abstract classes)
    "a4:shape_abstract": ("Shape is an abstract class", spec("abstract", "shape")),
    "a4:shape_area_abs": ("Shape has an abstract calculateArea()", spec("absmethod", "shape", "area")),
    "a4:circle_2d": ("Circle is a kind of Shape", spec("extends", "circle", "shape")),
    "a4:cyl_3d": ("Cylinder is a kind of Shape", spec("extends", "cyl", "shape")),
    "a4:cone_3d": ("Cone is a kind of Shape", spec("extends", "cone", "shape")),
    "a4:cyl_volume": ("a cylinder of radius 3, height 5 has volume 141.37",
                      spec("value", "cyl", "rad|^r$=3;hei|^h$=5", "vol", 141.37, 1.5)),
    "a4:cone_volume": ("a cone of radius 3, height 4 has volume 37.70",
                       spec("value", "cone", "rad|^r$=3;hei|^h$=4", "vol", 37.70, 1.5)),
    "src:shape_ref": ("uses Shape references for subclass objects", None),
    "a4:animal_abstract": ("Animal is an abstract class", spec("abstract", "animal")),
    "a4:mammal_abstract": ("Mammal extends Animal", spec("extends", "mammal", "animal")),
    "a4:mammal_is_abstract": ("Mammal is abstract", spec("abstract", "mammal")),
    "a4:cow_mammal": ("Cow extends Mammal", spec("extends", "cow", "mammal")),
    "a4:sound_abs": ("Animal has an abstract makeSound()", spec("absmethod", "animal", "sound")),
    "a4:birth_abs": ("Mammal has an abstract giveBirth()", spec("absmethod", "mammal", "birth")),
    "a4:cow_overrides": ("Cow implements makeSound() and giveBirth()", spec("overrides", "mammal", "sound|birth", 1)),
    "src:animal_refs": ("creates the Cow through Animal and Mammal references", None),
    "a4:vehicle_abstract": ("Vehicle is an abstract class", spec("abstract", "vehicle")),
    "a4:tax_abs": ("Vehicle has an abstract calculateTax()", spec("absmethod", "vehicle", "tax")),
    "a4:car_vehicle": ("Car extends Vehicle", spec("extends", "car", "vehicle")),
    "a4:bike_vehicle": ("Bike extends Vehicle", spec("extends", "bike", "vehicle")),
    "a4:tax_overridden": ("Car and Bike implement calculateTax()", spec("overrides", "vehicle", "tax", 2)),
    "a4:vehicle_counter": ("the static totalVehicles count goes up by one per vehicle created",
                           spec("counter", "vehicle")),
    "a4:total_method": ("Vehicle has a static getTotalVehicles()", spec("static", "vehicle", "total|count", "method")),
    "a4:payroll_abstract": ("Employee is abstract with an abstract calculateSalary()", spec("absmethod", EMP, "sal|pay")),
    "a4:payroll_subclasses": ("Permanent, Contract and Part-time employees implement calculateSalary()",
                              spec("overrides", EMP, "sal|pay", 3)),
    "a4:parttime_salary": ("a part-time employee with 10 hours at 50 an hour earns 500",
                           spec("value", "part", "hour|hrs=10;rate|wage|per=50", "sal|pay", 500, 0.5)),
    "a4:display_details": ("Employee has a concrete displayEmployeeDetails()",
                           spec("method", EMP, "disp|show|detail")),
    "a4:grade_abstract": ("an abstract class declares calculateGrade()", spec("absmethod", "", "grade")),
    "a4:grade_overridden": ("UG and PG students each implement calculateGrade()",
                            spec("overrides", "student|stud", "grade", 2)),
    "src:cgpa_method": ("has a calculateCGPA() method", None),
    "out:lines:5": ("prints results for at least five students", None),
    "a4:volume_abs": ("Shape has an abstract calculateVolume()", spec("absmethod", "shape", "vol")),
    "a4:shape_subclasses": ("at least two shapes implement calculateArea()", spec("overrides", "shape", "area", 2)),

    # ------------------------------------------------------------- Assignment 5, course 2 (overloading + overriding)
    "a5:mgr_emp": ("Manager extends Employee", spec("extends", MGR, EMP)),
    "a5:dev_emp": ("Developer extends Employee", spec("extends", DEV, EMP)),
    "a5:salary_overloads": ("Employee has calculateSalary(double) and calculateSalary(double, double)",
                            spec("methodsig", EMP, "sal", "num;num,num")),
    "a5:salary_overridden": ("Manager and Developer override calculateSalary()", spec("overrides", EMP, "sal", 2)),
    "a5:area_overloads": ("Shape has area(double) and area(double, double)", spec("methodsig", "shape", "area", "num;num,num")),
    "a5:area_overridden": ("Circle, Rectangle and Triangle override area()", spec("overrides", "shape", "area", 3)),
    "src:no_type_switch": ("doesn't choose the shape with instanceof", None),
    "a5:car_vehicle": ("Car extends Vehicle", spec("extends", "car", "vehicle")),
    "a5:bike_vehicle": ("Bike extends Vehicle", spec("extends", "bike", "vehicle")),
    "a5:auto_vehicle": ("Auto extends Vehicle", spec("extends", "auto", "vehicle")),
    "a5:fare_overloads": ("Vehicle has calculateFare with 1, 2 and 3 numbers", spec("methodsig", "vehicle", "fare", "num;num,num;num,num,num")),
    "a5:fare_overridden": ("Car, Bike and Auto override calculateFare()", spec("overrides", "vehicle", "fare", 3)),
    "src:vehicle_ref": ("uses Vehicle references for the vehicles", None),

    # ------------------------------------------------------------- Assignment 6, course 2 (bank system)
    "a6:savings_bank": ("SavingsAccount extends BankAccount", spec("extends", "sav", "bank|account")),
    "a6:current_bank": ("CurrentAccount extends BankAccount", spec("extends", "curr", "bank|account")),
    "a6:premium_savings": ("PremiumSavingsAccount extends SavingsAccount", spec("extends", "prem", "sav")),
    "a6:balance_private": ("balance is private in BankAccount", spec("modifier", "bank|account", BAL, "private")),
    "a6:savings_min": ("a savings account (20000, minimum 5000) refuses to withdraw 17000",
                       spec("bank", "^sav", f"{BAL}=20000;min=5000", "withdraw|draw", 17000, BAL, 20000)),
    "a6:savings_ok": ("a savings account (20000, minimum 5000) allows withdrawing 10000",
                      spec("bank", "^sav", f"{BAL}=20000;min=5000", "withdraw|draw", 10000, BAL, 10000)),
    "a6:current_overdraft": ("a current account (10000, overdraft 5000) allows withdrawing 15000",
                             spec("bank", "curr", f"{BAL}=10000;over|limit=5000", "withdraw|draw", 15000, BAL, -5000)),
    "a6:current_limit": ("a current account (10000, overdraft 5000) refuses to withdraw 16000",
                         spec("bank", "curr", f"{BAL}=10000;over|limit=5000", "withdraw|draw", 16000, BAL, 10000)),
    "a6:deposit_overloads": ("deposit(amount), deposit(amount, source) and deposit(amount, source, id)",
                             spec("methodsig", "bank|account", "dep", "num;num,text;num,text,text")),
    "a6:premium_points": ("depositing 1000 into a premium account adds 10 reward points",
                          spec("bank", "prem", f"{BAL}=5000;reward|point=0", "^dep", 1000, "reward|point", 10)),
    "a6:interest_overridden": ("calculateInterest() is overridden", spec("overrides", "bank|account", "interest", 2)),
    "src:process_transaction": ("has processTransaction(BankAccount account, double amount, String type)", None),

    # ------------------------------------------------------------- Mid-semester viva
    "mid:student_ctors": ("Student has a default and a parameterized constructor", spec("ctors", "student|stud", 2)),
    "out:average_cgpa": ("prints an average CGPA", None),
    "mid:bank_private": ("balance is private", spec("modifier", "bank|account", BAL, "private")),
    "mid:bank_negative_dep": ("depositing -100 leaves the balance unchanged",
                              spec("bank", "bank|account", f"{BAL}=1000", "dep", -100, BAL, 1000)),
    "mid:bank_overdraw": ("withdrawing more than the balance is refused",
                          spec("bank", "bank|account", f"{BAL}=1000", "withdraw|draw", 5000, BAL, 1000)),
    "mid:emp_subclasses": ("Manager, Developer and Intern override calculateSalary()", spec("overrides", EMP, "sal", 3)),
    "mid:person_chain": ("Manager extends Employee extends Person", spec("extends", MGR, "person")),
    "mid:shape_array": ("keeps the shapes in a Shape[] array", None),
    "mid:faculty": ("Faculty, TechnicalStaff and AdministrativeStaff implement calculateSalary()",
                    spec("overrides", EMP, "sal|pay", 3)),
    "mid:emp_counter": ("a static count of employees goes up by one per employee", spec("counter", EMP)),
}

# what a Python-side source check looks for
SOURCE_RULES = {
    "this_call": r"\bthis\s*\([^)]*\)\s*;",
    "explicit_cast": r"\(\s*(?:double|int|float|long)\s*\)\s*[\w(]|\bcalc\w*\s*\([^;()]*\d\.\d*[^;()]*\)\s*;",
    "number_char": r"new\s+Number\s*\(\s*'.'\s*\)",
    "super_args": r"\bsuper\s*\(\s*[^)\s]",
    "super_call": r"\bsuper\s*\(",
    "super_method": r"\bsuper\s*\.\s*\w+\s*\(",
    "employee_array": r"\bEmp\w*\s*\[\s*\]|\bnew\s+Emp\w*\s*\[|(?:List|ArrayList)\s*<\s*Emp\w*\s*>",
    "shape_ref": r"\bShape\s*(?:\[\s*\])?\s+\w+\s*=|\bShape\s*\[\s*\]|(?:List|ArrayList)\s*<\s*Shape\s*>",
    "animal_refs": r"\b(?:Animal|Mammal)\s+\w+\s*=\s*new\s+Cow\b",
    "cgpa_method": r"\b\w*(?:cgpa|CGPA|Cgpa)\w*\s*\(",
    "no_type_switch": r"^(?![\s\S]*\binstanceof\b)",
    "vehicle_ref": r"\bVehicle\s*(?:\[\s*\])?\s+\w+\s*=|\bVehicle\s*\[\s*\]|(?:List|ArrayList)\s*<\s*Vehicle\s*>",
    "process_transaction": r"\bprocess\w*\s*\(\s*\w*Account\s+\w+\s*,\s*(?:double|float|int|long)\s+\w+\s*,\s*String\s+\w+\s*\)",
    "shape_array": r"\bShape\s*\[\s*\]|(?:List|ArrayList)\s*<\s*Shape\s*>",
}

# what an output check looks for: every pattern, in this order, case-insensitive
OUTPUT_RULES = {
    "char_as_int": [r"(?<![\d.])65(?![\d.])"],
    "ctor_order": [r"employee[^\n]*constructor|constructor[^\n]*employee", r"manager[^\n]*constructor|constructor[^\n]*manager"],
    "role_messages": [r"manager manages the team", r"developer develops software"],
    "general_policy": [r"general company policy"],
    "average_cgpa": [r"av(?:era)?g\w*[^\n]*\d"],
}

# ------------------------------------------------------------------ the sheets
# (label, title, statement, checks)
RUN = "run"
SHEET_A2 = [
    ("2.1", "BankAccount with a constructor",
     "Create a class BankAccount having account number, account holder name and balance, all "
     "initialised by a constructor, with methods to deposit, withdraw and display the balance.",
     [RUN, "a2:bank_fields", "a2:bank_deposit", "a2:bank_withdraw", "a2:bank_display"]),
    ("2.2", "Student array: highest CGPA",
     "Create a class Student with name, roll number and CGPA, a parameterized constructor; store N "
     "students in an array of objects and display the student with the highest CGPA.",
     [RUN, "a2:student_fields", "a2:student_ctor", "src:student_array", "py:highest_cgpa"]),
    ("2.3", "Rectangle with three constructors",
     "Create a class Rectangle with a no-argument constructor (length = breadth = 1), a one-parameter "
     "constructor (length = breadth) and a two-parameter constructor, and methods for area and perimeter.",
     [RUN, "a2:rect_ctors", "a2:rect_default", "a2:rect_square", "a2:rect_area", "a2:rect_perimeter"]),
    ("2.4", "Employee: constructor chaining with this()",
     "Create a class Employee with a default constructor, a constructor with name, and one with name "
     "and salary; use this() to invoke another constructor and display the values.",
     [RUN, "a2:emp_ctors", "src:this_call", "out:lines:3"]),
    ("2.5", "MobilePhone copy constructor and discount",
     "Create a class MobilePhone with brand, model and price. Create one object, create another with "
     "the copy constructor, apply a 15% discount to the copy and display both.",
     [RUN, "a2:phone_fields", "a2:phone_copy", "py:discount15"]),
]
SHEET_A3 = [
    ("3.1", "Result: overloaded calculateResult()",
     "Create a class Result with calculateResult(int,int,int), (int,int,int,int) and "
     "(double,double,double) that calculate and display the total and average.",
     [RUN, "a3:result_overloads", "a3:result_3int", "a3:result_4int", "a3:result_3dbl"]),
    ("3.2", "Display: overloaded show() and widening",
     "Create a class Display with show(int), show(float), show(double) and show(long); call show(10), "
     "show(10L), show(10.5f), show(10.5) and show('A').",
     [RUN, "a3:display_overloads", "out:char_as_int"]),
    ("3.3", "Ambiguous calculate(int, double) / calculate(double, int)",
     "Create calculate(int x, double y) and calculate(double x, int y); calculate(10, 20) is ambiguous, "
     "so modify the call (an explicit cast) so the program compiles.",
     [RUN, "a3:calc_overloads", "src:explicit_cast"]),
    ("3.4", "Student: overloaded constructors with this()",
     "Create a class Student with rollNo, name, department and cgpa and constructors Student(), "
     "(rollNo, name), (rollNo, name, department), (rollNo, name, department, cgpa), using this().",
     [RUN, "a3:student_fields", "a3:student_ctors", "src:this_call", "out:lines:3"]),
    ("3.5", "Number: overloaded constructors and widening",
     "Create a class Number with constructors Number(int), Number(long), Number(double), and create "
     "new Number(10), new Number(10L), new Number(10.5) and new Number('A').",
     [RUN, "a3:number_ctors", "src:number_char", "out:lines:3"]),
]
SHEET_A4 = {
    "4.1": ("Employee Management: access specifiers",
            "Employee with ID, name, private salary, protected department and public company name, a salary "
            "setter that refuses negative values, and a Manager subclass with designation and team size.",
            [RUN, "a4:mgr_extends_emp", "a4:salary_private", "a4:dept_protected", "a4:company_public",
             "a4:mgr_fields", "java:salary_negative"]),
    "4.2": ("Constructors in inheritance: default and super(...)",
            "Employee (name, employeeId, salary) with a default and a parameterized constructor; Manager with "
            "department, a default constructor and a parameterized one that calls super(...).",
            [RUN, "a4:mgr_extends_emp", "a4:emp_ctor_default", "a4:emp_ctor_param", "a4:mgr_ctor_param",
             "src:super_args", "a4:display_manager"]),
    "4.3": ("super() must be the first statement",
            "Employee's default constructor prints \"Employee constructor called\"; Manager's constructor calls "
            "super() and prints \"Manager constructor called\"; show the order of constructor execution.",
            [RUN, "a4:mgr_extends_emp", "src:super_call", "out:ctor_order", "a4:display_manager"]),
    "4.4": ("Shape: overriding area()",
            "A superclass Shape with void area(), and Circle, Rectangle and Triangle overriding it; create "
            "objects of each and invoke area().",
            [RUN, "a4:circle_shape", "a4:rect_shape", "a4:tri_shape", "a4:area_overridden", "out:lines:3"]),
    "4.5": ("Circle → Cylinder → Cone with super",
            "Circle (radius, area(), display(), static info()); Cylinder extends Circle with height, overriding "
            "area() using super, and surfacearea(); Cone extends Cylinder, overriding area().",
            [RUN, "a4:cyl_circle", "a4:cone_cyl", "a4:circle_info", "a4:cyl_overrides", "a4:cyl_surface",
             "src:super_method"]),
    "4.6": ("Runtime polymorphism: Employee[] and calculateSalary()",
            "Employee with calculateSalary(), overridden in PermanentEmployee, ContractEmployee and Intern; "
            "store them in Employee[] employees and call calculateSalary() in a loop.",
            [RUN, "a4:emp3_subclasses", "src:employee_array", "out:lines:3:loop"]),
    "4.7": ("Overriding displayRole() vs hiding static companyPolicy()",
            "Employee with displayRole() and static companyPolicy(); Manager and Developer override "
            "displayRole() and define their own static companyPolicy(); add an Intern subclass.",
            [RUN, "a4:role_overridden", "a4:policy_hidden", "a4:intern_extends", "out:role_messages",
             "out:general_policy"]),
    "4.8": ("Abstract Shape: Circle, Cylinder, Cone",
            "An abstract class Shape with abstract calculateArea() and calculateVolume() and a concrete "
            "displayShapeName(); Circle (2D), Cylinder and Cone (3D) as subclasses, used through Shape references.",
            [RUN, "a4:shape_abstract", "a4:shape_area_abs", "a4:circle_2d", "a4:cyl_3d", "a4:cone_3d",
             "a4:cyl_volume", "a4:cone_volume", "src:shape_ref"]),
    "4.9": ("Abstract multilevel: Animal → Mammal → Cow",
            "Abstract Animal (name, abstract makeSound(), eat()); abstract Mammal extends Animal (abstract "
            "giveBirth(), hasHair()); Cow implements both; use Mammal and Animal references.",
            [RUN, "a4:animal_abstract", "a4:mammal_abstract", "a4:mammal_is_abstract", "a4:cow_mammal",
             "a4:sound_abs", "a4:birth_abs", "a4:cow_overrides", "src:animal_refs"]),
    "4.10": ("Abstract Vehicle with a static counter",
             "Abstract Vehicle (vehicleNumber, brand, price, abstract calculateTax(), displayDetails(), static "
             "totalVehicles and getTotalVehicles()); Car and Bike with different tax rules.",
             [RUN, "a4:vehicle_abstract", "a4:tax_abs", "a4:car_vehicle", "a4:bike_vehicle", "a4:tax_overridden",
              "a4:vehicle_counter", "a4:total_method"]),
    "4.11": ("Payroll: permanent, contract and part-time employees",
             "Abstract Employee (ID, name, department, displayEmployeeDetails(), abstract calculateSalary()); "
             "permanent = basic + allowances − deductions, contract = contract amount, part-time = hours × rate.",
             [RUN, "a4:payroll_abstract", "a4:payroll_subclasses", "a4:parttime_salary", "a4:display_details",
              "out:lines:3"]),
    "4.12": ("UG and PG grading with an abstract class",
             "Students with roll number, name, department and marks; calculateGrade() and calculateCGPA() with "
             "different UG and PG grade tables; display results for 3 UG and 2 PG students.",
             [RUN, "a4:grade_abstract", "a4:grade_overridden", "src:cgpa_method", "out:lines:5"]),
    "4.13": ("Shapes through a Shape reference",
             "Abstract methods calculateArea() and calculateVolume(); accept different shapes through a Shape "
             "reference and calculate their properties dynamically.",
             [RUN, "a4:shape_abstract", "a4:shape_area_abs", "a4:volume_abs", "a4:shape_subclasses", "src:shape_ref"]),
}
SHEET_A5_C2 = [
    ("1", "Employee: overloading and overriding calculateSalary()",
     "Employee (name, basicSalary) with calculateSalary(double) and calculateSalary(double, double); "
     "Manager and Developer override calculateSalary(double).",
     [RUN, "a5:mgr_emp", "a5:dev_emp", "a5:salary_overloads", "a5:salary_overridden", "out:lines:3"]),
    ("2", "Shape: overloaded and overridden area()",
     "Shape with area(double), area(double, double); Circle, Rectangle and Triangle override the right one; "
     "use Shape references without if-else/switch on the shape type.",
     [RUN, "a4:circle_shape", "a4:rect_shape", "a4:tri_shape", "a5:area_overloads", "a5:area_overridden",
      "src:shape_ref", "src:no_type_switch"]),
    ("3", "Vehicle fares: Car, Bike, Auto",
     "Vehicle with calculateFare(distance), (distance, waitingTime), (distance, waitingTime, serviceCharge); "
     "Car, Bike and Auto override calculateFare(distance); use Vehicle references.",
     [RUN, "a5:car_vehicle", "a5:bike_vehicle", "a5:auto_vehicle", "a5:fare_overloads", "a5:fare_overridden",
      "src:vehicle_ref"]),
]
SHEET_A6_C2 = [
    ("1", "Advanced Bank Account Management System",
     "BankAccount (private accountNumber, accountHolderName, balance, branchName) with SavingsAccount "
     "(interest, minimum balance), CurrentAccount (overdraft limit) and PremiumSavingsAccount (reward points, "
     "cashback); overloaded deposit(), overridden withdraw()/calculateInterest(), processTransaction().",
     [RUN, "a6:savings_bank", "a6:current_bank", "a6:premium_savings", "a6:balance_private", "a6:savings_min",
      "a6:savings_ok", "a6:current_overdraft", "a6:current_limit", "a6:deposit_overloads", "a6:premium_points",
      "a6:interest_overridden", "src:process_transaction"]),
]
SHEET_MIDSEM = [
    ("1", "Student records: constructors, array, highest and average CGPA",
     "Student (roll number, name, department, CGPA) with default and parameterized constructors chained "
     "with this(); N students in an array; the highest and the average CGPA.",
     [RUN, "a3:student_fields", "mid:student_ctors", "src:this_call", "src:student_array", "py:highest_cgpa",
      "out:average_cgpa"]),
    ("2", "BankAccount: encapsulated balance",
     "Account number, holder name, private balance; deposit() (positive only), withdraw() (not beyond the "
     "balance) and checkBalance(); at least three accounts.",
     [RUN, "mid:bank_private", "a2:bank_deposit", "mid:bank_negative_dep", "mid:bank_overdraw", "out:lines:3"]),
    ("3", "Result: overloaded methods and constructors",
     "calculateResult(int,int,int), (int,int,int,int), (double,double,double) showing total and average; "
     "overloaded constructors with four different invocations.",
     [RUN, "a3:result_overloads", "a3:result_3int", "a3:result_4int", "a3:result_3dbl"]),
    ("4", "Payroll: Manager, Developer, Intern",
     "Employee (ID, name, department) with Manager, Developer and Intern overriding calculateSalary(), "
     "using super().", [RUN, "mid:emp_subclasses", "src:super_args", "out:lines:3"]),
    ("5", "Abstract Shape[]: Circle, Rectangle, Triangle",
     "Abstract Shape with calculateArea(); Circle, Rectangle and Triangle in a Shape[] array, called in a loop.",
     [RUN, "a4:shape_abstract", "a4:shape_area_abs", "a4:area_overridden", "mid:shape_array"]),
    ("6", "Person → Employee → Manager constructors",
     "Person (name, age), Employee (ID, salary), Manager (department, team size); constructors calling "
     "super() and showing the order of execution.",
     [RUN, "mid:person_chain", "src:super_args", "out:lines:3"]),
    ("7", "Abstract Vehicle with a static counter",
     "Abstract Vehicle with calculateTax(), Car and Bike, displayDetails(), static totalVehicles and a static "
     "method returning it.", SHEET_A4["4.10"][2]),
    ("8", "Overriding displayRole() vs hiding companyPolicy()",
     "Employee with displayRole() and static companyPolicy(), redefined in Manager and Developer.",
     [RUN, "a4:role_overridden", "a4:policy_hidden"]),
    ("9", "Circle, Cylinder, Cone, Rectangle hierarchy",
     "A hierarchy where 2-D shapes don't have to implement volume; runtime polymorphism.",
     [RUN, "a4:cyl_volume", "a4:cone_volume", "src:shape_ref"]),
    ("10", "University payroll",
     "Abstract Employee with Faculty, TechnicalStaff and AdministrativeStaff, Employee[] employees, a static "
     "count of employees and the total payroll.",
     [RUN, "a4:payroll_abstract", "mid:faculty", "src:employee_array", "mid:emp_counter", "out:lines:3"]),
]


def _a4(*labels):
    return [(l, *SHEET_A4[l]) for l in labels]


# pack name -> the sheet's questions
PACKS: dict[str, list[tuple[str, str, str, list[str]]]] = {
    "oop-assignment-2": SHEET_A2,
    "oop-assignment-3": SHEET_A3,
    "oop-assignment-4": _a4("4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7"),
    "oop-assignment-4-part-1": _a4("4.1", "4.2", "4.3"),
    "oop-assignment-4-part-2": _a4("4.4", "4.5", "4.6", "4.7"),
    "oop-assignment-4-part-3": _a4("4.8", "4.9", "4.10"),
    "oop-assignment-4-part-4": _a4("4.11", "4.12", "4.13"),
    "oop-overloading-overriding": SHEET_A5_C2,
    "oop-bank-system": SHEET_A6_C2,
    "oop-mid-sem": SHEET_MIDSEM,
}
