"""Edit the participant-facing study content here."""

CONDITIONS = {
    "guided": {
        "name": "Guided Mutual-Fund Factsheet",
        "short": "1 · Guided",
        "prompt": "companion",
        "panel_title": "Example questions",
        "panel_sub": "Select a question or type your own below.",
        "about": "clickable example questions plus a chatbot.",
    },
    "hybrid": {
        "name": "Hybrid FAQ and Mutual-Fund Factsheet Companion",
        "short": "2 · Hybrid FAQ",
        "prompt": "companion",
        "panel_title": "Frequently Asked Questions",
        "panel_sub": "Open an answer, then use the chatbot for follow-up questions.",
        "about": "FAQ dropdowns with AI-written answers, plus a chatbot for follow-ups.",
    },
    "tutor": {
        "name": "Teaching-Focused Mutual-Fund Factsheet Tutor",
        "short": "3 · Tutor",
        "prompt": "tutor_friend",
        "panel_title": "Your learning path",
        "panel_sub": "Your tutor walks you through these. Ask anything, anytime.",
        "about": "a friendly tutor that explains one idea at a time and checks understanding.",
    },
}

# Condition 1 — clickable example questions (sent to the chatbot).
EXAMPLE_QUESTIONS = [
    "What type of mutual fund is this?",
    "What is the fund's investment objective?",
    "What is the minimum SIP amount?",
    "What is the fund's benchmark?",
    "How has the fund performed compared to its benchmark?",
    "What is the exit load?",
    "How is this fund taxed?",
    "What does the Sharpe ratio tell me?",
]

# Condition 2 — FAQ dropdowns. {fund} is replaced with the fund's name.
FAQ_QUESTIONS = [
    "What kind of companies does the {fund} invest in?",
    "What are the key features of the {fund}?",
    "Who should invest in the {fund}?",
    "What is the minimum amount I can invest?",
    "How has the {fund} performed against its benchmark?",
    "What charges apply if I withdraw early?",
    "How risky is the {fund}?",
    "How are gains from this fund taxed?",
]
