"""
AI endpoints for generating, classifying, and reviewing questions
"""
from __future__ import annotations
import uuid
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user
from app.core.config import settings
from app.ai.orchestrator import AIOrchestrator, AgentStatus
from app.ai.providers import get_provider
from app.ai.agents import (
    QuestionGenerationAgent, GeneratedQuestion,
    QuestionClassificationAgent, QuestionClassification,
    DistractorGenerationAgent,
    QualityReviewAgent, QualityReview
)
from app.models.question import Question
from app.schemas.question import QuestionCreate, QuestionOut
from app.schemas.ai import (
    GenerateQuestionRequest, ClassifyQuestionRequest,
    GenerateDistractorsRequest, ReviewQuestionRequest
)
from app.services import question_service

router = APIRouter(prefix="/ai", tags=["ai"])


# Initialize AI Orchestrator
def get_orchestrator() -> AIOrchestrator:
    """Get or create AI Orchestrator"""
    if not hasattr(get_orchestrator, "_instance"):
        provider_name = getattr(settings, "AI_PROVIDER", "mock")
        
        if provider_name.lower() in ("gemini", "google"):
            provider = get_provider(
                "gemini",
                api_key=getattr(settings, "GEMINI_API_KEY", "") or getattr(settings, "OPENAI_API_KEY", ""),
                model=getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash"),
            )
        elif provider_name.lower() == "openai":
            provider = get_provider(
                "openai",
                api_key=getattr(settings, "OPENAI_API_KEY", ""),
                model=getattr(settings, "OPENAI_MODEL", "gpt-4o"),
            )
        elif provider_name.lower() == "ollama":
            provider = get_provider(
                "ollama",
                base_url=getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434"),
                model=getattr(settings, "OLLAMA_MODEL", "llama3.1"),
            )
        else:  # Default to safe Mock provider
            provider = get_provider("mock")
        
        orchestrator = AIOrchestrator(provider)
        
        # Register agents properly with name parameter where required
        orchestrator.register_agent(
            "generation",
            QuestionGenerationAgent(name="generation", provider=provider, max_retries=3)
        )
        orchestrator.register_agent(
            "classification",
            QuestionClassificationAgent(provider=provider, max_retries=3)
        )
        orchestrator.register_agent(
            "distractor",
            DistractorGenerationAgent(name="distractor", provider=provider, max_retries=3)
        )
        orchestrator.register_agent(
            "quality_review",
            QualityReviewAgent(name="quality_review", provider=provider, max_retries=3)
        )
        
        get_orchestrator._instance = orchestrator
    
    return get_orchestrator._instance


@router.post("/health")
async def health_check():
    """Check AI provider health"""
    orchestrator = get_orchestrator()
    
    try:
        is_healthy = await orchestrator.provider.health_check()
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "provider": orchestrator.provider.__class__.__name__,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


class AIConfigUpdateReq(BaseModel):
    provider: str  # mock | gemini | openai | ollama
    api_key: Optional[str] = None
    model: Optional[str] = None
    ollama_base_url: Optional[str] = None


@router.get("/config")
async def get_ai_config(current_user=Depends(get_current_user)):
    """Lấy cấu hình AI hiện tại"""
    p = getattr(settings, "AI_PROVIDER", "mock")
    masked_key = ""
    if p in ("gemini", "google") and getattr(settings, "GEMINI_API_KEY", ""):
        k = settings.GEMINI_API_KEY
        masked_key = k[:6] + "..." + k[-4:] if len(k) > 10 else "***"
    elif p == "openai" and getattr(settings, "OPENAI_API_KEY", ""):
        k = settings.OPENAI_API_KEY
        masked_key = k[:6] + "..." + k[-4:] if len(k) > 10 else "***"

    current_model = (
        getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
        if p in ("gemini", "google")
        else getattr(settings, "OPENAI_MODEL", "gpt-4o")
        if p == "openai"
        else getattr(settings, "OLLAMA_MODEL", "llama3.1")
    )

    return {
        "provider": p,
        "masked_api_key": masked_key,
        "model": current_model,
        "ollama_base_url": getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434"),
    }


