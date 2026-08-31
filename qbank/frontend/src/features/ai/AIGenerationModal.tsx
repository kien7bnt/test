import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Sparkles,
  Bot,
  CheckCircle2,
  AlertTriangle,
  Layers,
  ArrowRight,
  ShieldCheck,
  Zap,
  HelpCircle,
  Copy,
  Plus,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { apiClient, domainApi, questionApi, getErrorMessage } from '@/services/api';
import { BloomBadge, DifficultyBadge } from '@/components/ui/Badge';

interface AIGenerationModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: (generatedQuestion: any) => void;
}

const BLOOM_LEVELS = [
  { value: 'remember', label: 'Nhận biết (Remember)' },
  { value: 'understand', label: 'Thông hiểu (Understand)' },
  { value: 'apply', label: 'Vận dụng (Apply)' },
  { value: 'analyze', label: 'Vận dụng cao (Analyze)' },
];

const DIFFICULTY_LEVELS = [
  { value: 'easy', label: 'Dễ' },
  { value: 'medium', label: 'Trung bình' },
  { value: 'hard', label: 'Khó' },
];

const QUESTION_TYPES = [
  { value: 'mcq', label: 'Trắc nghiệm (MCQ)' },
  { value: 'essay', label: 'Tự luận (Essay)' },
  { value: 'coding', label: 'Lập trình (Coding)' },
];

