"""Notes to Quiz Maker - upload photos of your notes (or paste text) and practise with an AI quiz.

Run locally:  streamlit run app.py
"""
from __future__ import annotations

import base64
import io
import json
import os
import re

import requests
import streamlit as st
from PIL import Image, ImageOps

# NOTE: talks to the Gemini web API directly with `requests`, so no 'google-genai' package is needed.
# ---------------- SETTINGS YOU CAN EDIT ----------------
DEFAULT_MODEL = "gemini-3.5-flash"   # change here (or set GEMINI_MODEL secret) if Google renames it
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_IMAGE_SIDE = 2000
MAX_IMAGES = 6
MAX_UPLOAD_MB = 10
MAX_TEXT_CHARS = 30000
# --------------------------------------------------------

LETTERS = "ABCD"
DIFFICULTY = {
    "Easy": "Easy: direct recall of facts and definitions.",
    "Medium": "Medium: understanding and applying the ideas.",
    "Hard": "Hard: tricky, application and reasoning questions with close wrong options.",
}

SYSTEM_PROMPT = """You are an expert teacher who writes exam practice questions.
Create multiple-choice questions ONLY from the study material given (images of notes and/or text).
Rules:
- Every question has exactly 4 options and exactly ONE correct option.
- Wrong options must be believable, not silly. Do not use "all of the above" or "none of the above".
- Spread questions across the whole material; do not repeat the same idea.
- Give a short, simple explanation of why the correct answer is right.
- Do not invent facts that are not supported by the material.
- Write in the same language as the material.
- If the material is unreadable or contains nothing to study, return an empty list.
"""

SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "question": {"type": "STRING"},
            "options": {"type": "ARRAY", "items": {"type": "STRING"}},
            "answer_index": {"type": "INTEGER"},
            "explanation": {"type": "STRING"},
        },
        "required": ["question", "options", "answer_index", "explanation"],
    },
}


# ---------------- helpers ----------------
def get_secret(name: str, default: str = "") -> str:
    """Read a setting from Streamlit secrets first, then environment variables."""
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:  # no secrets file present
        pass
    return os.environ.get(name, default)


