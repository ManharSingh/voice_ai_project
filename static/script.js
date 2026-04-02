const micBtn    = document.getElementById('micBtn');
const waveform  = document.getElementById('waveform');
const thinking  = document.getElementById('thinking');
const micHint   = document.getElementById('micHint');
const chatBox   = document.getElementById('chatBox');
const textInput = document.getElementById('textInput');
const sendBtn   = document.getElementById('sendBtn');
const clearBtn  = document.getElementById('clearBtn');

let recording = false;
let mediaRecorder = null;
let chunks = [];
let currentAudio = null;

function ts() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function addMsg(role, text, audioUrl = null) {
  const label = { user: 'YOU', ai: 'AI', err: '!!' }[role] || role;
  const div = document.createElement('div');
  div.className = `msg ${role}`;

  const safeText = text
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  const audioHtml = audioUrl ? `
    <div class="audio-pill" data-audio="${audioUrl}">
      ▶ play voice response
    </div>` : '';

  div.innerHTML = `
    <div class="avatar">${label}</div>
    <div class="msg-body">
      <div class="msg-text">${safeText}</div>
      ${audioHtml}
      <div class="msg-time">${ts()}</div>
    </div>
  `;

  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;

  const audioPill = div.querySelector('.audio-pill');
  if (audioPill) {
    audioPill.addEventListener('click', () => {
      playAudio(audioPill.dataset.audio);
    });
  }
}

function setLoading(on) {
  thinking.classList.toggle('show', on);
  if (on) waveform.classList.remove('show');
  micBtn.disabled = on;
  sendBtn.disabled = on;
  textInput.disabled = on;
}

function playAudio(url) {
  try {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    }

    currentAudio = new Audio(url);
    currentAudio.play().catch(err => {
      console.log("Autoplay blocked:", err);
    });
  } catch (err) {
    console.error("Audio play error:", err);
  }
}

async function sendAudio(blob) {
  setLoading(true);

  const form = new FormData();
  form.append('audio', blob, 'user_input.wav');

  try {
    const res = await fetch('/process_audio', {
      method: 'POST',
      body: form
    });

    const data = await res.json();

    if (res.ok) {
      if (data.transcript) {
        addMsg('user', `🎤 ${data.transcript}`);
      } else {
        addMsg('user', '🎤 voice message');
      }

      addMsg('ai', data.response, data.audio_url || null);

      if (data.audio_url) {
        playAudio(data.audio_url);
      }
    } else {
      addMsg('err', '⚠ ' + (data.response || 'Server error'));
    }

  } catch (err) {
    console.error(err);
    addMsg('err', '⚠ Cannot reach Flask server. Make sure it is running on localhost:5000.');
  } finally {
    setLoading(false);
    micHint.textContent = 'tap to speak';
  }
}

async function sendTextMessage() {
  const t = textInput.value.trim();
  if (!t) return;

  addMsg('user', t);
  textInput.value = '';
  setLoading(true);

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: t })
    });

    const data = await res.json();

    if (res.ok) {
      addMsg('ai', data.response, data.audio_url || null);
      if (data.audio_url) {
        playAudio(data.audio_url);
      }
    } else {
      addMsg('err', '⚠ ' + (data.response || 'Server error'));
    }

  } catch (err) {
    console.error(err);
    addMsg('err', '⚠ Cannot reach Flask server. Make sure it is running on localhost:5000.');
  } finally {
    setLoading(false);
  }
}

async function toggleMic() {
  if (!recording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      chunks = [];

      mediaRecorder.ondataavailable = e => chunks.push(e.data);

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/wav' });
        sendAudio(blob);
        stream.getTracks().forEach(t => t.stop());
      };

      mediaRecorder.start();
      recording = true;
      micBtn.classList.add('active');
      waveform.classList.add('show');
      micHint.textContent = 'recording… tap to stop';

    } catch (err) {
      console.error(err);
      alert('Microphone permission denied.');
    }

  } else {
    mediaRecorder.stop();
    recording = false;
    micBtn.classList.remove('active');
    waveform.classList.remove('show');
    micHint.textContent = 'processing…';
  }
}

micBtn.addEventListener('click', toggleMic);
sendBtn.addEventListener('click', sendTextMessage);
textInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') sendTextMessage();
});
clearBtn.addEventListener('click', () => {
  chatBox.innerHTML = '';
});

setTimeout(() => {
  addMsg('ai', "Hello! Speak or type something — I'll reply shortly and in voice too.");
}, 500);