export function AIGenerationModal({ open, onClose, onSuccess }: AIGenerationModalProps) {
  const qc = useQueryClient();
  const [prompt, setPrompt] = useState('');
  const [questionType, setQuestionType] = useState('mcq');
  const [bloomLevel, setBloomLevel] = useState('understand');
  const [expectedDifficulty, setExpectedDifficulty] = useState('medium');
  const [selectedDomainId, setSelectedDomainId] = useState('');
  const [selectedTopicId, setSelectedTopicId] = useState('');

  // Result state
  const [result, setResult] = useState<any>(null);

  // Fetch domains
  const { data: domainsData } = useQuery({
    queryKey: ['domains'],
    queryFn: () => domainApi.list(),
    enabled: open,
  });

  const domains = domainsData?.data ?? [];
  const selectedDomain = domains.find((d: any) => d.id === selectedDomainId);
  const topics = selectedDomain?.topics ?? [];

  // Multi-Agent Pipeline Mutation
  const pipelineMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post('/ai/pipeline/multi-agent', {
        prompt: prompt.trim(),
        question_type: questionType,
        bloom_level: bloomLevel,
        expected_difficulty: expectedDifficulty,
        chapter_id: selectedDomainId || undefined,
        topic_id: selectedTopicId || undefined,
        auto_save: false,
      });
      return res.data;
    },
    onSuccess: (data) => {
      setResult(data);
      toast.success('Hệ thống Multi-Agent AI đã sinh và thẩm định câu hỏi thành công!');
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  // Save to Question Bank Mutation
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!result?.question) return;
      const q = result.question;
      return await questionApi.create({
        type: q.type,
        stem: q.stem,
        rationale: q.rationale,
        bloom_level: q.bloom_level,
        expected_difficulty: q.expected_difficulty,
        chapter_id: q.chapter_id,
        topic_id: q.topic_id,
        options: q.options || [],
      });
    },
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['questions'] });
      qc.invalidateQueries({ queryKey: ['domains'] });
      toast.success('Đã lưu câu hỏi vào Ngân hàng câu hỏi!');
      onSuccess?.(res?.data);
      handleReset();
      onClose();
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  const handleReset = () => {
    setPrompt('');
    setResult(null);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  return (
    <Modal
      open={open}
      onOpenChange={handleClose}
      title={
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-purple-100 text-purple-700 rounded-lg">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <div className="font-bold text-gray-900 flex items-center gap-2">
              Multi-Agent AI Question Studio
              <span className="text-[10px] bg-purple-50 text-purple-700 border border-purple-200 px-2 py-0.5 rounded-full font-mono font-semibold uppercase">
                5 Agents Co-Pilot
              </span>
            </div>
            <p className="text-xs text-gray-500 font-normal">
              Phối hợp tự động 5 AI Agents: Generator &rarr; Distractor &rarr; Classifier &rarr; Reviewer &rarr; Duplicate Scanner
            </p>
          </div>
        </div>
      }
      size="xl"
      footer={
        result ? (
          <>
            <Button variant="secondary" onClick={() => setResult(null)}>
              Tạo câu hỏi khác
            </Button>
            <Button
              loading={saveMutation.isPending}
              onClick={() => saveMutation.mutate()}
              className="bg-purple-600 hover:bg-purple-700 text-white"
            >
              <CheckCircle2 className="h-4 w-4 mr-1.5" />
              Lưu vào Ngân hàng câu hỏi
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={handleClose}>
              Hủy
            </Button>
            <Button
              loading={pipelineMutation.isPending}
              onClick={() => {
                if (!prompt.trim()) {
                  toast.error('Vui lòng nhập yêu cầu / chủ đề');
                  return;
                }
                pipelineMutation.mutate();
              }}
              className="bg-purple-600 hover:bg-purple-700 text-white"
            >
              <Zap className="h-4 w-4 mr-1.5" />
              Kích hoạt Multi-Agent AI
            </Button>
          </>
        )
      }
    >
      {!result ? (
        <div className="space-y-4">
          {/* Prompt */}
          <div>
            <label className="block text-sm font-semibold text-gray-800 mb-1">
              Yêu cầu nội dung / Kiến thức cần tạo <span className="text-red-500">*</span>
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ví dụ: Tạo câu hỏi trắc nghiệm về đạo hàm của hàm số lượng giác y = sin(2x), có bẫy về hệ số 2 và dấu của đạo hàm..."
              rows={3}
              className="w-full px-3.5 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            />
          </div>

          {/* Grid Settings */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Loại câu hỏi
              </label>
              <select
                value={questionType}
                onChange={(e) => setQuestionType(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs bg-white focus:ring-2 focus:ring-purple-500 focus:outline-none"
              >
                {QUESTION_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Mức độ Bloom
              </label>
              <select
                value={bloomLevel}
                onChange={(e) => setBloomLevel(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs bg-white focus:ring-2 focus:ring-purple-500 focus:outline-none"
              >
                {BLOOM_LEVELS.map((b) => (
                  <option key={b.value} value={b.value}>
                    {b.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Độ khó dự kiến
              </label>
              <select
                value={expectedDifficulty}
                onChange={(e) => setExpectedDifficulty(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs bg-white focus:ring-2 focus:ring-purple-500 focus:outline-none"
              >
                {DIFFICULTY_LEVELS.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Domain & Topic Selector */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Lĩnh vực kiến thức
              </label>
              <select
                value={selectedDomainId}
                onChange={(e) => {
                  setSelectedDomainId(e.target.value);
                  setSelectedTopicId('');
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs bg-white focus:ring-2 focus:ring-purple-500 focus:outline-none"
              >
                <option value="">— Tự động phân loại —</option>
                {domains.map((d: any) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-700 mb-1">
                Chủ đề con
              </label>
              <select
                value={selectedTopicId}
                onChange={(e) => setSelectedTopicId(e.target.value)}
                disabled={!selectedDomainId}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs bg-white focus:ring-2 focus:ring-purple-500 focus:outline-none disabled:bg-gray-100 disabled:text-gray-400"
              >
                <option value="">— Tự động phân loại —</option>
                {topics.map((t: any) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Multi-Agent Architecture Explanation */}
          <div className="p-3.5 bg-purple-50/60 border border-purple-200 rounded-xl space-y-2">
            <span className="text-xs font-bold text-purple-900 flex items-center gap-1.5">
              <Bot className="h-4 w-4 text-purple-600" />
              Quy trình phối hợp 5 AI Agents tự động:
            </span>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2 text-[11px]">
              <div className="bg-white p-2 rounded-lg border border-purple-100 shadow-2xs">
                <span className="font-bold text-purple-700 block">1. Generator</span>
                <span className="text-gray-500">Tạo stem & đáp án</span>
              </div>
              <div className="bg-white p-2 rounded-lg border border-purple-100 shadow-2xs">
                <span className="font-bold text-purple-700 block">2. Distractor</span>
                <span className="text-gray-500">Tạo 3 bẫy tư duy</span>
              </div>
              <div className="bg-white p-2 rounded-lg border border-purple-100 shadow-2xs">
                <span className="font-bold text-purple-700 block">3. Classifier</span>
                <span className="text-gray-500">Chuẩn hóa Bloom</span>
              </div>
              <div className="bg-white p-2 rounded-lg border border-purple-100 shadow-2xs">
                <span className="font-bold text-purple-700 block">4. Reviewer</span>
                <span className="text-gray-500">Thẩm định chất lượng</span>
              </div>
              <div className="bg-white p-2 rounded-lg border border-purple-100 shadow-2xs">
                <span className="font-bold text-purple-700 block">5. Duplicate</span>
                <span className="text-gray-500">Quét trùng lặp</span>
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* Multi-Agent Results View */
        <div className="space-y-4">
          {/* Agent Execution Traces Bar */}
          <div className="bg-gray-50 border border-gray-200 rounded-xl p-3.5 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-gray-800 flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                Tiến trình thực thi Multi-Agent (5 Agents hoàn tất)
              </span>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                  Chất lượng: {result.quality_score}%
                </span>
                <span className="text-xs font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200">
                  Trùng lặp: {result.duplicate_score}%
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 text-xs">
              {result.traces?.map((trace: any, idx: number) => (
                <div
                  key={idx}
                  className="bg-white p-2.5 rounded-lg border border-gray-200 shadow-2xs space-y-1"
                >
                  <div className="flex items-center justify-between font-semibold text-gray-900 text-[11px]">
                    <span>{trace.role}</span>
                    <span className="text-gray-400 font-mono">{trace.time_ms}ms</span>
                  </div>
                  <p className="text-[11px] text-gray-500 line-clamp-1">{trace.output_summary}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Question Preview Card */}
          <div className="bg-white border border-gray-200 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2 flex-wrap pb-2 border-b border-gray-100">
              <span className="text-xs font-bold text-purple-700 uppercase bg-purple-50 px-2 py-0.5 rounded">
                {result.question?.type?.toUpperCase()}
              </span>
              <BloomBadge level={result.question?.bloom_level} />
              <DifficultyBadge level={result.question?.expected_difficulty} />
              {result.is_publishable && (
                <span className="text-xs bg-emerald-50 text-emerald-700 font-semibold px-2 py-0.5 rounded-full border border-emerald-200 ml-auto flex items-center gap-1">
                  <ShieldCheck className="h-3.5 w-3.5" /> Đạt chuẩn xuất bản
                </span>
              )}
            </div>

            {/* Stem */}
            <div>
              <p className="text-sm font-semibold text-gray-900 whitespace-pre-wrap">
                {result.question?.stem}
              </p>
            </div>

            {/* Options */}
            {result.question?.options && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                {result.question.options.map((opt: any, idx: number) => (
                  <div
                    key={idx}
                    className={`p-2.5 rounded-lg border text-xs transition-colors ${
                      opt.is_correct
                        ? 'bg-green-50/80 border-green-300 text-green-900 font-semibold'
                        : 'bg-gray-50 border-gray-200 text-gray-700'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <span className="font-bold shrink-0">{opt.label || String.fromCharCode(65 + idx)}.</span>
                      <div>
                        <span>{opt.text}</span>
                        {opt.distractor_reason && (
                          <p className="text-[10px] text-gray-400 font-normal mt-0.5">
                            Bẫy tư duy: {opt.distractor_reason}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Rationale */}
            {result.question?.rationale && (
              <div className="p-3 bg-blue-50/60 border border-blue-200 rounded-lg text-xs text-blue-950 space-y-1">
                <span className="font-bold flex items-center gap-1 text-blue-800">
                  <HelpCircle className="h-3.5 w-3.5" /> Lời giải chi tiết:
                </span>
                <p className="text-blue-900 whitespace-pre-wrap">{result.question.rationale}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
