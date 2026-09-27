import { z } from "zod";

/**
 * Zod schemas for runtime response validation and contract enforcement.
 */

export const PaperSchema = z.object({
  code: z.string(),
  name: z.string(),
  total_chapters: z.number().int().optional(),
  total_subtopics: z.number().int().optional(),
  completed_subtopics: z.number().int().optional(),
  coverage_pct: z.number().min(0).max(100).optional(),
});

export const SubtopicScoreSchema = z.object({
  node_id: z.string(),
  importance: z.number().min(0).max(1),
  exam_score: z.number(),
  practice_score: z.number(),
  weight_prior: z.number(),
  freq_hits: z.number().int(),
  streak_decay: z.number().optional(),
  trend: z.enum(["rising", "stable", "falling"]).optional(),
});

export const WhyResponseSchema = z.object({
  node_id: z.string(),
  importance: z.number().min(0).max(1),
  exam_score: z.number(),
  practice_score: z.number(),
  weight_prior: z.number(),
  freq_hits: z.number().int(),
  last_tested: z.string().nullable().optional(),
  half_life_decay: z.number().optional(),
  law_stale: z.boolean().optional(),
  summary: z.string(),
});

export const PlanDaySchema = z.object({
  day_index: z.number().int(),
  date: z.string().optional(),
  estimated_minutes: z.number().int(),
  subtopics: z.array(
    z.object({
      node_id: z.string(),
      title: z.string(),
      paper_code: z.string(),
      importance: z.number().min(0).max(1),
      status: z.enum(["not_started", "in_progress", "done"]).default("not_started"),
    })
  ),
});

export const RevisionItemSchema = z.object({
  node_id: z.string(),
  title: z.string(),
  paper_code: z.string(),
  interval_days: z.number().int(),
  repetition_number: z.number().int(),
  due_date: z.string(),
  is_overdue: z.boolean().default(false),
});

export const CuratorQueueItemSchema = z.object({
  unit_id: z.number().int(),
  document_id: z.number().int(),
  paper_code: z.string(),
  attempt_id: z.string().nullable(),
  label_path: z.string(),
  display_label: z.string(),
  marks: z.number().nullable(),
  kind: z.string(),
  question_text: z.string(),
  answer_text: z.string().nullable(),
  bucket: z.enum(["A", "B", "C", "D"]),
  primary_suggestion: z.object({
    node_id: z.string(),
    node_title: z.string().optional(),
    method: z.string(),
    confidence: z.number(),
    anchor_evidence: z.string().nullable().optional(),
  }),
  secondary_suggestions: z.array(
    z.object({
      node_id: z.string(),
      node_title: z.string().optional(),
      method: z.string(),
      confidence: z.number(),
    })
  ).default([]),
});

export type Paper = z.infer<typeof PaperSchema>;
export type SubtopicScore = z.infer<typeof SubtopicScoreSchema>;
export type WhyResponse = z.infer<typeof WhyResponseSchema>;
export type PlanDay = z.infer<typeof PlanDaySchema>;
export type RevisionItem = z.infer<typeof RevisionItemSchema>;
export type CuratorQueueItem = z.infer<typeof CuratorQueueItemSchema>;
