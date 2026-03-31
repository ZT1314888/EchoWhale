SCENE_QUESTIONS = {
    "restaurant": "Would you like something to drink with that?",
    "coffee_shop": "Would you like that hot or iced?",
    "office": "Which task would you like to handle first?",
    "travel": "Do you need directions or help buying a ticket?",
}


def build_follow_up(scene: str) -> str:
    return SCENE_QUESTIONS.get(scene, "Can you tell me a little more?")
