/* ── FootballGPT — Frontend JS ───────────────────────────────────────────── */

const SESSION_ID   = `session_${Date.now()}`;
const messagesArea = document.getElementById('messages-area');
const chatForm     = document.getElementById('chat-form');
const userInput    = document.getElementById('user-input');
const sendBtn      = document.getElementById('send-btn');
const typingEl     = document.getElementById('typing-indicator');
const statusDot    = document.getElementById('status-dot');
const charCount    = document.getElementById('char-count');
const resetBtn     = document.getElementById('reset-btn');
const hamburger    = document.getElementById('hamburger');
const sidebar      = document.querySelector('.sidebar');

let isLoading = false;

// ── Textarea auto-resize ──────────────────────────────────────────────────────
userInput.addEventListener('input', () => {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 160) + 'px';
  charCount.textContent = `${userInput.value.length} / 2000`;
});

// Submit on Enter (Shift+Enter = newline)
userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!isLoading) chatForm.requestSubmit();
  }
});

// ── Hamburger (mobile) ────────────────────────────────────────────────────────
hamburger.addEventListener('click', () => sidebar.classList.toggle('open'));
document.addEventListener('click', (e) => {
  if (!sidebar.contains(e.target) && !hamburger.contains(e.target)) {
    sidebar.classList.remove('open');
  }
});

// ── Quick topic chips ─────────────────────────────────────────────────────────
document.querySelectorAll('.topic-chip').forEach(btn => {
  btn.addEventListener('click', () => {
    const q = btn.dataset.q;
    if (q && !isLoading) {
      userInput.value = q;
      userInput.dispatchEvent(new Event('input'));
      sidebar.classList.remove('open');
      sendMessage(q);
      userInput.value = '';
      userInput.style.height = 'auto';
      charCount.textContent = '0 / 2000';
    }
  });
});

// ── Reset conversation ────────────────────────────────────────────────────────
resetBtn.addEventListener('click', async () => {
  await fetch('/api/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: SESSION_ID })
  });
  messagesArea.innerHTML = '';
  appendMessage('assistant', '🔄 Conversation reset! Ask me anything about football ⚽');
});

// ── Form submit ───────────────────────────────────────────────────────────────
chatForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = userInput.value.trim();
  if (!text || isLoading) return;

  userInput.value = '';
  userInput.style.height = 'auto';
  charCount.textContent = '0 / 2000';

  sendMessage(text);
});

// ── Core send function ────────────────────────────────────────────────────────
async function sendMessage(text) {
  if (isLoading) return;
  isLoading = true;
  sendBtn.disabled = true;

  appendMessage('user', escapeHtml(text));
  showTyping(true);
  scrollToBottom();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, session_id: SESSION_ID })
    });

    const data = await res.json();
    showTyping(false);

    if (!res.ok || data.error) {
      appendMessage('error', `⚠️ ${data.error || 'Something went wrong.'}`);
      setStatus('offline');
    } else {
      appendMessage('assistant', formatMarkdown(data.reply));
      setStatus('online');
    }
  } catch (err) {
    showTyping(false);
    appendMessage('error', '⚠️ Could not reach the server. Is Flask running?');
    setStatus('offline');
  }

  isLoading = false;
  sendBtn.disabled = false;
  scrollToBottom();
  userInput.focus();
}

// ── DOM helpers ───────────────────────────────────────────────────────────────
function appendMessage(role, html) {
  const row = document.createElement('div');
  row.className = `msg-row ${role === 'user' ? 'user-row' : 'assistant-row'}`;

  const avatar = document.createElement('div');
  if (role === 'user') {
    avatar.className = 'avatar user-avatar';
    avatar.textContent = '🧑';
  } else {
    avatar.className = 'avatar assistant-avatar';
    avatar.textContent = '⚽';
  }

  const bubble = document.createElement('div');
  bubble.className = `bubble ${
    role === 'user'      ? 'user-bubble' :
    role === 'error'     ? 'assistant-bubble error-bubble' :
                           'assistant-bubble'
  }`;
  bubble.innerHTML = html;

  row.appendChild(avatar);
  row.appendChild(bubble);
  messagesArea.appendChild(row);
}

function showTyping(show) {
  typingEl.classList.toggle('visible', show);
  scrollToBottom();
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    messagesArea.scrollTop = messagesArea.scrollHeight;
  });
}

function setStatus(state) {
  statusDot.className = `status-dot ${state}`;
}

// ── Very lightweight markdown → HTML ─────────────────────────────────────────
function formatMarkdown(text) {
  // Escape HTML first (for plain text parts)
  let html = escapeHtml(text);

  // Bold **text**
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Italic *text*
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Inline code `code`
  html = html.replace(/`([^`]+)`/g, '<code style="background:rgba(57,217,138,0.15);padding:1px 5px;border-radius:4px;font-size:13px;">$1</code>');
  // Headers ## / ###
  html = html.replace(/^### (.+)$/gm, '<h4 style="color:var(--green-neon);margin:8px 0 4px;">$1</h4>');
  html = html.replace(/^## (.+)$/gm,  '<h3 style="color:var(--gold);margin:10px 0 5px;">$1</h3>');
  // Bullet lists
  html = html.replace(/^\s*[-*•]\s+(.+)$/gm, '<li style="margin-left:16px;">$1</li>');
  html = html.replace(/(<li.*<\/li>)/s, '<ul style="margin:6px 0;">$1</ul>');
  // Numbered lists
  html = html.replace(/^\d+\.\s+(.+)$/gm, '<li style="margin-left:16px;">$1</li>');
  // Newlines → <br> (but not inside block elements)
  html = html.replace(/\n\n/g, '<br><br>');
  html = html.replace(/\n/g, '<br>');

  return html;
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Ping Ollama on load ───────────────────────────────────────────────────────
(async function pingOllama() {
  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'ping', session_id: 'health_check' })
    });
    setStatus(res.ok ? 'online' : 'offline');
    // Reset health check session
    await fetch('/api/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: 'health_check' })
    });
  } catch {
    setStatus('offline');
  }
})();
