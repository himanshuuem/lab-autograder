"""Requirement checks for the other OOP lab sheets (packs.py), run through the real sandbox
runner: a correct answer to every question passes every check, and typical mistakes fail
the check about them."""
import shutil
from types import SimpleNamespace

import pytest
from conftest import LocalSandbox

from autograder import checks, packs
from autograder.grading import _grade_by_checks
from autograder.models import ProgramResult, TestCase

pytestmark = pytest.mark.skipif(shutil.which("javac") is None, reason="needs a JDK")


def grade(code: str, pack: str, label: str):
    ids = checks.PACKS[pack][label]
    tests = [TestCase(stdin="", expected=checks.CHECKS[i], rule=i, weight=1.0, hidden=False) for i in ids]
    from docextract.langdetect import java_entrypoint
    p = SimpleNamespace(language="java", code=code, entrypoint=java_entrypoint(code),
                        ocr=False, claimed_output=None, claimed_from_image=False)
    pr = ProgramResult(question_label=label, language="java", code=code)
    _grade_by_checks(LocalSandbox(), SimpleNamespace(time_limit_s=5.0), SimpleNamespace(label=label),
                     p, pr, tests, [])
    return {r.rule: (r.passed, r.note) for r in pr.runs}


def failed(res):
    return {k: note for k, (ok, note) in res.items() if not ok}


