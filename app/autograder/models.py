from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text,
                        UniqueConstraint, false, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """A teacher who signs in (with Google, or the local admin form)."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(300), unique=True)
    name: Mapped[str] = mapped_column(String(300), default="")
    picture: Mapped[str] = mapped_column(String(1000), default="")
    role: Mapped[str] = mapped_column(String(20), default="teacher")        # teacher | admin
    status: Mapped[str] = mapped_column(String(20), default="pending")      # pending | active | disabled
    # the teacher's Google grant (refresh token), encrypted with SECRET_KEY
    google_token: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    courses: Mapped[list["Course"]] = relationship(secondary="course_teachers", back_populates="teachers")

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# who teaches a course: everyone who loaded it from their own Classroom (co-teachers share it)
course_teachers = Table(
    "course_teachers", Base.metadata,
    Column("course_id", ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    ext_id: Mapped[str] = mapped_column(String(128), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    section: Mapped[str] = mapped_column(String(300), default="")
    link: Mapped[str] = mapped_column(String(500), default="")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="course", cascade="all, delete-orphan")
    teachers: Mapped[list[User]] = relationship(secondary="course_teachers", back_populates="courses")


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("course_id", "ext_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    ext_id: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    max_points: Mapped[float] = mapped_column(Float, default=100)
    due: Mapped[str | None] = mapped_column(String(20), nullable=True)
    materials: Mapped[list] = mapped_column(JSON, default=list)
    link: Mapped[str] = mapped_column(String(500), default="")
    # grading settings
    time_limit_s: Mapped[float] = mapped_column(Float, default=2.0)
    compare_mode: Mapped[str] = mapped_column(String(20), default="tokens")
    similarity_threshold: Mapped[float] = mapped_column(Float, default=0.6)
    starter_code: Mapped[str] = mapped_column(Text, default="")
    tests_imported: Mapped[bool] = mapped_column(Boolean, default=False)
    last_graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    course: Mapped[Course] = relationship(back_populates="assignments")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan", order_by="Question.position")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="assignment", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300), default="")
    statement: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    assignment: Mapped[Assignment] = relationship(back_populates="questions")
    tests: Mapped[list["TestCase"]] = relationship(
        back_populates="question", cascade="all, delete-orphan", order_by="TestCase.position")


class TestCase(Base):
    __tablename__ = "test_cases"
    __test__ = False  # not a pytest class
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"))
    stdin: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[str] = mapped_column(Text, default="")
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(10), default="manual")  # pdf | manual | check
    position: Mapped[int] = mapped_column(Integer, default=0)
    # a requirement check instead of an input/output test (see checks.py), e.g. "java:speed_max"
    rule: Mapped[str] = mapped_column(String(60), default="", server_default=text("''"))
    question: Mapped[Question] = relationship(back_populates="tests")


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    ext_id: Mapped[str] = mapped_column(String(128), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    email: Mapped[str] = mapped_column(String(300), default="")


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"))
    ext_id: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(40), default="")
    late: Mapped[bool] = mapped_column(Boolean, default=False)
    files: Mapped[list] = mapped_column(JSON, default=list)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")
    error: Mapped[str] = mapped_column(Text, default="")
    extraction: Mapped[dict] = mapped_column(JSON, default=dict)
    auto_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    override_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    override_note: Mapped[str] = mapped_column(Text, default="")
    flags: Mapped[list] = mapped_column(JSON, default=list)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_grade: Mapped[float | None] = mapped_column(Float, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Classroom's updateTime when the files were last downloaded in full: the same time next
    # sync means nothing changed, so the saved PDF is graded without downloading again
    source_updated: Mapped[str] = mapped_column(String(40), default="", server_default=text("''"))
    # {question label: code} typed by the teacher over what was read from the PDF (an OCR
    # misreading, a missed answer); used instead of the extracted code every time it is graded
    code_fixes: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"))

    assignment: Mapped[Assignment] = relationship(back_populates="submissions")
    student: Mapped[Student] = relationship()
    programs: Mapped[list["ProgramResult"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan", order_by="ProgramResult.id")

    @property
    def final_score(self) -> float | None:
        return self.override_score if self.override_score is not None else self.auto_score


class ProgramResult(Base):
    __tablename__ = "program_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    question_label: Mapped[str] = mapped_column(String(32))
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    code: Mapped[str] = mapped_column(Text, default="")
    claimed_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    repairs: Mapped[dict] = mapped_column(JSON, default=dict)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    ocr: Mapped[bool] = mapped_column(Boolean, default=False)
    compile_status: Mapped[str] = mapped_column(String(30), default="")
    compile_output: Mapped[str] = mapped_column(Text, default="")
    tests_passed: Mapped[int] = mapped_column(Integer, default=0)
    tests_total: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1
    claimed_status: Mapped[str] = mapped_column(String(30), default="NONE")
    claimed_from_image: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    fixed_by_teacher: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    submission: Mapped[Submission] = relationship(back_populates="programs")
    runs: Mapped[list["Run"]] = relationship(back_populates="program", cascade="all, delete-orphan",
                                             order_by="Run.id")


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("program_results.id", ondelete="CASCADE"))
    test_case_id: Mapped[int | None] = mapped_column(ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True)
    stdin: Mapped[str] = mapped_column(Text, default="")
    expected: Mapped[str] = mapped_column(Text, default="")
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30))
    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runtime_ms: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    rule: Mapped[str] = mapped_column(String(60), default="", server_default=text("''"))
    note: Mapped[str] = mapped_column(Text, default="", server_default=text("''"))   # what a check found
    program: Mapped[ProgramResult] = relationship(back_populates="runs")


class SimilarityPair(Base):
    __tablename__ = "similarity_pairs"
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    question_label: Mapped[str] = mapped_column(String(32))
    sub_a_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    sub_b_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)
    jaccard: Mapped[float] = mapped_column(Float)
    lines_a: Mapped[list] = mapped_column(JSON, default=list)
    lines_b: Mapped[list] = mapped_column(JSON, default=list)
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    verdict: Mapped[str] = mapped_column(String(20), default="")  # "" | cleared | confirmed
    assignment: Mapped[Assignment] = relationship()
    sub_a: Mapped[Submission] = relationship(foreign_keys=[sub_a_id])
    sub_b: Mapped[Submission] = relationship(foreign_keys=[sub_b_id])


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    assignment_id: Mapped[int | None] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), nullable=True)
    submission_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)     # who started it
    status: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
