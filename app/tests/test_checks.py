"""Requirement checks for the OOP lab Assignment 1, run through the real sandbox runner
against correct and broken versions of each program."""
import shutil
from types import SimpleNamespace

import pytest
from conftest import LocalSandbox

from autograder import checks
from autograder.grading import _grade_by_checks
from autograder.models import ProgramResult, TestCase

pytestmark = pytest.mark.skipif(shutil.which("javac") is None, reason="needs a JDK")


def grade(code: str, question: str, claimed: str | None = None):
    ids = checks.OOP_ASSIGNMENT_1[question]
    tests = [TestCase(stdin="", expected=checks.CHECKS[i], rule=i, weight=1.0, hidden=False) for i in ids]
    from docextract.langdetect import java_entrypoint
    p = SimpleNamespace(language="java", code=code, entrypoint=java_entrypoint(code),
                        ocr=False, claimed_output=claimed, claimed_from_image=False)
    pr = ProgramResult(question_label=question, language="java", code=code)
    flags = []
    _grade_by_checks(LocalSandbox(), SimpleNamespace(time_limit_s=5.0), SimpleNamespace(label=question),
                     p, pr, tests, flags)
    return {r.rule: (r.passed, r.note) for r in pr.runs}, pr, flags


def passed(res):
    return {k for k, (ok, _) in res.items() if ok}


# ---------------------------------------------------------------- Q1 Car
CAR_OK = """
class Car {
    String brand, model, color; int maxSpeed;
    Car(String b, String m, String c, int s) { brand = b; model = m; color = c; maxSpeed = s; }
    void display() { System.out.println(brand + " " + model + " " + color + " " + maxSpeed); }
}
public class CarDemo {
    public static void main(String[] a) {
        new Car("Tata", "Nexon", "Red", 160).display();
        new Car("BMW", "X1", "Blue", 220).display();
        new Car("Ford", "Figo", "White", 170).display();
    }
}
"""


def test_q1_car():
    res, pr, _ = grade(CAR_OK, "1")
    assert passed(res) == {"run", "java:car_fields", "out:lines:3"} and pr.score == 1.0
    one_car = CAR_OK.replace('new Car("BMW", "X1", "Blue", 220).display();', "").replace(
        'new Car("Ford", "Figo", "White", 170).display();', "")
    res, pr, _ = grade(one_car.replace("color", "shade"), "1")
    assert passed(res) == {"run"} and "colour" in res["java:car_fields"][1]


# ---------------------------------------------------------------- Q2 Student
STUDENT_OK = """
class Student {
    String name; int roll; String dept; double cgpa;
    Student(String n, int r, String d, double c) { name = n; roll = r; dept = d; cgpa = c; }
}
public class Main {
    public static void main(String[] a) {
        Student[] s = { new Student("Asha", 1, "IT", 8.7), new Student("Ravi", 2, "IT", 9.4),
                        new Student("Mina", 3, "CSE", 9.1) };
        Student best = s[0];
        for (Student x : s) if (x.cgpa > best.cgpa) best = x;
        System.out.println(best.name + " " + best.roll + " " + best.dept + " " + best.cgpa);
    }
}
"""


def test_q2_student():
    res, pr, _ = grade(STUDENT_OK, "2")
    assert pr.score == 1.0, res
    wrong = STUDENT_OK.replace("x.cgpa > best.cgpa", "x.cgpa < best.cgpa")      # prints the lowest
    no_array = """
class Student { String name; int roll; String dept; double cgpa;
    Student(String n, int r, String d, double c) { name = n; roll = r; dept = d; cgpa = c; } }
public class Main { public static void main(String[] a) {
    Student s1 = new Student("Asha", 1, "IT", 8.7); Student s2 = new Student("Ravi", 2, "IT", 9.4);
    System.out.println(s2.name + " " + s2.cgpa); } }
"""
    res, _, _ = grade(wrong, "2")
    assert not res["py:highest_cgpa"][0] and "9.4" in res["py:highest_cgpa"][1]
    res, _, _ = grade(no_array, "2")
    assert res["py:highest_cgpa"][0] and not res["src:student_array"][0]


