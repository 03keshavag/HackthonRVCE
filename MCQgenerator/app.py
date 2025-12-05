from flask import Flask, render_template, request, redirect, url_for, session
from openai import OpenAI
import re

app = Flask(__name__)
app.secret_key = "samarth_mcq_secret_2025"  # needed for session storage

# ========= 🔥 AI CONFIG =========
API_KEY = ""
MODEL = "moonshotai/kimi-k2-instruct-0905"
client = OpenAI(api_key=API_KEY, base_url="https://api.groq.com/openai/v1")

LANG_MAP = {
    "kn": "Kannada",
    "en": "English",
    "hi": "Hindi",
    "te": "Telugu",
    "ta": "Tamil"
}

# ========= 🧠 AI HELPERS =========

def generate_summary(topic, lang_code):
    """Generate a short explanation of the topic in the chosen language."""
    prompt = f"Explain the topic '{topic}' in {LANG_MAP[lang_code]} in 4–6 short, simple sentences, suitable for a student."
    res = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return res.choices[0].message.content.strip()


def generate_quiz(topic, lang_code):
    """Generate 4 MCQs in strict format."""
    prompt = f"""
Create a 4-question multiple choice quiz on the topic '{topic}' in {LANG_MAP[lang_code]}.

Use EXACTLY this format (no extra text, no translation):

Q1: Your first question text here
A) option1
B) option2
C) option3
D) option4
Answer: A

Q2: Your second question text here
A) option1
B) option2
C) option3
D) option4
Answer: C

Q3: ...
A) ...
B) ...
C) ...
D) ...
Answer: B

Q4: ...
A) ...
B) ...
C) ...
D) ...
Answer: D
"""
    res = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}]
    )
    return res.choices[0].message.content.strip()


def parse_mcq(text):
    """
    Parse AI output in format:
    Q1: ...
    A) ...
    B) ...
    C) ...
    D) ...
    Answer: X
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    questions = []
    current = None

    for line in lines:
        # Question line
        if re.match(r"^Q\d+\s*[:.]", line):
            if current:
                questions.append(current)
            q_text = re.sub(r"^Q\d+\s*[:.]\s*", "", line).strip()
            current = {
                "question": q_text,
                "options": {},
                "answer": None
            }
        # Option line (A) ... / B) ... etc)
        elif re.match(r"^[A-D]\)", line):
            key = line[0]
            value = line[2:].strip()
            if current:
                current["options"][key] = value
        # Answer line
        elif line.lower().startswith("answer"):
            m = re.search(r"([A-D])", line)
            if current and m:
                current["answer"] = m.group(1)

    if current:
        questions.append(current)

    # Only keep complete questions
    cleaned = [q for q in questions if q["answer"] and len(q["options"]) == 4]
    return cleaned

# ========= FLASK ROUTES =========

@app.route("/")
def index():
    return render_template("index.html", languages=LANG_MAP)


@app.route("/generate", methods=["POST"])
def generate():
    topic = request.form.get("topic", "").strip()
    lang = request.form.get("language", "en")

    if not topic:
        return redirect(url_for("index"))

    summary = generate_summary(topic, lang)
    quiz_raw = generate_quiz(topic, lang)
    questions = parse_mcq(quiz_raw)

    # store in session
    session["summary"] = summary
    session["questions"] = questions

    return redirect(url_for("quiz"))


@app.route("/quiz")
def quiz():
    questions = session.get("questions", [])
    summary = session.get("summary", "")
    if not questions:
        return redirect(url_for("index"))
    return render_template("quiz.html", summary=summary, questions=questions)


@app.route("/submit", methods=["POST"])
def submit():
    questions = session.get("questions", [])
    if not questions:
        return redirect(url_for("index"))

    score = 0
    detailed_results = []

    for idx, q in enumerate(questions):
        # name="q0", "q1", ...
        user_choice = request.form.get(f"q{idx}")
        correct_choice = q["answer"]
        is_correct = (user_choice == correct_choice)
        if is_correct:
            score += 1

        detailed_results.append({
            "question": q["question"],
            "options": q["options"],
            "correct": correct_choice,
            "chosen": user_choice,
            "is_correct": is_correct
        })

    return render_template("result.html",
                           score=score,
                           total=len(questions),
                           results=detailed_results)


if __name__ == "__main__":
    app.run(debug=True)