# One correct answer per question, written the way students write them.
GOOD = {
    ("oop-assignment-2", "2.1"): """
class BankAccount {
    long accountNumber; String holderName; double balance;
    BankAccount(long n, String h, double b) { accountNumber = n; holderName = h; balance = b; }
    void deposit(double amt) { if (amt > 0) balance += amt; }
    void withdraw(double amt) { if (amt <= balance) balance -= amt; else System.out.println("Insufficient balance"); }
    void displayBalance() { System.out.println("Balance: " + balance); }
}
public class Main {
    public static void main(String[] args) {
        BankAccount a = new BankAccount(1001, "Asha", 5000);
        a.deposit(1000); a.withdraw(2000); a.displayBalance();
    }
}""",
    ("oop-assignment-2", "2.2"): """
class Student {
    String name; int rollNo; double cgpa;
    Student(String name, int rollNo, double cgpa) { this.name = name; this.rollNo = rollNo; this.cgpa = cgpa; }
}
public class Main {
    public static void main(String[] args) {
        Student[] s = { new Student("Asha", 1, 8.7), new Student("Ravi", 2, 9.4), new Student("Mina", 3, 9.1) };
        Student best = s[0];
        for (Student x : s) if (x.cgpa > best.cgpa) best = x;
        System.out.println("Highest CGPA: " + best.name + " " + best.cgpa);
    }
}""",
    ("oop-assignment-2", "2.3"): """
class Rectangle {
    double length, breadth;
    Rectangle() { length = 1; breadth = 1; }
    Rectangle(double side) { length = side; breadth = side; }
    Rectangle(double l, double b) { length = l; breadth = b; }
    double area() { return length * breadth; }
    double perimeter() { return 2 * (length + breadth); }
}
public class Main {
    public static void main(String[] args) {
        Rectangle r = new Rectangle(4, 5);
        System.out.println(r.area() + " " + r.perimeter());
    }
}""",
    ("oop-assignment-2", "2.4"): """
class Employee {
    String name; double salary;
    Employee() { this("Unknown"); }
    Employee(String name) { this(name, 10000); }
    Employee(String name, double salary) { this.name = name; this.salary = salary; }
    void display() { System.out.println(name + " " + salary); }
}
public class Main {
    public static void main(String[] args) {
        new Employee().display(); new Employee("Ravi").display(); new Employee("Asha", 50000).display();
    }
}""",
    ("oop-assignment-2", "2.5"): """
class MobilePhone {
    String brand, model; double price;
    MobilePhone(String b, String m, double p) { brand = b; model = m; price = p; }
    MobilePhone(MobilePhone o) { brand = o.brand; model = o.model; price = o.price; }
    void display() { System.out.println(brand + " " + model + " " + price); }
}
public class Main {
    public static void main(String[] args) {
        MobilePhone a = new MobilePhone("Samsung", "M34", 20000);
        MobilePhone b = new MobilePhone(a);
        b.price = b.price - b.price * 15 / 100;
        a.display(); b.display();
    }
}""",
    ("oop-assignment-3", "3.1"): """
class Result {
    void calculateResult(int a, int b, int c) { int t = a + b + c; System.out.println("Total = " + t + " Average = " + t / 3.0); }
    void calculateResult(int a, int b, int c, int d) { int t = a + b + c + d; System.out.println("Total = " + t + " Average = " + t / 4.0); }
    void calculateResult(double a, double b, double c) { double t = a + b + c; System.out.println("Total = " + t + " Average = " + t / 3); }
}
public class Main {
    public static void main(String[] args) {
        Result r = new Result();
        r.calculateResult(70, 80, 90); r.calculateResult(70, 80, 90, 100); r.calculateResult(70.5, 80.5, 90.5);
    }
}""",
    ("oop-assignment-3", "3.2"): """
class Display {
    void show(int x) { System.out.println("int: " + x); }
    void show(long x) { System.out.println("long: " + x); }
    void show(float x) { System.out.println("float: " + x); }
    void show(double x) { System.out.println("double: " + x); }
}
public class Main {
    public static void main(String[] args) {
        Display d = new Display();
        d.show(10); d.show(10L); d.show(10.5f); d.show(10.5); d.show('A');
    }
}""",
    ("oop-assignment-3", "3.3"): """
public class Test {
    void calculate(int x, double y) { System.out.println("int, double"); }
    void calculate(double x, int y) { System.out.println("double, int"); }
    public static void main(String[] args) {
        Test t = new Test();
        // t.calculate(10, 20);   ambiguous
        t.calculate((double) 10, 20);
    }
}""",
    ("oop-assignment-3", "3.4"): """
class Student {
    int rollNo; String name, department; double cgpa;
    Student() { this(0, "NA"); }
    Student(int rollNo, String name) { this(rollNo, name, "IT"); }
    Student(int rollNo, String name, String department) { this(rollNo, name, department, 0.0); }
    Student(int rollNo, String name, String department, double cgpa) {
        this.rollNo = rollNo; this.name = name; this.department = department; this.cgpa = cgpa; }
    void show() { System.out.println(rollNo + " " + name + " " + department + " " + cgpa); }
}
public class Main {
    public static void main(String[] args) {
        new Student().show(); new Student(1, "Asha").show(); new Student(2, "Ravi", "CSE").show();
        new Student(3, "Mina", "IT", 9.1).show();
    }
}""",
    ("oop-assignment-3", "3.5"): """
class Number {
    Number(int x) { System.out.println("int constructor " + x); }
    Number(long x) { System.out.println("long constructor " + x); }
    Number(double x) { System.out.println("double constructor " + x); }
}
public class Main {
    public static void main(String[] args) {
        Number n1 = new Number(10); Number n2 = new Number(10L); Number n3 = new Number(10.5); Number n4 = new Number('A');
    }
}""",
    ("oop-assignment-4", "4.1"): """
class Employee {
    int empId; String empName; private double salary; protected String department; public String companyName = "TCS";
    void setSalary(double s) { if (s >= 0) salary = s; else System.out.println("Salary can't be negative"); }
    double getSalary() { return salary; }
    void display() { System.out.println(empId + " " + empName + " " + salary + " " + department); }
}
class Manager extends Employee {
    String designation; int teamMembers;
    void setManager(String d, int t) { designation = d; teamMembers = t; department = "Sales"; }
    void displayManager() { System.out.println(designation + " " + teamMembers + " " + department + " " + getSalary()); }
}
public class Main {
    public static void main(String[] args) {
        Employee e = new Employee(); e.setSalary(30000); e.setSalary(-5); e.display();
        Manager m = new Manager(); m.setManager("Lead", 5); m.displayManager();
    }
}""",
    ("oop-assignment-4", "4.2"): """
class Employee {
    String name; int employeeId; double salary;
    Employee() { name = "None"; employeeId = 0; salary = 0; }
    Employee(String n, int id, double s) { name = n; employeeId = id; salary = s; }
    void displayEmployee() { System.out.println(name + " " + employeeId + " " + salary); }
}
class Manager extends Employee {
    String department;
    Manager() { department = "None"; }
    Manager(String n, int id, double s, String d) { super(n, id, s); department = d; }
    void displayManager() { displayEmployee(); System.out.println(department); }
}
public class Main {
    public static void main(String[] args) { new Manager("Asha", 7, 90000, "HR").displayManager(); }
}""",
    ("oop-assignment-4", "4.3"): """
class Employee {
    String name; int employeeId; double salary;
    Employee() { name = "None"; System.out.println("Employee constructor called"); }
    void displayEmployee() { System.out.println(name + " " + employeeId + " " + salary); }
}
class Manager extends Employee {
    String department;
    Manager() { super(); department = "HR"; System.out.println("Manager constructor called"); }
    void displayManager() { displayEmployee(); System.out.println(department); }
}
public class Main {
    public static void main(String[] args) { new Manager().displayManager(); }
}""",
    ("oop-assignment-4", "4.4"): """
class Shape { void area() { System.out.println("Area of shape"); } }
class Circle extends Shape { double r = 2; void area() { System.out.println("Circle area " + Math.PI * r * r); } }
class Rectangle extends Shape { double l = 4, b = 5; void area() { System.out.println("Rectangle area " + l * b); } }
class Triangle extends Shape { double b = 4, h = 3; void area() { System.out.println("Triangle area " + 0.5 * b * h); } }
public class Main {
    public static void main(String[] args) { new Circle().area(); new Rectangle().area(); new Triangle().area(); }
}""",
    ("oop-assignment-4", "4.5"): """
class Circle {
    double radius;
    Circle(double r) { radius = r; }
    double area() { return Math.PI * radius * radius; }
    void display() { System.out.println("Radius " + radius + " area " + area()); }
    static void info() { System.out.println("Shapes"); }
}
class Cylinder extends Circle {
    double height;
    Cylinder(double r, double h) { super(r); height = h; }
    double area() { return 2 * super.area() + 2 * Math.PI * radius * height; }
    double surfaceArea() { return area(); }
    void display() { System.out.println("Cylinder area " + area()); }
}
class Cone extends Cylinder {
    Cone(double r, double h) { super(r, h); }
    double area() { double l = Math.sqrt(radius * radius + height * height); return Math.PI * radius * (radius + l); }
}
public class Main {
    public static void main(String[] args) { Circle.info(); new Cylinder(3, 5).display(); System.out.println(new Cone(3, 4).area()); }
}""",
    ("oop-assignment-4", "4.6"): """
class Employee { void calculateSalary() { System.out.println("Employee salary"); } }
class PermanentEmployee extends Employee { void calculateSalary() { System.out.println("Permanent: 50000"); } }
class ContractEmployee extends Employee { void calculateSalary() { System.out.println("Contract: 30000"); } }
class Intern extends Employee { void calculateSalary() { System.out.println("Intern: 10000"); } }
public class Main {
    public static void main(String[] args) {
        Employee[] employees = new Employee[3];
        employees[0] = new PermanentEmployee(); employees[1] = new ContractEmployee(); employees[2] = new Intern();
        for (int i = 0; i < employees.length; i++) employees[i].calculateSalary();
    }
}""",
    ("oop-assignment-4", "4.7"): """
class Employee {
    void displayRole() { System.out.println("Employee works for the organization."); }
    static void companyPolicy() { System.out.println("General company policy."); }
}
class Manager extends Employee {
    void displayRole() { System.out.println("Manager manages the team."); }
    static void companyPolicy() { System.out.println("Manager follows managerial policy."); }
}
class Developer extends Employee {
    void displayRole() { System.out.println("Developer develops software."); }
    static void companyPolicy() { System.out.println("Developer follows technical policy."); }
}
class Intern extends Employee { void displayRole() { System.out.println("Intern learns."); } }
public class Main {
    public static void main(String[] args) {
        Employee e1 = new Manager(); Employee e2 = new Developer();
        e1.displayRole(); e2.displayRole(); e1.companyPolicy(); Manager.companyPolicy();
    }
}""",
    ("oop-assignment-4-part-3", "4.8"): """
abstract class Shape {
    abstract double calculateArea();
    abstract double calculateVolume();
    void displayShapeName() { System.out.println(getClass().getSimpleName()); }
}
class Circle extends Shape {
    double radius; Circle(double r) { radius = r; }
    double calculateArea() { return Math.PI * radius * radius; }
    double calculateVolume() { return 0; }
}
class Cylinder extends Shape {
    double radius, height; Cylinder(double r, double h) { radius = r; height = h; }
    double calculateArea() { return 2 * Math.PI * radius * (radius + height); }
    double calculateVolume() { return Math.PI * radius * radius * height; }
}
class Cone extends Shape {
    double radius, height; Cone(double r, double h) { radius = r; height = h; }
    double calculateArea() { return Math.PI * radius * (radius + Math.sqrt(radius * radius + height * height)); }
    double calculateVolume() { return Math.PI * radius * radius * height / 3; }
}
public class Main {
    public static void main(String[] args) {
        Shape[] s = { new Circle(3), new Cylinder(3, 5), new Cone(3, 4) };
        for (Shape x : s) { x.displayShapeName(); System.out.println(x.calculateArea() + " " + x.calculateVolume()); }
    }
}""",
    ("oop-assignment-4-part-3", "4.9"): """
abstract class Animal {
    String name;
    abstract void makeSound();
    void eat() { System.out.println(name + " eats"); }
}
abstract class Mammal extends Animal {
    abstract void giveBirth();
    void hasHair() { System.out.println("has hair"); }
}
class Cow extends Mammal {
    Cow() { name = "Cow"; }
    void makeSound() { System.out.println("Moo"); }
    void giveBirth() { System.out.println("Calf"); }
}
public class Main {
    public static void main(String[] args) {
        Mammal m = new Cow(); Animal a = new Cow();
        m.giveBirth(); a.makeSound(); a.eat();
    }
}""",
    ("oop-assignment-4-part-3", "4.10"): """
abstract class Vehicle {
    String vehicleNumber, brand; double price;
    static int totalVehicles = 0;
    Vehicle(String n, String b, double p) { vehicleNumber = n; brand = b; price = p; totalVehicles++;
        System.out.println("Vehicle constructor"); }
    abstract double calculateTax();
    void displayDetails() { System.out.println(vehicleNumber + " " + brand + " " + price + " " + calculateTax()); }
    static int getTotalVehicles() { return totalVehicles; }
}
class Car extends Vehicle {
    Car(String n, String b, double p) { super(n, b, p); }
    double calculateTax() { return price * 0.1; }
}
class Bike extends Vehicle {
    Bike(String n, String b, double p) { super(n, b, p); }
    double calculateTax() { return price * 0.05; }
}
public class Main {
    public static void main(String[] args) {
        new Car("WB01", "Tata", 800000).displayDetails(); new Bike("WB02", "Hero", 90000).displayDetails();
        System.out.println(Vehicle.getTotalVehicles());
    }
}""",
    ("oop-assignment-4-part-4", "4.11"): """
abstract class Employee {
    int id; String name, department;
    Employee(int i, String n, String d) { id = i; name = n; department = d; }
    void displayEmployeeDetails() { System.out.println(id + " " + name + " " + department + " " + calculateSalary()); }
    abstract double calculateSalary();
}
class PermanentEmployee extends Employee {
    double basic, allowances, deductions;
    PermanentEmployee(int i, String n, String d, double b, double a, double x) { super(i, n, d); basic = b; allowances = a; deductions = x; }
    double calculateSalary() { return basic + allowances - deductions; }
}
class ContractEmployee extends Employee {
    double contractAmount;
    ContractEmployee(int i, String n, String d, double c) { super(i, n, d); contractAmount = c; }
    double calculateSalary() { return contractAmount; }
}
class PartTimeEmployee extends Employee {
    double hours, hourlyRate;
    PartTimeEmployee(int i, String n, String d, double h, double r) { super(i, n, d); hours = h; hourlyRate = r; }
    double calculateSalary() { return hours * hourlyRate; }
}
public class Main {
    public static void main(String[] args) {
        Employee[] e = { new PermanentEmployee(1, "A", "IT", 30000, 5000, 2000), new ContractEmployee(2, "B", "HR", 25000),
                         new PartTimeEmployee(3, "C", "IT", 40, 200) };
        for (Employee x : e) x.displayEmployeeDetails();
    }
}""",
    ("oop-assignment-4-part-4", "4.12"): """
abstract class Student {
    int roll; String name, dept; double marks;
    Student(int r, String n, String d, double m) { roll = r; name = n; dept = d; marks = m; }
    abstract String calculateGrade();
    double calculateCGPA() { return marks / 10; }
    void show() { System.out.println(roll + " " + name + " " + calculateGrade() + " " + calculateCGPA()); }
}
class UGStudent extends Student {
    UGStudent(int r, String n, String d, double m) { super(r, n, d, m); }
    String calculateGrade() { return marks >= 90 ? "A+" : marks >= 80 ? "A" : marks >= 70 ? "B+" : marks >= 60 ? "B" : marks >= 50 ? "C" : marks >= 40 ? "D" : "F"; }
}
class PGStudent extends Student {
    PGStudent(int r, String n, String d, double m) { super(r, n, d, m); }
    String calculateGrade() { return marks >= 85 ? "A" : marks >= 75 ? "A-" : marks >= 65 ? "B+" : marks >= 55 ? "B" : marks >= 50 ? "C" : "F"; }
}
public class Main {
    public static void main(String[] args) {
        Student[] s = { new UGStudent(1, "A", "IT", 91), new UGStudent(2, "B", "IT", 75), new UGStudent(3, "C", "IT", 45),
                        new PGStudent(4, "D", "IT", 80), new PGStudent(5, "E", "IT", 52) };
        for (Student x : s) x.show();
    }
}""",
    ("oop-assignment-4-part-4", "4.13"): """
abstract class Shape { abstract double calculateArea(); abstract double calculateVolume(); }
class Sphere extends Shape {
    double r; Sphere(double r) { this.r = r; }
    double calculateArea() { return 4 * Math.PI * r * r; }
    double calculateVolume() { return 4.0 / 3 * Math.PI * r * r * r; }
}
class Cube extends Shape {
    double a; Cube(double a) { this.a = a; }
    double calculateArea() { return 6 * a * a; }
    double calculateVolume() { return a * a * a; }
}
public class Main {
    public static void main(String[] args) {
        Shape s = new Sphere(2); System.out.println(s.calculateArea() + " " + s.calculateVolume());
        s = new Cube(3); System.out.println(s.calculateArea() + " " + s.calculateVolume());
    }
}""",
    ("oop-overloading-overriding", "1"): """
class Employee {
    String name; double basicSalary;
    Employee(String n, double b) { name = n; basicSalary = b; }
    double calculateSalary(double basicSalary) { return basicSalary; }
    double calculateSalary(double basicSalary, double bonus) { return basicSalary + bonus; }
}
class Manager extends Employee {
    Manager(String n, double b) { super(n, b); }
    double calculateSalary(double basicSalary) { return basicSalary * 1.5; }
}
class Developer extends Employee {
    Developer(String n, double b) { super(n, b); }
    double calculateSalary(double basicSalary) { return basicSalary * 1.2; }
}
public class Main {
    public static void main(String[] args) {
        Employee[] e = { new Employee("A", 20000), new Manager("B", 40000), new Developer("C", 30000) };
        for (Employee x : e) System.out.println(x.name + " " + x.calculateSalary(x.basicSalary));
    }
}""",
    ("oop-overloading-overriding", "2"): """
class Shape {
    double area(double radius) { return 0; }
    double area(double a, double b) { return 0; }
}
class Circle extends Shape { double radius = 2; double area(double r) { return Math.PI * r * r; } }
class Rectangle extends Shape { double area(double l, double b) { return l * b; } }
class Triangle extends Shape { double area(double b, double h) { return 0.5 * b * h; } }
public class Main {
    public static void main(String[] args) {
        Shape s1 = new Circle(), s2 = new Rectangle(), s3 = new Triangle();
        System.out.println(s1.area(2) + " " + s2.area(4, 5) + " " + s3.area(4, 3));
    }
}""",
    ("oop-overloading-overriding", "3"): """
class Vehicle {
    double distance, waitingTime, serviceCharge;
    double calculateFare(double distance) { return distance * 10; }
    double calculateFare(double distance, double waitingTime) { return calculateFare(distance) + waitingTime * 2; }
    double calculateFare(double distance, double waitingTime, double serviceCharge) { return calculateFare(distance, waitingTime) + serviceCharge; }
}
class Car extends Vehicle { double calculateFare(double d) { return d * 15; } }
class Bike extends Vehicle { double calculateFare(double d) { return d * 6; } }
class Auto extends Vehicle { double calculateFare(double d) { return d * 9; } }
public class Main {
    public static void main(String[] args) {
        Vehicle[] v = { new Car(), new Bike(), new Auto() };
        for (Vehicle x : v) System.out.println(x.calculateFare(10, 5, 20));
    }
}""",
    ("oop-bank-system", "1"): """
class BankAccount {
    private String accountNumber, accountHolderName, branchName; private double balance;
    BankAccount() { }
    BankAccount(String n, String h, double b, String br) { accountNumber = n; accountHolderName = h; balance = b; branchName = br; }
    double getBalance() { return balance; }
    protected void setBalance(double b) { balance = b; }
    void deposit(double amount) { if (amount > 0) balance += amount; }
    void deposit(double amount, String source) { deposit(amount); System.out.println("from " + source); }
    void deposit(double amount, String source, String transactionId) { deposit(amount, source); System.out.println(transactionId); }
    void withdraw(double amount) { if (amount <= balance) balance -= amount; }
    void displayAccountDetails() { System.out.println(accountNumber + " " + accountHolderName + " " + balance); }
    double calculateInterest() { return 0; }
}
class SavingsAccount extends BankAccount {
    private double interestRate, minimumBalance;
    SavingsAccount(String n, String h, double b, String br, double rate, double min) { super(n, h, b, br); interestRate = rate; minimumBalance = min; }
    double calculateInterest() { return getBalance() * interestRate / 100; }
    void withdraw(double amount) { if (getBalance() - amount >= minimumBalance) setBalance(getBalance() - amount); else System.out.println("Minimum balance"); }
}
class CurrentAccount extends BankAccount {
    double overdraftLimit; String businessType;
    CurrentAccount(String n, String h, double b, String br, double limit, String type) { super(n, h, b, br); overdraftLimit = limit; businessType = type; }
    void withdraw(double amount) { if (amount <= getBalance() + overdraftLimit) setBalance(getBalance() - amount); else System.out.println("Limit exceeded"); }
}
class PremiumSavingsAccount extends SavingsAccount {
    double rewardPoints, cashbackPercentage;
    PremiumSavingsAccount(String n, String h, double b, String br, double rate, double min, double cash) { super(n, h, b, br, rate, min); cashbackPercentage = cash; }
    void deposit(double amount) { super.deposit(amount); rewardPoints = rewardPoints + amount / 100; }
    double calculateInterest() { return super.calculateInterest() + getBalance() * 0.01; }
}
public class Main {
    static void processTransaction(BankAccount account, double amount, String type) {
        if (type.equals("deposit")) account.deposit(amount); else account.withdraw(amount);
    }
    public static void main(String[] args) {
        BankAccount a = new SavingsAccount("1", "A", 20000, "X", 4, 5000);
        BankAccount b = new CurrentAccount("2", "B", 10000, "X", 5000, "Shop");
        BankAccount c = new PremiumSavingsAccount("3", "C", 50000, "X", 5, 5000, 2);
        processTransaction(a, 5000, "deposit"); processTransaction(b, 15000, "withdraw"); processTransaction(c, 10000, "deposit");
        a.displayAccountDetails(); b.displayAccountDetails(); c.displayAccountDetails();
    }
}""",
}