@router.post("/config")
async def update_ai_config(data: AIConfigUpdateReq, current_user=Depends(get_current_user)):
    """Cập nhật cấu hình AI (Provider, API Key, Model) thời gian thực"""
    if not current_user.has_role("admin", "teacher"):
        raise HTTPException(status_code=403, detail="Chỉ giáo viên/admin mới có quyền cấu hình AI")

    settings.AI_PROVIDER = data.provider
    if data.api_key:
        if data.provider in ("gemini", "google"):
            settings.GEMINI_API_KEY = data.api_key
        elif data.provider == "openai":
            settings.OPENAI_API_KEY = data.api_key
    if data.model:
        if data.provider in ("gemini", "google"):
            settings.GEMINI_MODEL = data.model
        elif data.provider == "openai":
            settings.OPENAI_MODEL = data.model
        elif data.provider == "ollama":
            settings.OLLAMA_MODEL = data.model
    if data.ollama_base_url:
        settings.OLLAMA_BASE_URL = data.ollama_base_url

    # Reset orchestrator instance to rebuild with new provider
    if hasattr(get_orchestrator, "_instance"):
        delattr(get_orchestrator, "_instance")

    new_orch = get_orchestrator()
    is_healthy = await new_orch.provider.health_check()

    return {
        "message": "Cấu hình AI đã được cập nhật thành công",
        "provider": data.provider,
        "is_healthy": is_healthy,
    }


@router.post("/questions/generate", response_model=QuestionOut | dict, status_code=status.HTTP_201_CREATED)
async def generate_question(
    data: GenerateQuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Generate a new question using AI.
    
    If auto_save=true, automatically save the generated question to the database.
    """
    if not current_user.has_role("teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ giáo viên có thể tạo câu hỏi"
        )
    
    orchestrator = get_orchestrator()
    
    # Call generation agent
    output = await orchestrator.execute_agent(
        "generation",
        user_id=str(current_user.id),
        prompt=data.prompt,
        subject=data.subject,
        topic=data.topic,
        chapter=data.chapter,
        bloom_level=data.bloom_level,
        expected_difficulty=data.expected_difficulty,
        question_type=data.question_type,
        learning_objectives=data.learning_objectives,
        context=data.context,
    )
    
    if output.status != AgentStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=output.error or "Không thể tạo câu hỏi"
        )
    
    generated = output.data
    
    if data.auto_save:
        # Convert generated data to QuestionCreate schema
        create_data = QuestionCreate(
            type=generated.type,
            stem=generated.stem,
            rationale=generated.rationale,
            bloom_level=generated.bloom_level,
            expected_difficulty=generated.expected_difficulty,
            options=generated.options,
            essay_data=generated.essay_data if hasattr(generated, 'essay_data') else None,
            coding_data=generated.coding_data if hasattr(generated, 'coding_data') else None,
        )
        
        # Save to database
        question = await question_service.create_question(db, create_data, current_user.id)
        
        # Convert to output format
        return _question_to_out(question)
    
    # Return just the generated data without saving
    return {
        "id": None,
        "item_id": "DRAFT",
        "type": generated.type,
        "status": "draft",
        "stem": generated.stem,
        "rationale": generated.rationale,
        "bloom_level": generated.bloom_level,
        "expected_difficulty": generated.expected_difficulty,
        "options": generated.options or [],
    }


@router.post("/questions/classify")
async def classify_question(
    data: ClassifyQuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> QuestionClassification:
    """Classify a question into curriculum structure"""
    
    if not current_user.has_role("teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ giáo viên có thể phân loại câu hỏi"
        )
    
    orchestrator = get_orchestrator()
    
    output = await orchestrator.execute_agent(
        "classification",
        user_id=str(current_user.id),
        stem=data.stem,
        options=data.options,
        correct_answer=data.correct_answer,
        essay_data=data.essay_data,
        coding_data=data.coding_data,
    )
    
    if output.status != AgentStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=output.error or "Không thể phân loại câu hỏi"
        )
    
    return output.data


@router.post("/questions/distractors")
async def generate_distractors(
    data: GenerateDistractorsRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate distractors for a question"""
    
    if not current_user.has_role("teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ giáo viên có thể tạo phương án sai"
        )
    
    orchestrator = get_orchestrator()
    
    output = await orchestrator.execute_agent(
        "distractor",
        user_id=str(current_user.id),
        stem=data.stem,
        correct_answer=data.correct_answer,
        context=data.context,
        topic=data.topic,
        bloom_level=data.bloom_level,
        num_distractors=data.num_distractors,
    )
    
    if output.status != AgentStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=output.error or "Không thể tạo phương án sai"
        )
    
    return output.data


