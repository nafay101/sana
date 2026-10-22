"""AI Math Solver - upload a photo of a math question, get a step-by-step solution.

Run locally:  streamlit run app.py
"""
from __future__ import annotations

import base64
import io
import os
import time

import requests
import streamlit as st
from PIL import Image, ImageOps

# NOTE: this app talks to the Gemini web API directly with `requests`,
# so it does NOT need the 'google-genai' package (avoids install/import errors).
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# ---------------- SETTINGS YOU CAN EDIT ----------------
DEFAULT_MODEL = "gemini3.5-flash"   # change here (or set GEMINI_MODEL) if Google renames it
FALLBACK_MODELS = ["gemini-3.8-flash-lite"]   # backup model if the main one is busy / out of free quota
RETRY_WAIT_SECONDS = 8
MAX_IMAGE_SIDE = 2000                # big photos are shrunk to this many pixels (faster, cheaper)
MAX_UPLOAD_MB = 10
# --------------------------------------------------------

SYSTEM_PROMPT = """You are a patient, friendly math tutor.
The student sends a photo of a math question. Do this:
1. Read the question carefully from the image. If part of it is unreadable, say exactly what
   you could not read and state the assumption you made.
2. Solve it correctly. Double-check the final answer before replying.
3. Reply in Markdown with exactly these sections:
   ## Question
   (write the question you read, so the student can confirm it is right)
   ## Solution
   (numbered steps, one idea per step, show the working)
   ## Final Answer
   (short, in bold)
   ## Explanation
   (explain WHY each step works, in simple words, and name the rule or formula used)
4. Write all math in LaTeX: $...$ for inline and $$...$$ for display equations.
5. If the image is not a math question, say so politely and ask for a clearer picture.
"""

LEVELS = {
    "Simple (easy words)": "Explain like I am a beginner. Use very simple words and short sentences.",
    "Normal": "Explain clearly at a normal high-school / university level.",
    "Detailed": "Give a detailed explanation, mention alternative methods and common mistakes.",
}


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
    """Fix phone rotation, shrink very large photos, return (jpeg_bytes, mime_type)."""
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        # flatten transparency onto white so PNG screenshots stay readable
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    elif img.mode == "L":
        img = img.convert("RGB")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    return out.getvalue(), "image/jpeg"


def build_prompt(level: str, extra: str) -> str:
    text = "Solve the math question in this image.\n" + LEVELS.get(level, LEVELS["Normal"])
    if extra.strip():
        text += "\nExtra instruction from the student: " + extra.strip()
    return text


def solve_question(api_key: str, model: str, image_bytes: bytes, mime: str, prompt: str) -> str:
    body = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(image_bytes).decode()}},
            {"text": prompt},
        ]}],
        "generationConfig": {"temperature": 0.2},
    }
    resp = call_gemini(api_key, model, body, 120)
    if resp.status_code != 200:
        try:
            detail = resp.json().get("error", {}).get("message", resp.text)
        except ValueError:
            detail = resp.text
        raise RuntimeError(f"{resp.status_code} {detail}")
    try:
        parts = resp.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError, ValueError):
        text = ""
    if not text:
        raise RuntimeError("The AI returned an empty answer (the image may have been blocked). "
                           "Try a clearer picture.")
    return text


def call_gemini(api_key: str, model: str, body: dict, timeout: int):
    """Send the request. On 'too many requests' wait and retry, then try the backup model."""
    resp = None
    for m in [model] + [x for x in FALLBACK_MODELS if x != model]:
        for attempt in range(2):
            resp = requests.post(API_URL.format(model=m), json=body, timeout=timeout,
                                 headers={"x-goog-api-key": api_key, "Content-Type": "application/json"})
            if resp.status_code in (429, 503) and attempt == 0:
                time.sleep(RETRY_WAIT_SECONDS)
                continue
            break
        if resp.status_code not in (429, 503, 404):
            return resp
    return resp


def friendly_error(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "api key" in low or "api_key" in low or "permission" in low or "401" in low or "403" in low:
        return "Your Gemini API key looks invalid. Check it and try again."
    if "429" in low or "quota" in low or "resource_exhausted" in low:
        return ("Too many requests / free limit reached. Google says: " + msg[:250] + "  -> Wait 1-2 minutes and "
                "try again. If it keeps happening, the DAILY free limit is used up: try tomorrow, or turn on "
                "billing in Google AI Studio.")
    if "404" in low or "not found" in low:
        return f"The model name was not found. Change DEFAULT_MODEL (or GEMINI_MODEL). Details: {msg}"
    return f"Something went wrong: {msg}"


def main() -> None:
    st.set_page_config(page_title="AI Math Solver", page_icon="🧮", layout="centered")
    st.title("🧮 AI Math Solver")
    st.write("Upload a photo of any math question and get a step-by-step solution "
             "with a simple explanation.")

    with st.sidebar:
        st.header("Settings")
        api_key = get_secret("GEMINI_API_KEY")
        if not api_key:
            api_key = st.text_input("Gemini API key", type="password",
                                    help="Get a free key at https://aistudio.google.com/apikey")
        else:
            st.success("API key loaded ✔")
        model = get_secret("GEMINI_MODEL", DEFAULT_MODEL)
        level = st.selectbox("Explanation style", list(LEVELS))
        st.caption(f"Model: {model}")

    uploaded = st.file_uploader("Upload the question (photo or screenshot)",
                                type=["png", "jpg", "jpeg", "webp"])
    use_camera = st.toggle("Or take a photo with the camera")
    camera = st.camera_input("Take a photo") if use_camera else None
    source = uploaded or camera
    extra = st.text_input("Optional note (e.g. 'solve only part b')")

    if source is not None:
        st.image(source, caption="Your question", use_container_width=True)

    if st.button("Solve it", type="primary", disabled=source is None):
        if not api_key:
            st.error("Please enter your Gemini API key in the sidebar.")
            return
        raw = source.getvalue()
        if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
            st.error(f"Image is larger than {MAX_UPLOAD_MB} MB. Please use a smaller one.")
            return
        try:
            image_bytes, mime = prepare_image(raw)
        except Exception:
            st.error("Could not open that image. Please upload a PNG, JPG or WEBP file.")
            return
        try:
            with st.spinner("Solving..."):
                answer = solve_question(api_key, model, image_bytes, mime, build_prompt(level, extra))
            st.session_state["answer"] = answer
        except Exception as exc:
            st.session_state.pop("answer", None)
            st.error(friendly_error(exc))

    if st.session_state.get("answer"):
        st.divider()
        st.markdown(st.session_state["answer"])
        st.download_button("Download solution (.md)", st.session_state["answer"],
                           file_name="solution.md")
        st.caption("AI can make mistakes. Always double-check important answers.")


if __name__ == "__main__":
    main()