@pytest.mark.parametrize("pack,label", sorted(GOOD))
def test_correct_answer_passes_every_check(pack, label):
    res = grade(GOOD[(pack, label)], pack, label)
    assert set(res) == set(checks.PACKS[pack][label])
    assert not failed(res), failed(res)


def test_every_pack_question_has_a_reference_answer_or_shares_one():
    """Every question's checks are exercised by some correct answer above."""
    covered = {cid for (pack, label) in GOOD for cid in checks.PACKS[pack][label]}
    for pack, questions in packs.PACKS.items():
        for label, _, _, ids in questions:
            assert set(ids) <= covered | {"java:salary_negative", "out:average_cgpa", "mid:student_ctors",
                                           "mid:bank_private", "mid:bank_negative_dep", "mid:bank_overdraw",
                                           "mid:emp_subclasses", "mid:person_chain", "mid:shape_array",
                                           "mid:faculty", "mid:emp_counter"}, (pack, label)


# ---------------------------------------------------------------- typical mistakes
def test_rectangle_mistakes():
    wrong = GOOD[("oop-assignment-2", "2.3")].replace("Rectangle() { length = 1; breadth = 1; }", "Rectangle() { }")
    assert set(failed(grade(wrong, "oop-assignment-2", "2.3"))) == {"a2:rect_default"}
    wrong = GOOD[("oop-assignment-2", "2.3")].replace("2 * (length + breadth)", "length + breadth")
    assert set(failed(grade(wrong, "oop-assignment-2", "2.3"))) == {"a2:rect_perimeter"}