@router.post("/questions/review")
async def review_question(
    data: ReviewQuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> QualityReview:
    """Review question quality"""
    
    if not current_user.has_role("teacher", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ giáo viên có thể đánh giá câu hỏi"
        )
    
    orchestrator = get_orchestrator()
    
    output = await orchestrator.execute_agent(
        "quality_review",
        user_id=str(current_user.id),
        stem=data.stem,
        options=data.options,
        correct_answer=data.correct_answer,
        rationale=data.rationale,
        essay_data=data.essay_data,
        coding_data=data.coding_data,
        bloom_level=data.bloom_level,
        question_type=data.question_type,
    )
    
    if output.status != AgentStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=output.error or "Không thể đánh giá câu hỏi"
        )
    
    return output.data


@router.post("/questions/{question_id}/review")
async def review_existing_question(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> QualityReview:
    """Review an existing question"""
    
    question = await question_service.get_question(db, question_id)
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy câu hỏi"
        )
    
    # Extract question data
    options = [
        {
            "label": opt.label,
            "text": opt.text,
            "is_correct": opt.is_correct,
        }
        for opt in question.options
    ]
    
    correct_ans = None
    if question.essay_data and question.essay_data.sample_answer:
        correct_ans = question.essay_data.sample_answer
        
    req_data = ReviewQuestionRequest(
        stem=question.stem,
        options=options if options else None,
        correct_answer=correct_ans,
        rationale=question.rationale,
        bloom_level=question.bloom_level,
        question_type=question.type,
    )
    
    # Call review endpoint
    return await review_question(
        data=req_data,
        db=db,
        current_user=current_user,
    )


