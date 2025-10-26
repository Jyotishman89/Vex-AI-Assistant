from datetime import datetime
import webbrowser
import requests
from pathlib import Path

CONFIG = {
    "AI_ENDPOINT": "http://localhost:11434/api/generate", 
    "AI_MODEL": "mistral",
}

def open_website(url: str) -> str:
    if not url.startswith("http"):
        url = "https://" + url
    try:
        webbrowser.open(url)
        return f"Opening {url}"
    except Exception as e:
        return f"Failed to open {url}: {e}"

def wiki_summary(query: str) -> str:
    """Small fallback: use Wikipedia REST API for a short summary (if available)."""
    try:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + requests.utils.requote_uri(query)
        r = requests.get(url, timeout=6)
        if r.status_code == 200:
            j = r.json()
            extract = j.get("extract")
            if extract:
                return extract if len(extract) < 800 else extract[:800] + "..."
    except Exception:
        pass
    return None

def ai_fallback(prompt: str) -> str:
    """First try configured AI endpoint, then Wikipedia summary, then generic fallback."""
    try:
        res = requests.post(CONFIG["AI_ENDPOINT"],
                            json={"model": CONFIG["AI_MODEL"], "prompt": prompt, "stream": False},
                            timeout=6)
        if res.status_code == 200:
            j = res.json()
            return j.get("response") or j.get("text") or str(j)
    except Exception as e:
        print("AI endpoint not reachable:", e)

    try:
        q = prompt.lower().replace("who is ", "").replace("what is ", "").replace("define ", "").strip()
        summary = wiki_summary(q)
        if summary:
            return summary
    except Exception:
        pass

    return "Sorry — I couldn't reach the AI service. Try again or check server logs."

def process_command_return(text: str) -> str:
    if not text:
        return "No command provided."
    c = text.lower().strip()

    if "open youtube" in c:
        return open_website("https://youtube.com")
    if "open google" in c:
        return open_website("https://google.com")
    if "open github" in c:
        return open_website("https://github.com")
    if "open linkedin" in c:
        return open_website("https://linkedin.com")
    if "open chatgpt" in c:
        return open_website("https://chatgpt.com")

    if c.startswith("play "):
        song = c.replace("play", "").strip()
        url = "https://www.youtube.com/results?search_query=" + song.replace(" ", "+")
        return open_website(url)

    if "time" in c and "date" not in c:
        return datetime.now().strftime("The time is %I:%M %p")
    if "date" in c:
        return datetime.now().strftime("Today is %A, %B %d, %Y")

    if any(k in c for k in ("who", "what", "when", "where", "define", "how")):
        return ai_fallback(text)

    return ai_fallback(text)