def test_bank_withdraw_mistake():
    wrong = GOOD[("oop-assignment-2", "2.1")].replace("balance -= amt", "balance += amt")
    assert set(failed(grade(wrong, "oop-assignment-2", "2.1"))) == {"a2:bank_withdraw"}


def test_no_this_chaining_and_no_copy_constructor():
    wrong = GOOD[("oop-assignment-2", "2.4")].replace('this("Unknown");', 'name = "Unknown";').replace(
        'this(name, 10000);', 'this.name = name;')
    assert "src:this_call" in failed(grade(wrong, "oop-assignment-2", "2.4"))
    wrong = GOOD[("oop-assignment-2", "2.5")].replace(
        "MobilePhone(MobilePhone o) { brand = o.brand; model = o.model; price = o.price; }", "").replace(
        "new MobilePhone(a)", "new MobilePhone(a.brand, a.model, a.price)")
    assert set(failed(grade(wrong, "oop-assignment-2", "2.5"))) == {"a2:phone_copy"}


def test_result_wrong_average():
    wrong = GOOD[("oop-assignment-3", "3.1")].replace("t / 4.0", "t / 3.0")
    assert set(failed(grade(wrong, "oop-assignment-3", "3.1"))) == {"a3:result_4int"}


def test_access_specifiers():
    wrong = GOOD[("oop-assignment-4", "4.1")].replace("private double salary", "double salary").replace(
        "if (s >= 0) salary = s; else System.out.println(\"Salary can't be negative\");", "salary = s;")
    assert set(failed(grade(wrong, "oop-assignment-4", "4.1"))) == {"a4:salary_private", "java:salary_negative"}


