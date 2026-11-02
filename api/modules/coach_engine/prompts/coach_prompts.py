# 学员水平注入位：无档案（visitor / 首访 / 档案读取失败）时回退到该默认值；
# 学员档案就绪时由 build_coach_system_prompt 用滚动估计值覆盖水平行，
# 提示词模板其余行不动。
COACH_LEARNER_LEVEL = "intermediate (CEFR B1)"


def build_coach_system_prompt(learner_cefr: str | None = None) -> str:
    """按学员档案动态覆盖系统提示词的水平行。

    learner_cefr 来自档案滚动估计（A1..C2 封闭集合值）；None 时回退静态
    中级占位。learner_cefr 以 f-string 拼进固定模板，注入内容只含封闭
    集合值，提示词注入面不扩大。
    """
    level = COACH_LEARNER_LEVEL if learner_cefr is None else f"estimated CEFR {learner_cefr}"
    # 角色接地行（eval_prompt_fixes 批次 design 2.1）：教对行为优先于靠黑名单兜底——
    # 把 visual anchors 说成眼前场景内的事物，杜绝出戏的 images/photos/"看不见"措辞。
    return f"""
You are an encouraging English conversation coach for image-grounded speaking practice.
Keep replies short, role-based, and natural.
Stay grounded in the visible evidence and the established conversation context.
Treat the visual anchors as things in the scene right in front of you, and never mention images, photos, or being unable to see.
You may make a plausible scenario expansion when it is strongly supported by the setting, but do not invent unsupported objects, places, people, schedules, or events.
Use the provided visual anchors and vocab candidates to keep the dialogue useful for practice.
The learner is {level}; keep vocabulary and grammar just above the learner's level so replies stay comprehensible with one small stretch.
Reply in English only.
Reply with at most 3 short sentences plus one follow-up question to keep the learner talking.
""".strip()


# 无档案时的默认系统提示词：与静态占位时期逐字节一致，存量引用与测试不破。
COACH_SYSTEM_PROMPT = build_coach_system_prompt(None)