def prepare_image(data: bytes) -> tuple[bytes, str]:
    """Fix phone rotation, shrink big photos, return (jpeg_bytes, mime_type)."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    elif img.mode == "L":
        img = img.convert("RGB")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue(), "image/jpeg"


def build_prompt(n: int, difficulty: str, text: str) -> str:
    prompt = (f"Write exactly {n} multiple-choice questions from the study material below.\n"
              f"Difficulty - {DIFFICULTY.get(difficulty, DIFFICULTY['Medium'])}\n")
    if text.strip():
        prompt += "\nSTUDY MATERIAL (text):\n" + text.strip()[:MAX_TEXT_CHARS]
    else:
        prompt += "\nThe study material is in the attached image(s)."
    return prompt


def clean_questions(raw) -> list[dict]:
    """Keep only well-formed questions: 4 non-empty options, valid answer index."""
    good = []
    if not isinstance(raw, list):
        return good
    for q in raw:
        try:
            question = str(q["question"]).strip()
            options = [str(o).strip() for o in q["options"]]
            idx = int(q["answer_index"])
            explanation = str(q.get("explanation", "")).strip()
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if question and len(options) == 4 and all(options) and 0 <= idx < 4 \
                and len(set(options)) == 4:
            good.append({"question": question, "options": options,
                         "answer_index": idx, "explanation": explanation})
    return good


def parse_quiz(text: str) -> list[dict]:
    """Parse the AI reply into a clean question list (tolerates ```json fences)."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(text)
    except ValueError:
        m = re.search(r"\[.*\]", text, flags=re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except ValueError:
            return []
    if isinstance(data, dict):  # sometimes wrapped as {"questions": [...]}
        data = data.get("questions", [])
    return clean_questions(data)


def generate_quiz(api_key: str, model: str, images: list[tuple[bytes, str]],
                  text: str, n: int, difficulty: str) -> list[dict]:
    parts = [{"inline_data": {"mime_type": mime, "data": base64.b64encode(b).decode()}}
             for b, mime in images]
    parts.append({"text": build_prompt(n, difficulty, text)})
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json",
                             "responseSchema": SCHEMA},
    }
    resp = requests.post(API_URL.format(model=model), json=body, timeout=180,
                         headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
    if resp.status_code != 200:
        try:
            detail = resp.json().get("error", {}).get("message", resp.text)
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"{resp.status_code} {detail}")
    try:
        reply = "".join(p.get("text", "") for p in resp.json()["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError, ValueError):
        reply = ""
    quiz = parse_quiz(reply)
    if not quiz:
        raise RuntimeError("No questions could be made. Try clearer notes or add more text.")
    return quiz[:n]


def quiz_to_markdown(quiz: list[dict]) -> str:
    lines = ["# Practice Quiz", ""]
    for i, q in enumerate(quiz, 1):
        lines.append(f"**Q{i}. {q['question']}**")
        for j, opt in enumerate(q["options"]):
            lines.append(f"- {LETTERS[j]}. {opt}")
        lines.append("")
    lines += ["---", "## Answer key", ""]
    for i, q in enumerate(quiz, 1):
        a = q["answer_index"]
        lines.append(f"{i}. **{LETTERS[a]}. {q['options'][a]}** - {q['explanation']}")
    return "\n".join(lines)


def friendly_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "api key" in low or "api_key" in low or "permission" in low or "401" in low or "403" in low:
        return "Your Gemini API key looks invalid. Check it and try again."
    if "429" in low or "quota" in low or "resource_exhausted" in low:
        return "Too many requests or the free limit is used up. Wait a minute and try again."
    if "404" in low or "not found" in low:
        return f"The model name was not found. Change DEFAULT_MODEL (or GEMINI_MODEL). Details: {msg}"
    if "timed out" in low or "timeout" in low or "connection" in low:
        return "Could not reach Gemini (network problem or timeout). Please try again."
    return f"Something went wrong: {msg}"


def reset_answers() -> None:
    for key in [k for k in st.session_state if str(k).startswith("quizq_")]:
        del st.session_state[key]
    st.session_state["checked"] = False


# ---------------- page ----------------
def show_quiz(quiz: list[dict]) -> None:
    st.divider()
    st.subheader(f"📝 Your quiz ({len(quiz)} questions)")
    checked = st.session_state.get("checked", False)
    for i, q in enumerate(quiz):
        labels = [f"{LETTERS[j]}. {opt}" for j, opt in enumerate(q["options"])]
        st.markdown(f"**Q{i + 1}. {q['question']}**")
        choice = st.radio("Choose one", labels, index=None, key=f"quizq_{i}",
                          label_visibility="collapsed", disabled=checked)
        if checked:
            right = labels[q["answer_index"]]
            if choice == right:
                st.success(f"✅ Correct! {q['explanation']}")
            elif choice is None:
                st.warning(f"Skipped. Correct answer: **{right}**. {q['explanation']}")
            else:
                st.error(f"❌ Wrong. Correct answer: **{right}**. {q['explanation']}")

    if not checked:
        if st.button("Check my answers", type="primary"):
            st.session_state["checked"] = True
            st.rerun()
    else:
        score = sum(1 for i, q in enumerate(quiz)
                    if st.session_state.get(f"quizq_{i}") == f"{LETTERS[q['answer_index']]}. "
                    f"{q['options'][q['answer_index']]}")
        st.metric("Your score", f"{score} / {len(quiz)}", f"{round(100 * score / len(quiz))}%")
        if st.button("Try again (same questions)"):
            reset_answers()
            st.rerun()
    st.download_button("Download quiz + answer key (.md)", quiz_to_markdown(quiz),
                       file_name="quiz.md")


def main() -> None:
    st.set_page_config(page_title="Notes to Quiz Maker", page_icon="📝", layout="centered")
    st.title("📝 Notes to Quiz Maker")
    st.write("Upload photos of your notes or paste text, and get a practice quiz with answers "
             "and explanations.")

    with st.sidebar:
        st.header("Settings")
        api_key = get_secret("GEMINI_API_KEY")
        if not api_key:
            api_key = st.text_input("Gemini API key", type="password",
                                    help="Get a free key at https://aistudio.google.com/apikey")
        else:
            st.success("API key loaded ✔")
        model = get_secret("GEMINI_MODEL", DEFAULT_MODEL)
        n = st.slider("Number of questions", 3, 20, 10)
        difficulty = st.selectbox("Difficulty", list(DIFFICULTY), index=1)
        st.caption(f"Model: {model}")

    files = st.file_uploader(f"Upload notes (up to {MAX_IMAGES} photos)",
                             type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
    text = st.text_area("...or paste your notes here", height=150)

    if files:
        st.image([f for f in files[:MAX_IMAGES]], width=150)

    if st.button("Make my quiz", type="primary", disabled=not (files or text.strip())):
        if not api_key:
            st.error("Please enter your Gemini API key in the sidebar.")
            return
        if len(files) > MAX_IMAGES:
            st.error(f"Please upload at most {MAX_IMAGES} images.")
            return
        images = []
        for f in files:
            raw = f.getvalue()
            if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
                st.error(f"'{f.name}' is larger than {MAX_UPLOAD_MB} MB.")
                return
            try:
                images.append(prepare_image(raw))
            except Exception:
                st.error(f"Could not open '{f.name}'. Please use PNG, JPG or WEBP.")
                return
        try:
            with st.spinner("Writing your questions..."):
                quiz = generate_quiz(api_key, model, images, text, n, difficulty)
            reset_answers()
            st.session_state["quiz"] = quiz
            if len(quiz) < n:
                st.info(f"Only {len(quiz)} good questions could be made from this material.")
        except Exception as exc:
            st.error(friendly_error(exc))

    if st.session_state.get("quiz"):
        show_quiz(st.session_state["quiz"])
        st.caption("AI can make mistakes. Check important facts against your textbook.")


if __name__ == "__main__":
    main()