def test_constructor_order_and_static_hiding():
    wrong = GOOD[("oop-assignment-4", "4.3")].replace('System.out.println("Employee constructor called");', "")
    assert "out:ctor_order" in failed(grade(wrong, "oop-assignment-4", "4.3"))
    wrong = GOOD[("oop-assignment-4", "4.7")].replace(
        'static void companyPolicy() { System.out.println("Manager follows managerial policy."); }', "").replace(
        'static void companyPolicy() { System.out.println("Developer follows technical policy."); }', "")
    assert "a4:policy_hidden" in failed(grade(wrong, "oop-assignment-4", "4.7"))


def test_abstract_and_counter_mistakes():
    wrong = GOOD[("oop-assignment-4-part-3", "4.10")].replace("abstract class Vehicle", "class Vehicle").replace(
        "abstract double calculateTax();", "double calculateTax() { return 0; }").replace(" totalVehicles++;", "")
    assert set(failed(grade(wrong, "oop-assignment-4-part-3", "4.10"))) == {
        "a4:vehicle_abstract", "a4:tax_abs", "a4:vehicle_counter"}


def test_wrong_volume():
    wrong = GOOD[("oop-assignment-4-part-3", "4.8")].replace("radius * radius * height / 3", "radius * radius * height")
    assert set(failed(grade(wrong, "oop-assignment-4-part-3", "4.8"))) == {"a4:cone_volume"}