# ---------------------------------------------------------------- Q3 Circle
CIRCLE_OK = """
class Circle {
    double radius;
    Circle(double r) { radius = r; }
    double area() { return 3.14 * radius * radius; }
    double circumference() { return 2 * 3.14 * radius; }
}
public class Main { public static void main(String[] a) {
    Circle c1 = new Circle(2), c2 = new Circle(3);
    System.out.println(c1.area() > c2.area() ? "c1 bigger" : "c2 bigger"); } }
"""


def test_q3_circle():
    res, pr, _ = grade(CIRCLE_OK, "3")
    assert pr.score == 1.0, res
    # computed in the constructor and printed instead of returned: still checked
    printed = """
class Circle { private double r; private double area, circumference;
    Circle(double r) { this.r = r; area = Math.PI * r * r; circumference = 2 * Math.PI * r; }
    void showArea() { System.out.println("Area: " + area); }
    void showCircumference() { System.out.println("Circumference = " + circumference); } }
public class Main { public static void main(String[] a) { new Circle(1).showArea(); } }
"""
    res, pr, _ = grade(printed, "3")
    assert pr.score == 1.0, res
    res, _, _ = grade(CIRCLE_OK.replace("2 * 3.14 * radius", "3.14 * radius"), "3")
    assert res["java:circle_area"][0] and not res["java:circle_circumference"][0]
    assert "9.42" in res["java:circle_circumference"][1]


# ---------------------------------------------------------------- Q4 Car speed
SPEED_OK = """
class Car {
    String brand, model; private int speed;
    Car(String b, String m) { brand = b; model = m; }
    void increaseSpeed(int d) { speed = Math.min(180, speed + d); }
    void decreaseSpeed(int d) { speed = Math.max(0, speed - d); }
    void display() { System.out.println(speed); }
}
public class Main { public static void main(String[] a) { Car c = new Car("Tata", "Nexon"); c.increaseSpeed(50); c.display(); } }
"""


def test_q4_speed():
    res, pr, _ = grade(SPEED_OK, "4")
    assert pr.score == 1.0, res
    unbounded = SPEED_OK.replace("Math.min(180, speed + d)", "speed + d").replace("private int speed", "int speed")
    res, _, _ = grade(unbounded, "4")
    assert passed(res) == {"run", "java:speed_min"}
    assert "520" in res["java:speed_max"][1] or "500" in res["java:speed_max"][1]
    # no-argument accelerate/brake, called repeatedly
    steps = """
class Car { String brand, model; private double speed;
    void accelerate() { if (speed + 10 <= 180) speed += 10; }
    void brake() { if (speed - 10 >= 0) speed -= 10; } }
public class Main { public static void main(String[] a) { new Car().accelerate(); } }
"""
    res, pr, _ = grade(steps, "4")
    assert pr.score == 1.0, res


# ---------------------------------------------------------------- Q5 Employee
EMP_OK = """
class Employee {
    int id; String name; private double salary;
    Employee(int id, String name) { this.id = id; this.name = name; }
    void setSalary(double s) { if (s >= 0) salary = s; else System.out.println("Invalid"); }
    double getSalary() { return salary; }
}
public class Main { public static void main(String[] a) { Employee e = new Employee(1, "Asha"); e.setSalary(100); System.out.println(e.getSalary()); } }
"""


def test_q5_employee():
    res, pr, _ = grade(EMP_OK, "5")
    assert pr.score == 1.0, res
    res, _, _ = grade(EMP_OK.replace("if (s >= 0) salary = s; else System.out.println(\"Invalid\");", "salary = s;"), "5")
    assert passed(res) == {"run", "java:salary_private", "java:salary_set_get"}
    res, _, _ = grade(EMP_OK.replace("double getSalary() { return salary; }", "")
                      .replace("System.out.println(e.getSalary());", ""), "5")
    assert not res["java:salary_set_get"][0] and "retrieve" in res["java:salary_set_get"][1]


