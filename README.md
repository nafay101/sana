# 📝 Notes to Quiz Maker

Upload photos of your notes (or paste text) and get a practice multiple-choice quiz made by
**Google Gemini Flash**. Answer the questions, press **Check my answers**, and see your score with
an explanation for every question. Built with Python + Streamlit.

## Features
- Upload up to 6 photos of notes (PNG, JPG, WEBP) and/or paste text
- Choose 3 to 20 questions and Easy / Medium / Hard difficulty
- 4 options per question, exactly one correct answer
- Instant score and an explanation for each answer
- Try the same quiz again
- Download the quiz with an answer key (`.md`) for printing or sharing

## Files
| File | Purpose |
|---|---|
| `app.py` | The whole app |
| `requirements.txt` | Python packages |
| `README.md` | This guide |

## 1. Get a free Gemini API key
1. Go to https://aistudio.google.com/apikey and sign in with Google.
2. Click **Create API key** and copy it. Never share it or put it inside your code.

## 2. Run it on your computer
Install Python 3.10+ first, then in a terminal inside the project folder:

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. Paste your API key in the sidebar.

Optional: so you don't paste the key every time, create `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "paste-your-key-here"
```

## 3. Push to GitHub
Create a free account at https://github.com, then create a **new empty repository**
(for example `quiz-maker`; do not tick "Add README").

In the project folder (it must contain `app.py`, `requirements.txt` and `README.md` directly,
not inside another folder):

```bash
# keep your key out of GitHub
printf ".streamlit/secrets.toml\n__pycache__/\n.env\n" > .gitignore

git init
git add .
git commit -m "Notes to Quiz Maker"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/quiz-maker.git
git push -u origin main
```

On Windows PowerShell, create the `.gitignore` file with Notepad instead of `printf`, and put
these three lines in it: `.streamlit/secrets.toml`, `__pycache__/`, `.env`.

If Git asks for a password, use a **Personal Access Token** (GitHub > Settings > Developer
settings > Personal access tokens), not your account password.

Easiest alternative with no commands: on GitHub click **Add file > Upload files** and drag in the
three files.

## 4. Deploy on Streamlit Community Cloud (free)
1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click **Create app** > **Deploy a public app from GitHub**.
3. Pick your repository, branch `main`, and main file path `app.py`.
4. Open **Advanced settings > Secrets** and paste:
   ```toml
   GEMINI_API_KEY = "paste-your-key-here"
   ```
5. Click **Deploy**. After a minute or two you get a public link like
   `https://your-app-name.streamlit.app`.

To update the app later, change the code, then run `git add . && git commit -m "update" && git push`.
Streamlit redeploys automatically.

## Changing the AI model
The model name is at the top of `app.py` (`DEFAULT_MODEL = "gemini-2.5-flash"`). You can also add a
`GEMINI_MODEL` secret to override it without editing code. If you see "model not found", Google
may have renamed it: check https://ai.google.dev/gemini-api/docs/models.

## Troubleshooting
| Problem | Fix |
|---|---|
| "API key looks invalid" | Create a new key and paste it again, with no spaces |
| "Too many requests" | The free limit is used up; wait a minute or try later |
| "Model not found" | Update the model name (see above) |
| "No questions could be made" | Use clearer, well-lit photos or paste the text instead |
| App file name | Name it exactly `app.py` (no spaces) |

AI can make mistakes. Check important facts against your textbook.
