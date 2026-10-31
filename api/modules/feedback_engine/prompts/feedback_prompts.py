# 契约式系统提示词（审计 Finding 20）：错误分类封闭集合、每处错误一句纠正
# + 一句解释、CEFR 标注与各字段长度约束全部显式写入；输出仅 JSON，
# 与 parse_llm_json 兼容。提示词是软约束，schema 与消费侧截断才是硬顶。
FEEDBACK_PROMPT = """
You are an English writing coach reviewing one learner message from a speaking-practice session. Return strict JSON only (no markdown fences, no extra text) with exactly these keys:

{"errors": [{"category": "...", "original": "...", "correction": "...", "explanation": "..."}], "grammar": "...", "more_natural": "...", "useful_words": ["..."], "cefr_level": "..."}

Field contract:
- errors: at most 3 items, and [] when the message has no errors. category must be one of: grammar, tense, article, preposition, word_choice, collocation, register, spelling, other. original quotes the exact fragment from the learner message; correction is the fixed fragment; explanation is one English sentence of at most 20 words.
- grammar: learner-facing correction text. Write one line per error as "original -> correction (explanation)", at most 3 lines and at most 320 characters in total. When errors is empty, write one short encouraging sentence instead.
- more_natural: the whole message rewritten in a more natural, idiomatic way, at most 2 sentences.
- useful_words: 2 to 4 scene-related short English words or phrases.
- cefr_level: your CEFR estimate of this learner message, one of A1, A2, B1, B2, C1, C2.
""".strip()


from api.modules.feedback_engine.schema import FeedbackInput


def build_feedback_user_prompt(payload: FeedbackInput) -> str:
    """组装反馈引擎的 user prompt（live 链路与评测台共用的单一装配点）。

    学员档案注入块在 scene 块之后追加（与教练 user prompt 同位约定）：
    有则加、无则省，保证无档案时提示词与历史形态逐字节一致。
    从 FeedbackEngineAgent._run_live 内联装配原样提取（P0/G8），
    评测台经本函数复用同一装配路径，消除两处契约漂移。
    """
    user_prompt_lines = [f"Scene: {payload.scene}"]
    if payload.learner_context:
        user_prompt_lines.append(payload.learner_context)
    user_prompt_lines.extend(
        [
            f"Vocab candidates: {', '.join(payload.vocab_candidates) or 'none'}",
            f"Learner message: {payload.learner_message}",
            # 输出契约（含 errors/cefr_level 新键）以系统提示词为准，
            # 这里不再重复键清单，避免两处契约漂移。
            "Return strict JSON following the output contract in the system prompt.",
        ]
    )
    return "\n".join(user_prompt_lines)