# ---------------------------------------------------------------- Q6 ATM
ATM_OK = """
class ATM {
    private int pin; private double balance;
    ATM(int pin, double balance) { this.pin = pin; this.balance = balance; }
    void changePin(int oldPin, int newPin) { if (oldPin == pin) pin = newPin; }
    void deposit(double amt) { if (amt > 0) balance += amt; }
    void withdraw(int p, double amt) { if (p == pin && amt <= balance) balance -= amt; else System.out.println("Denied"); }
    double checkBalance() { return balance; }
}
public class Main { public static void main(String[] a) { ATM m = new ATM(1111, 500); m.withdraw(1111, 100); System.out.println(m.checkBalance()); } }
"""


def test_q6_atm():
    res, pr, _ = grade(ATM_OK, "6")
    assert pr.score == 1.0, res
    no_pin_check = ATM_OK.replace("if (p == pin && amt <= balance)", "if (amt <= balance)")
    res, _, _ = grade(no_pin_check, "6")
    assert not res["java:atm_wrong_pin"][0] and res["java:atm_right_pin"][0]
    neg = ATM_OK.replace("if (amt > 0) balance += amt;", "balance += amt;")
    res, _, _ = grade(neg, "6")
    assert not res["java:atm_deposit_negative"][0] and "to 1134" in res["java:atm_deposit_negative"][1]
    # PIN entered first through a separate method; amount-only withdraw; String PIN
    login = """
class ATM { private String pin = "4321"; private double balance = 2000; private boolean ok;
    boolean verifyPin(String p) { ok = p.equals(pin); return ok; }
    void deposit(double d) { if (d < 0) throw new IllegalArgumentException("negative"); balance += d; }
    void withdraw(double d) { if (ok && d <= balance) balance -= d; } }
public class Main { public static void main(String[] a) { ATM m = new ATM(); m.verifyPin("4321"); m.withdraw(5); } }
"""
    res, pr, _ = grade(login, "6")
    assert pr.score == 1.0, res


# ---------------------------------------------------------------- general
def test_compile_error_fails_every_check():
    res, pr, flags = grade(CAR_OK.replace("display();", "display()"), "1")
    assert pr.score == 0.0 and pr.compile_status == "COMPILE_ERROR"
    assert all(not ok for ok, _ in res.values()) and flags[0]["code"] == "COMPILE_ERROR"


def test_program_waiting_for_keyboard_input_still_runs():
    reads = CAR_OK.replace("public static void main(String[] a) {",
                           "public static void main(String[] a) {\n java.util.Scanner sc = new java.util.Scanner(System.in);"
                           " String b = sc.nextLine();")
    res, _, _ = grade(reads, "1")
    assert res["run"][0] and "keyboard" in res["run"][1]
    assert res["java:car_fields"][0]       # behaviour checks don't depend on main


def test_install_adds_checks_and_keeps_io_tests():
    from autograder.models import Question
    q = Question(label="4", title="Car Speed Control")
    q.tests.append(TestCase(stdin="5\n", expected="5", source="manual"))
    a = SimpleNamespace(questions=[q, Question(label="9", title="extra")])
    db = SimpleNamespace(flush=lambda: None)
    assert checks.install(db, a, "oop-assignment-1") == 4
    assert [t.rule or "" for t in q.tests] == ["", "run", "java:speed_private", "java:speed_max", "java:speed_min"]
    assert checks.install(db, a, "oop-assignment-1") == 4 and len(q.tests) == 5     # replaces, not duplicates


def test_upgrading_an_existing_database_adds_the_check_columns(tmp_path):
    """The bug this guards: an empty-string default was written as `DEFAULT ` (invalid SQL),
    so the app could not start on a database made by the previous version."""
    from sqlalchemy import create_engine, inspect, text
    from autograder.db import Base, _add_missing_columns
    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        c.execute(text("ALTER TABLE runs DROP COLUMN note"))
        c.execute(text("ALTER TABLE runs DROP COLUMN rule"))
        c.execute(text("ALTER TABLE test_cases DROP COLUMN rule"))
        c.execute(text("INSERT INTO test_cases (id, question_id, stdin, expected, hidden, weight, source, position) "
                       "VALUES (1, 1, '5', '5', 0, 1.0, 'manual', 0)"))
    added = _add_missing_columns(eng)
    assert {"runs.note", "runs.rule", "test_cases.rule"} <= set(added)
    assert {"rule", "note"} <= {c["name"] for c in inspect(eng).get_columns("runs")}
    with eng.connect() as c:                      # existing tests become plain input/output tests
        assert c.execute(text("SELECT rule FROM test_cases WHERE id = 1")).scalar() == ""