def test_bank_rules():
    wrong = GOOD[("oop-bank-system", "1")].replace(
        "if (getBalance() - amount >= minimumBalance) setBalance(getBalance() - amount);",
        "if (amount <= getBalance()) setBalance(getBalance() - amount);")
    assert set(failed(grade(wrong, "oop-bank-system", "1"))) == {"a6:savings_min"}
    wrong = GOOD[("oop-bank-system", "1")].replace("rewardPoints = rewardPoints + amount / 100;", "")
    assert set(failed(grade(wrong, "oop-bank-system", "1"))) == {"a6:premium_points"}


def test_install_sets_the_sheet_questions():
    """Installing a sheet pack replaces mis-read questions with the sheet's, keeping a TA's
    hand-made question that has its own tests."""
    from autograder.db import init_engine, session_scope
    from autograder.models import Assignment, Course, Question
    init_engine("sqlite://")
    with session_scope() as db:
        c = Course(ext_id="c", name="OOP")
        a = Assignment(ext_id="a", title="Assignment 4", course=c)
        a.questions.append(Question(label="4", title="Assignment- 4- 2nd Part", position=0))
        mine = Question(label="99", title="extra", position=1)
        mine.tests.append(TestCase(stdin="", expected="x", source="manual", position=0))
        a.questions.append(mine)
        db.add(a)
        db.flush()
        n = checks.install(db, a, "oop-assignment-4-part-2")
        assert [q.label for q in sorted(a.questions, key=lambda q: q.position)][:4] == ["4.4", "4.5", "4.6", "4.7"]
        assert {q.label for q in a.questions} == {"4.4", "4.5", "4.6", "4.7", "99"}
        assert n == sum(len(ids) for _, _, _, ids in packs.PACKS["oop-assignment-4-part-2"])


