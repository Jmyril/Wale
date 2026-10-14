const logEl = document.getElementById("messages");
const formEl = document.getElementById("composer");
const inputEl = document.getElementById("input");
const stateEl = document.getElementById("state");
const copyEl = document.getElementById("copy");
const snippetEl = document.getElementById("snippet");

const WORD_DELAY = 55;

const LEARN_LABELS = {
  learned: "LEARNED",
  learned_repeat: "STILL LEARNING",
  known: "KNOWN",
  rejected: "INVALID GRAMMAR",
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const scrollDown = () => { logEl.scrollTop = logEl.scrollHeight; };

function setState(text) {
  stateEl.textContent = text;
}

function sessionId() {
  let id = localStorage.getItem("wale_session");
  if (!id) {
    id = Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("wale_session", id);
  }
  return id;
}

function makeLine(who) {
  const line = document.createElement("p");
  line.className = `line line--${who}`;
  logEl.appendChild(line);
  scrollDown();
  return line;
}

// Feed words in as the server streams them, paced so a burst of tokens
// still cascades instead of appearing all at once.
function makeRevealer(line) {
  const queue = [];
  let running = false;

  async function pump() {
    if (running) return;
    running = true;
    while (queue.length) {
      const word = queue.shift();
      const span = document.createElement("span");
      span.className = "w";
      span.textContent = word;
      line.appendChild(span);
      line.appendChild(document.createTextNode(" "));
      scrollDown();
      await sleep(WORD_DELAY);
    }
    running = false;
  }

  const push = (word) => { queue.push(word); pump(); };
  push.done = async () => {
    while (running || queue.length) await sleep(30);
    scrollDown();
  };
  return push;
}

function addThinking() {
  const line = document.createElement("div");
  line.className = "line line--bot";
  line.innerHTML = '<span class="thinking"><i></i><i></i><i></i></span>';
  logEl.appendChild(line);
  scrollDown();
  return line;
}

function dismissIntro() {
  const intro = document.getElementById("intro");
  if (intro) intro.remove();
}

async function send(message) {
  dismissIntro();
  const userLine = makeLine("user");
  userLine.textContent = message;

  const thinking = addThinking();
  setState("THINKING...");
  inputEl.disabled = true;
  let learnLabel = "";
  let botLine = null;
  let push = null;

  try {
    const res = await fetch("/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session: sessionId() }),
    });

    if (!res.body) {
      const data = await res.json();
      thinking.remove();
      push = makeRevealer(makeLine("bot"));
      push(data.reply || "...");
      learnLabel = LEARN_LABELS[(data.learned || {}).status] || "";
    } else {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buffer.indexOf("\n")) >= 0) {
          const raw = buffer.slice(0, idx).trim();
          buffer = buffer.slice(idx + 1);
          if (!raw) continue;
          let obj;
          try { obj = JSON.parse(raw); } catch { continue; }
          if (obj.t !== undefined) {
            if (!botLine) {
              thinking.remove();
              botLine = makeLine("bot");
              push = makeRevealer(botLine);
            }
            push(obj.t);
          } else if (obj.done) {
            learnLabel = LEARN_LABELS[(obj.learned || {}).status] || "";
          }
        }
      }
      if (push) await push.done();
      if (!botLine) {
        thinking.remove();
        push = makeRevealer(makeLine("bot"));
        push("...");
        await push.done();
      }
    }
    if (learnLabel) setState(learnLabel);
  } catch (err) {
    thinking.remove();
    push = makeRevealer(makeLine("bot"));
    push("(device broke, try again)");
    if (push.done) await push.done();
  } finally {
    inputEl.disabled = false;
    if (learnLabel) setTimeout(() => setState("IDLE"), 1700);
    else setState("IDLE");
    inputEl.focus();
  }
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const message = inputEl.value.trim();
  if (!message) return;
  inputEl.value = "";
  send(message);
});

// Copy the install snippet.
copyEl.addEventListener("click", async () => {
  const text = snippetEl.textContent;
  try {
    await navigator.clipboard.writeText(text);
  } catch (e) {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  copyEl.textContent = "✓ COPIED";
  setTimeout(() => { copyEl.textContent = "COPY"; }, 2000);
});

// Opened straight off disk (file://) there is no backend to talk to.
if (location.protocol === "file:") {
  const introText = document.querySelector(".intro__text");
  if (introText) {
    introText.innerHTML =
      "This page is opened directly from disk, so the chat has nothing to talk " +
      "to. Run <b>./run.sh</b> (or <b>python3 server.py</b>), then open " +
      "<b>http://127.0.0.1:8000</b>.";
  }
}

window.addEventListener("load", () => {
  inputEl.focus();
});

// If the URL points at #chat, drop the cursor there.
if (location.hash === "#chat") {
  document.getElementById("chat")?.scrollIntoView();
}
