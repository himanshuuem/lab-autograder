"""Placing programs whose question number was only a guess (upload order) by what
the question is about: class and file names against the question titles."""
from dataclasses import dataclass, field

from autograder.grading import _map_programs


@dataclass
class Q:
    label: str
    title: str
    statement: str = ""


@dataclass
class P:
    question: str
    code: str
    source_file: str | None = None
    label_guessed: bool = False
    warnings: list = field(default_factory=list)


QUESTIONS = [
    Q("1", "Create a class Car with the following data members", "Brand Model Color Maximum Speed"),
    Q("2", "Design a class Student to store the student's name, roll number", "department and CGPA"),
    Q("3", "Create a class Circle with a data member radius", "Area Circumference"),
    Q("4", "Car Speed Control", "Design a Car class having Brand Model Private Speed. Increase speed, decrease speed"),
    Q("5", "Design an Employee class containing", "id name salary"),
    Q("6", "Design an ATM class with", "pin balance deposit withdraw"),
]


def java(cls, body=""):
    return f"class {cls} {{\n  {body}\n  public static void main(String[] a) {{ }}\n}}\n"


def test_upload_order_guesses_are_placed_by_topic():
    """Arya's files: Employee.java, Car-1.java, Circle.java, ATM.java, Car.java, Student.java."""
    progs = [
        P("1", java("Employee", "int id; double salary;"), "Employee.java", True),
        P("2", java("Car", "private int speed; void increaseSpeed(int d) { speed += d; } void decreaseSpeed() {}"), "Car-1.java", True),
        P("3", java("Circle", "double radius; double area() { return 0; }"), "Circle.java", True),
        P("4", java("ATM", "int pin; double balance;"), "ATM.java", True),
        P("5", java("Car", "String brand, model, color; int maxSpeed;"), "Car.java", True),
        P("6", java("Student", "String name; int roll; double cgpa;"), "Student.java", True),
    ]
    mapped, extra, _ = _map_programs(QUESTIONS, progs)
    assert {q: p.source_file for q, p in mapped.items()} == {
        "1": "Car.java", "2": "Student.java", "3": "Circle.java",
        "4": "Car-1.java", "5": "Employee.java", "6": "ATM.java"}
    assert not extra
    assert all(p.question == q for q, p in mapped.items())


def test_numbers_that_were_not_guessed_are_kept():
    progs = [P("1", java("Employee"), "q1.java"), P("2", java("Car"), "q2.java")]
    mapped, _, _ = _map_programs(QUESTIONS, progs)
    assert mapped["1"].source_file == "q1.java" and mapped["2"].source_file == "q2.java"


def test_guesses_only_take_free_questions():
    progs = [P("1", java("Car", "String brand;"), "q1.java"),                 # stated: question 1
             P("2", java("Car", "String brand;"), "Car.java", True)]          # guessed, also a Car
    mapped, extra, _ = _map_programs(QUESTIONS, progs)
    assert mapped["1"].source_file == "q1.java"
    assert mapped.get("4") is progs[1] or progs[1] in extra or mapped.get("2") is progs[1]
    assert sum(p is progs[1] for p in mapped.values()) <= 1


def test_no_topic_match_keeps_the_guess():
    progs = [P("1", java("Alpha"), "a.java", True), P("2", java("Beta"), "b.java", True)]
    mapped, _, _ = _map_programs(QUESTIONS, progs)
    assert mapped["1"].source_file == "a.java" and mapped["2"].source_file == "b.java"


PART_2 = [Q("4.4", "Shape area overriding"), Q("4.5", "Circle Cylinder Cone"), Q("4.6", "Employee array"),
          Q("4.7", "displayRole companyPolicy")]


def test_sheet_numbers_written_differently():
    """Q5 / 45 / Q1 for a part numbered 4.4-4.7: the part after the dot, the dot lost, the position."""
    progs = [P("4", java("Shape"), "a"), P("45", java("Cylinder"), "b"), P("3", java("Emp"), "c"), P("4.7", java("Role"), "d")]
    mapped, extra, _ = _map_programs(PART_2, progs)
    assert {q: p.source_file for q, p in mapped.items()} == {"4.4": "a", "4.5": "b", "4.6": "c", "4.7": "d"}
    assert not extra
    progs = [P("1", java("Shape"), "a"), P("2", java("Cylinder"), "b")]
    mapped, _, _ = _map_programs(PART_2, progs)
    assert {q: p.source_file for q, p in mapped.items()} == {"4.4": "a", "4.5": "b"}


def test_two_answers_never_share_a_question():
    progs = [P("4.4", java("Shape"), "a"), P("4", java("Shape2"), "b")]
    mapped, extra, _ = _map_programs(PART_2, progs)
    assert mapped["4.4"].source_file == "a" and [p.source_file for p in extra] == ["b"]


def test_a_class_from_another_answer_is_copied_in():
    from autograder.grading import _borrow_classes
    q1 = P("1", "class Car {\n  int speed;\n}\npublic class CarDemo {\n  public static void main(String[] a) { }\n}\n")
    q4 = P("4", "public class Speed {\n  public static void main(String[] a) { Car c = new Car(); }\n}\n")
    q1.language = q4.language = "java"
    _borrow_classes(q4, [q1, q4])
    assert "class Car {" in q4.code and "CarDemo" not in q4.code and q4.warnings