# ---------------------------------------------------------------- designs seen in real submissions
def test_radii_field_and_getter_taking_an_argument():
    res, pr, _ = grade(CIRCLE_OK.replace("radius", "radii"), "3")
    assert pr.score == 1.0, res
    emp = EMP_OK.replace("double getSalary() { return salary; }", "double RetrieveSalary(int v) { return salary; }") \
                .replace("e.getSalary()", "e.RetrieveSalary(0)")
    res, pr, _ = grade(emp, "5")
    assert pr.score == 1.0, res


def test_class_declared_inside_another_class():
    nested = """
public class Main {
    static class ATM {
        private int PIN = 1111; private double Balance = 500;
        void deposit(int n) { if (n > 0) Balance += n; }
        void withdraw(int pin, int n) { if (pin == PIN && n <= Balance) Balance -= n; }
    }
    public static void main(String[] a) { new ATM().deposit(5); }
}
"""
    res, pr, _ = grade(nested, "6")
    assert pr.score == 1.0, res


def test_unusual_speed_method_names():
    typo = SPEED_OK.replace("increaseSpeed", "edd_speed").replace("decreaseSpeed", "zub_speed") \
                   .replace("c.increaseSpeed(50)", "c.edd_speed(50)")
    res, pr, _ = grade(typo, "4")
    assert pr.score == 1.0, res
    one = """
class Car { String Brand, Model; private int speed;
    void Speed(int s) { if (s >= 0 && s <= 180) speed = s; } }
public class Main { public static void main(String[] a) { new Car().Speed(50); } }
"""
    res, pr, _ = grade(one, "4")
    assert pr.score == 1.0, res


def test_interactive_atm_reading_amount_and_pin_from_the_keyboard():
    interactive = """
import java.util.Scanner;
class ATM {
    private int pin = 1234; private double balance = 1000;
    Scanner sc = new Scanner(System.in);
    void deposit() { System.out.print("Amount: "); double a = sc.nextDouble(); if (a > 0) balance += a; }
    void withdraw() { System.out.print("PIN: "); int p = sc.nextInt(); System.out.print("Amount: "); double a = sc.nextDouble();
                      if (p == pin && a <= balance) balance -= a; else System.out.println("Wrong PIN"); }
}
public class Main { public static void main(String[] x) { new ATM(); } }
"""
    res, pr, _ = grade(interactive, "6")
    assert passed(res) >= {"java:atm_deposit_negative", "java:atm_wrong_pin", "java:atm_right_pin"}, res
    with_scanner_arg = """
import java.util.Scanner;
class ATM {
    private int pin = 4321; private double balance = 800;
    void deposit(Scanner sc) { double a = sc.nextDouble(); balance += a; }
    void withdraw(Scanner sc) { double a = sc.nextDouble(); int p = sc.nextInt(); if (p == pin) balance -= a; }
}
public class Main { public static void main(String[] x) { } }
"""
    res, _, _ = grade(with_scanner_arg, "6")
    assert not res["java:atm_deposit_negative"][0]                # accepts -100: a real mistake
    assert res["java:atm_wrong_pin"][0] and res["java:atm_right_pin"][0], res


# ---------------------------------------------------------------- the output the student showed
@pytest.mark.parametrize("shown, prints, image, differs", [
    # real cases: OCR misreads and cropped screenshots are not suspicious
    ("Maximum Speed: 18@ km/h\nBrand: Honda", "Maximum Speed: 180 km/h\nBrand: Honda\nModel: City\n", True, False),
    ("Model : A@Q\nColor : white", "Model : A00\nColor : white\nMaxSpeed : 100\n", True, False),
    ("Name: Sayak Roll: 24 CGPA: 99.5", "Name: Sayak Roll: 24 CGPA: 9.5\n", True, False),
    ("Salary set successfully!", "Salary set successfully!\n100000.0\n", True, False),
    ("Brand: Tata\nSpeed: 120", "Brand: Tata\nSpeed: 120\nBrand: Ford\n", False, False),
    # a different program's output, or invented numbers, is
    ("Area : 78.5\nCircumference : 31.4", "Brand: Tata\nSpeed: 120\n", True, True),
    ("Total balance: 5000\nWithdrawn: 200", "Total balance: 1000\nWithdrawn: 900\n", False, True),
])
def test_shown_output_comparison(shown, prints, image, differs):
    assert checks.shown_output_differs(shown, prints, image) is differs


