document.addEventListener("DOMContentLoaded", () => {
  const sendBtn = document.getElementById("send-btn");
  const launchBtn = document.getElementById("launch-btn");
  const startChatBtn = document.getElementById("start-chat-btn");
  const input = document.getElementById("cmd-input");
  const replyEl = document.getElementById("reply");
  const toggle = document.getElementById("theme-toggle");
  const hero = document.getElementById("hero");

  function showReply(text, isError = false) {
    replyEl.textContent = text;
    replyEl.style.color = isError ? "#ff8a8a" : (document.body.classList.contains("light") ? "#035b9d" : "#8fffe0");
  }

  async function sendCmd() {
    const cmd = input.value.trim();
    if (!cmd) { showReply("Please type a command.", true); return; }

    showReply("Jarvis — thinking...");
    sendBtn.disabled = true;

    try {
      const res = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd })
      });

      const text = await res.text(); 
      let data;
      try { data = JSON.parse(text); } catch (e) { data = null; }

      if (!res.ok) {
        console.error("Server error", res.status, text);
        showReply(`Server error ${res.status}: ${data?.reply || text || res.statusText}`, true);
      } else {
        const reply = data?.reply ?? text ?? "(no reply)";
        showReply(reply, false);
        console.log("Jarvis reply:", reply);
      }
    } catch (err) {
      console.error("Network error", err);
      showReply("Network error: " + (err.message || err), true);
    } finally {
      sendBtn.disabled = false;
    }
  }
  launchBtn.addEventListener("click", async () => {
    showReply("Launching assistant...");
    try {
      const r = await fetch("/api/launch", { method: "POST" });
      const j = await r.json();
      showReply(j.status || "Launch issued");
    } catch (e) {
      console.error(e);
      showReply("Launch failed: " + (e.message || e), true);
    }
  });
  startChatBtn.addEventListener("click", () => {
    document.querySelector(".command-box").scrollIntoView({ behavior: "smooth" });
    input.focus();
  });

  toggle.addEventListener("change", () => {
    document.body.classList.toggle("light");
    hero.classList.toggle("light");
    replyEl.style.color = document.body.classList.contains("light") ? "#035b9d" : "#8fffe0";
  });

  sendBtn.addEventListener("click", sendCmd);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendCmd(); });
});

// === Smooth Scroll & Active Navbar Highlight ===
const navLinks = document.querySelectorAll(".nav-link");

// Smooth scroll
navLinks.forEach(link => {
  link.addEventListener("click", (e) => {
    e.preventDefault();
    const target = document.querySelector(link.getAttribute("href"));
    if (target) {
      window.scrollTo({
        top: target.offsetTop - 80, // offset for navbar
        behavior: "smooth"
      });
    }
  });
});

// Active highlight while scrolling
window.addEventListener("scroll", () => {
  let fromTop = window.scrollY + 100;
  navLinks.forEach(link => {
    const section = document.querySelector(link.getAttribute("href"));
    if (
      section.offsetTop <= fromTop &&
      section.offsetTop + section.offsetHeight > fromTop
    ) {
      link.classList.add("active");
    } else {
      link.classList.remove("active");
    }
  });
});
