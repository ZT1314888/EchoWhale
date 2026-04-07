SCENE_PROMPT_VERSION = "scene-v4"

SCENE_INFERENCE_PROMPT = """
Analyze one user image for an English speaking practice app.
Return one JSON object only with keys: scene, role, opener, visual_anchors, vocab_candidates, confidence.

Rules:
- scene: short snake_case setting name.
- role: 1 to 3 words for a natural speaking partner.
- opener: one short English opener, max 14 words.
- visual_anchors: 2 to 4 lower-case clues that define the setting.
- vocab_candidates: 3 to 6 lower-case practice-ready words or short phrases.
- confidence: number between 0 and 1.

Use the image as the source of truth. Filename is only a weak hint.
Prefer scene-defining clues such as menu_board, reception_desk, platform_sign, checkout_counter.
Avoid filler clues like table, chair, furniture, room unless they are the main clue.
Keep office-like scenes visitor-friendly when the space looks like a lobby, lounge, or reception area.
Do not mention AI, the image, or JSON.
Do not add markdown fences or extra commentary.
""".strip()
