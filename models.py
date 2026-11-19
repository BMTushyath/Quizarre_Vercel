from pydantic import BaseModel
from typing import List, Optional


class Question(BaseModel):
    question: str
    options: List[str]
    correct: str


class Quiz(BaseModel):
    title: str
    host_name: str
    questions: List[Question]


class CreateQuizPayload(BaseModel):
    title: str
    host_name: str
    questions: List[dict]
