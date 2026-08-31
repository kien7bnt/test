from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class GenerateQuestionRequest(BaseModel):
    prompt: Optional[str] = Field(None, description="Prompt yêu cầu tạo câu hỏi")
    subject: Optional[str] = Field(None, description="Môn học")
    topic: Optional[str] = Field(None, description="Chủ đề")
    chapter: Optional[str] = Field(None, description="Chương")
    bloom_level: Optional[str] = Field(None, description="Mức độ Bloom")
    expected_difficulty: Optional[str] = Field(None, description="Độ khó dự kiến")
    question_type: str = Field("mcq", description="Loại câu hỏi")
    learning_objectives: Optional[list[str]] = Field(None, description="Mục tiêu học tập")
    context: Optional[str] = Field(None, description="Bối cảnh/Hạn chế")
    auto_save: bool = Field(False, description="Tự động lưu vào DB")


class ClassifyQuestionRequest(BaseModel):
    stem: str
    options: Optional[list[dict]] = None
    correct_answer: Optional[str] = None
    essay_data: Optional[dict] = None
    coding_data: Optional[dict] = None


class GenerateDistractorsRequest(BaseModel):
    stem: str
    correct_answer: str
    context: Optional[str] = None
    topic: Optional[str] = None
    bloom_level: Optional[str] = None
    num_distractors: int = 3


class ReviewQuestionRequest(BaseModel):
    stem: str
    options: Optional[list[dict]] = None
    correct_answer: Optional[str] = None
    rationale: Optional[str] = None
    essay_data: Optional[dict] = None
    coding_data: Optional[dict] = None
    bloom_level: Optional[str] = None
    question_type: str = "mcq"