# a real Assignment submission: the third CGPA is written as a whole number (9), and the
# program correctly prints that student; the check used to skip the 9 and expect 8.9
CGPA_WHOLE = '''class Student {
    String name, dept; int rollNo; double cgpa;
    Student(String name, int rollNo, String dept, double cgpa) {
        this.name = name; this.rollNo = rollNo; this.dept = dept; this.cgpa = cgpa; }
    public static void main(String[] args) {
        Student[] students = new Student[3];
        students[0] = new Student("a",1,"IT",8.9);
        students[1] = new Student("b",2,"CST",7.8);
        students[2] = new Student("c",3,"IT",9);
    }
}'''


def test_highest_cgpa_written_as_a_whole_number():
    ok, note = checks.check_highest_cgpa(CGPA_WHOLE, "c 3 IT 9.0\n")
    assert ok and "9" in note
    ok, note = checks.check_highest_cgpa(CGPA_WHOLE, "a 1 IT 8.9\n")       # the wrong student
    assert not ok and "is 9;" in note


def test_highest_cgpa_read_from_the_constructor_position():
    # CGPA comes second and the roll number (10) is also in 0-10: only the cgpa slot counts
    code = '''class Student { String n; double cg; int roll;
        Student(String n, double cg, int roll) { this.n = n; this.cg = cg; this.roll = roll; }
        static void m() { new Student("x, y", 9, 4); new Student("z", 8.5, 10); } }'''
    assert checks.check_highest_cgpa(code, "x, y 9.0 4")[0]
    assert not checks.check_highest_cgpa(code, "z 8.5 10")[0]


def test_highest_cgpa_whatever_the_class_is_called():
    # real submissions named the class `student` and `Students`
    lower = '''class student { String name; int roll; String dept; double cgpa;
        student(String name, int roll, String dept, double cgpa) { this.cgpa = cgpa; }
        public static void main(String[] a) { student s[] = new student[3];
            s[0] = new student("ramu", 88, "it", 9.2); s[1] = new student("vishnu", 45, "cst", 8);
            s[2] = new student("gowtham", 44, "it", 9.5); } }'''
    assert checks.check_highest_cgpa(lower, "name:gowthamroll:44deptitcgpa9.5")[0]    # glued to the word
    plural = lower.replace("student", "Students")
    assert checks.check_highest_cgpa(plural, "gowtham 44 it 9.5")[0]
    assert not checks.check_highest_cgpa(plural, "ramu 88 it 9.2")[0]


def test_highest_cgpa_float_suffix_and_default_zero():
    # `8.82f` in the constructor call, `s1.cgpa = 9.08f;` on a field (real submissions)
    ctor = '''class Student { float Cgpa; Student(String n, int r, String d, float CGPA) { Cgpa = CGPA; }
        static void m() { new Student("A", 64, "IT", 8.82f); new Student("B", 79, "CST", 9.02f); } }'''
    assert checks.check_highest_cgpa(ctor, "B 79 CST 9.02")[0]
    field = '''class student { float cgpa; static void m() { student s1 = new student(); s1.cgpa = 9.08f;
        student s2 = new student(); s2.cgpa = 8.0f; } }'''
    assert checks.check_highest_cgpa(field, "CGPA : 9.08")[0]
    # a default `cgpa = 0;` with the real values read from the keyboard is not a CGPA of 0
    typed = '''class Student { double cgpa; Student() { cgpa = 0; }
        void read(java.util.Scanner sc) { cgpa = sc.nextDouble(); } }'''
    ok, note = checks.check_highest_cgpa(typed, "x 9 9 9.0\n", typed=True)
    assert ok and "is 0" not in note
