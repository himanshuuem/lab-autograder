"""Provider interface shared by the Google and demo implementations."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderError(RuntimeError):
    pass


class Provider(ABC):
    mode = "abstract"

    @abstractmethod
    def list_courses(self) -> list[dict]: ...
    @abstractmethod
    def list_coursework(self, course_id: str) -> list[dict]: ...
    @abstractmethod
    def list_submissions(self, course_id: str, coursework_id: str) -> list[dict]: ...
    @abstractmethod
    def download_file(self, file_id: str) -> dict: ...  # {file_id, title, mime, data: bytes}
    @abstractmethod
    def set_grade(self, course_id: str, coursework_id: str, submission_id: str,
                  grade: float, assign: bool) -> dict: ...