@router.post("/questions/detect-duplicates")
async def detect_question_duplicates(
    stem: str,
    target_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Phát hiện câu hỏi trùng lặp hoặc tương tự trong ngân hàng câu hỏi"""
    from app.ai.agents.duplicate import DuplicateDetectionAgent
    from app.models.question import Question
    from sqlalchemy import select

    # Fetch all existing questions in bank
    q_stmt = select(Question).where(Question.status != "archived")
    res = await db.execute(q_stmt)
    questions = res.scalars().all()

    candidates = [{"id": str(q.id), "stem": q.stem} for q in questions]

    provider = get_provider(settings.AI_PROVIDER)
    agent = DuplicateDetectionAgent(provider=provider)

    output = await agent.execute(
        target_stem=stem,
        candidate_questions=candidates,
        target_id=target_id,
        threshold=0.65,
    )

    if output.status != AgentStatus.SUCCESS or not output.data:
        raise HTTPException(status_code=500, detail=output.error or "Lỗi quét trùng lặp")

    return output.data


# ─── Multi-Agent Pipeline Auto-Pilot ──────────────────────────────────────────

class MultiAgentGenerateReq(BaseModel):
    prompt: str
    topic_id: Optional[uuid.UUID] = None
    chapter_id: Optional[uuid.UUID] = None
    question_type: str = "mcq"
    bloom_level: str = "understand"
    expected_difficulty: str = "medium"
    context: Optional[str] = None
    auto_save: bool = False


@router.post("/pipeline/multi-agent")
async def run_multi_agent_pipeline(
    data: MultiAgentGenerateReq,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Kích hoạt hệ thống Multi-Agent AI phối hợp 5 Agents:
    1. QuestionGenerationAgent: Sinh stem và đáp án
    2. DistractorGenerationAgent: Tối ưu 3 phương án bẫy & giải thích
    3. QuestionClassificationAgent: Chuẩn hóa Bloom & độ khó
    4. QualityReviewAgent: Thẩm định chất lượng & cấp điểm
    5. DuplicateDetectionAgent: Quét đối chiếu với ngân hàng câu hỏi
    """
    if not current_user.has_role("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Chỉ giáo viên mới có thể sử dụng Multi-Agent AI")

    orchestrator = get_orchestrator()
    traces = []

    # ─── 1. Question Generation Agent ────────────────────────────────────────
    gen_out = await orchestrator.execute_agent(
        "generation",
        user_id=str(current_user.id),
        prompt=data.prompt,
        bloom_level=data.bloom_level,
        expected_difficulty=data.expected_difficulty,
        question_type=data.question_type,
        context=data.context,
    )
    if gen_out.status != AgentStatus.SUCCESS or not gen_out.data:
        raise HTTPException(status_code=400, detail=gen_out.error or "Agent Tạo câu hỏi thất bại")

    gen_data = gen_out.data
    traces.append({
        "agent": "QuestionGenerationAgent",
        "role": "Sinh nội dung câu hỏi & đáp án chuẩn",
        "status": "success",
        "time_ms": round(gen_out.execution_time_ms, 1),
        "output_summary": f"Đã sinh câu hỏi loại {gen_data.type} với {len(gen_data.options or [])} lựa chọn",
    })

    # ─── 2. Distractor Generation Agent (for MCQ) ───────────────────────────
    options = gen_data.options or []
    if gen_data.type == "mcq" and len(options) >= 2:
        dist_out = await orchestrator.execute_agent(
            "distractor",
            user_id=str(current_user.id),
            stem=gen_data.stem,
            correct_answer=next((o.get("text") for o in options if o.get("is_correct")), "A"),
            bloom_level=data.bloom_level,
            num_distractors=3,
        )
        if dist_out.status == AgentStatus.SUCCESS and dist_out.data:
            traces.append({
                "agent": "DistractorGenerationAgent",
                "role": "Tối ưu phương án gây nhiễu & bẫy tư duy",
                "status": "success",
                "time_ms": round(dist_out.execution_time_ms, 1),
                "output_summary": "Đã tạo lý do phương án sai chi tiết cho từng đáp án",
            })
        else:
            traces.append({
                "agent": "DistractorGenerationAgent",
                "role": "Tối ưu phương án gây nhiễu",
                "status": "skipped",
                "time_ms": 0,
                "output_summary": "Sử dụng các phương án mặc định từ Generator",
            })

    # ─── 3. Classification Agent ─────────────────────────────────────────────
    class_out = await orchestrator.execute_agent(
        "classification",
        user_id=str(current_user.id),
        stem=gen_data.stem,
        options=options,
        correct_answer=next((o.get("text") for o in options if o.get("is_correct")), None),
    )
    final_bloom = data.bloom_level
    final_diff = data.expected_difficulty
    if class_out.status == AgentStatus.SUCCESS and class_out.data:
        final_bloom = class_out.data.bloom_level or final_bloom
        final_diff = class_out.data.expected_difficulty or final_diff
        traces.append({
            "agent": "QuestionClassificationAgent",
            "role": "Chuẩn hóa Bloom Taxonomy & Độ khó",
            "status": "success",
            "time_ms": round(class_out.execution_time_ms, 1),
            "output_summary": f"Xác nhận Bloom: {final_bloom.upper()}, Độ khó: {final_diff.upper()}",
        })

    # ─── 4. Quality Review Agent ─────────────────────────────────────────────
    review_out = await orchestrator.execute_agent(
        "quality_review",
        user_id=str(current_user.id),
        stem=gen_data.stem,
        options=options,
        correct_answer=next((o.get("text") for o in options if o.get("is_correct")), None),
        rationale=gen_data.rationale,
        bloom_level=final_bloom,
        question_type=gen_data.type,
    )
    quality_score = 0.95
    is_publishable = True
    issues = []
    if review_out.status == AgentStatus.SUCCESS and review_out.data:
        quality_score = review_out.data.overall_score
        is_publishable = review_out.data.is_publishable
        issues = [i.model_dump() for i in review_out.data.issues]
        traces.append({
            "agent": "QualityReviewAgent",
            "role": "Thẩm định chất lượng & Đánh giá sư phạm",
            "status": "success",
            "time_ms": round(review_out.execution_time_ms, 1),
            "output_summary": f"Điểm chất lượng: {round(quality_score * 100)}/100 (Đạt chuẩn xuất bản: {is_publishable})",
        })

    # ─── 5. Duplicate Scanner Agent ──────────────────────────────────────────
    from app.ai.agents.duplicate import DuplicateDetectionAgent
    from sqlalchemy import select
    all_q_stmt = select(Question).where(Question.status != "archived").limit(20)
    all_q_res = await db.execute(all_q_stmt)
    all_q_list = all_q_res.scalars().all()
    candidates = [{"id": str(q.id), "stem": q.stem} for q in all_q_list]

    dup_agent = DuplicateDetectionAgent(provider=orchestrator.provider)
    dup_out = await dup_agent.execute(
        target_stem=gen_data.stem,
        candidate_questions=candidates,
        threshold=0.65,
    )
    dup_score = 0.05
    if dup_out.status == AgentStatus.SUCCESS and dup_out.data:
        dup_score = max([m.similarity_score for m in dup_out.data.matches] or [0.05])
        traces.append({
            "agent": "DuplicateDetectionAgent",
            "role": "Quét đối chiếu trùng lặp với kho dữ liệu",
            "status": "success",
            "time_ms": round(dup_out.execution_time_ms, 1),
            "output_summary": f"Độ tương đồng tối đa: {round(dup_score * 100, 1)}% (Kho {len(candidates)} câu)",
        })

    # Build final question structure
    question_payload = {
        "type": gen_data.type,
        "stem": gen_data.stem,
        "rationale": gen_data.rationale,
        "bloom_level": final_bloom,
        "expected_difficulty": final_diff,
        "chapter_id": str(data.chapter_id) if data.chapter_id else None,
        "topic_id": str(data.topic_id) if data.topic_id else None,
        "options": options,
    }

    saved_id = None
    if data.auto_save:
        from app.schemas.question import QuestionCreate
        create_data = QuestionCreate(
            type=gen_data.type,
            stem=gen_data.stem,
            rationale=gen_data.rationale,
            bloom_level=final_bloom,
            expected_difficulty=final_diff,
            chapter_id=data.chapter_id,
            topic_id=data.topic_id,
            options=options,
        )
        saved_q = await question_service.create_question(db, create_data, current_user.id)
        saved_id = str(saved_q.id)

    return {
        "question": question_payload,
        "pipeline_status": "completed",
        "traces": traces,
        "quality_score": round(quality_score * 100, 1),
        "is_publishable": is_publishable,
        "quality_issues": issues,
        "duplicate_score": round(dup_score * 100, 1),
        "saved_question_id": saved_id,
    }


def _question_to_out(q) -> QuestionOut:
    """Convert question model to output schema"""
    from app.schemas.question import (
        EssayDataOut, CodingDataOut, QuestionOptionOut
    )
    return QuestionOut(
        id=q.id,
        item_id=q.item_id,
        type=q.type,
        status=q.status,
        stem=q.stem,
        rationale=q.rationale,
        subject_id=q.subject_id,
        subject_name=q.subject.name if q.subject else None,
        chapter_id=q.chapter_id,
        chapter_name=q.chapter.name if q.chapter else None,
        topic_id=q.topic_id,
        topic_name=q.topic.name if q.topic else None,
        bloom_level=q.bloom_level,
        expected_difficulty=q.expected_difficulty,
        options=[
            QuestionOptionOut(
                id=o.id,
                question_id=o.question_id,
                label=o.label,
                text=o.text,
                is_correct=o.is_correct,
                distractor_reason=o.distractor_reason,
                order_index=o.order_index,
            )
            for o in q.options
        ],
        essay_data=EssayDataOut.model_validate(q.essay_data) if q.essay_data else None,
        coding_data=CodingDataOut.model_validate(q.coding_data) if q.coding_data else None,
        version=q.version,
        created_by=q.created_by,
        created_at=q.created_at,
        updated_at=q.updated_at,
    )