def test_students_typed_at_the_keyboard():
    """Grading types 3 students in (all 7s, all 9s, all 8s): the one with CGPA 9 must be shown."""
    code = """
import java.util.Scanner;
class Student { String name; int roll; double cgpa; }
public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        int n = sc.nextInt();
        Student[] s = new Student[n];
        for (int i = 0; i < n; i++) {
            s[i] = new Student();
            s[i].name = sc.next(); s[i].roll = sc.nextInt(); s[i].cgpa = sc.nextDouble();
        }
        Student best = s[0];
        for (Student x : s) if (x.cgpa > best.cgpa) best = x;
        System.out.println("Topper: " + best.name + " " + best.roll + " " + best.cgpa);
    }
}"""
    res = grade(code, "oop-assignment-2", "2.2")
    assert res["py:highest_cgpa"][0], res["py:highest_cgpa"]
    assert not grade(code.replace("x.cgpa > best.cgpa", "x.cgpa < best.cgpa"), "oop-assignment-2", "2.2")["py:highest_cgpa"][0]


def test_the_compile_error_a_question_asks_for_is_set_aside():
    """3.3 asks students to show that calculate(10, 20) doesn't compile: that line is commented
    out and the rest graded; any other compile error still fails."""
    code = GOOD[("oop-assignment-3", "3.3")].replace("// t.calculate(10, 20);   ambiguous", "t.calculate(10, 20);")
    res = grade(code, "oop-assignment-3", "3.3")
    assert not failed(res), failed(res)
    broken = code.replace('System.out.println("int, double");', 'System.out.println("int, double")')
    assert set(failed(grade(broken, "oop-assignment-3", "3.3"))) == {"run", "a3:calc_overloads", "src:explicit_cast"}


def test_accessing_the_private_salary_as_asked():
    code = GOOD[("oop-assignment-4", "4.1")].replace(
        'm.displayManager();', 'm.displayManager();\n        // System.out.println(m.salary);\n        System.out.println(e.salary);')
    assert not failed(grade(code, "oop-assignment-4", "4.1"))


def test_a_decimal_value_also_resolves_the_ambiguity():
    code = GOOD[("oop-assignment-3", "3.3")].replace("t.calculate((double) 10, 20);", "t.calculate(10, 20.0);")
    assert not failed(grade(code, "oop-assignment-3", "3.3"))
