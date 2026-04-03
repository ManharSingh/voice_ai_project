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
  return new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.innerText = text;
  return div.innerHTML;
}

function stopCurrentAudio() {
  if (currentAudio) {
    currentAudio.pause();
    currentAudio.currentTime = 0;
  }
}

function playAudio(audioUrl) {
  stopCurrentAudio();
  currentAudio = new Audio(audioUrl);
  currentAudio.play().catch(err => {
    console.log("Audio play blocked:", err);
  });
}

function addMsg(role, text, audioUrl = null) {
  const label = {user:'YOU', ai:'AI', err:'!!'}[role] || role;
  const div = document.createElement('div');
  div.className = `msg ${role}`;

  const safeText = escapeHtml(text);

  const audioHtml = audioUrl ? `
    <div class="audio-pill" data-audio="${audioUrl}">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
        <polygon points="5 3 19 12 5 21 5 3"/>
      </svg>
      play voice response
    </div>` : '';

  div.innerHTML = `
    <div class="avatar">${label}</div>
    <div class="msg-body">
      <div class="msg-text">${safeText}</div>
      ${audioHtml}
      <div class="msg-time">${ts()}</div>
    </div>`;

  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;

  const audioPill = div.querySelector(".audio-pill");
  if (audioPill) {
    audioPill.addEventListener("click", () => {
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
      if (data.user_text) {
        addMsg('user', `🎤 ${data.user_text}`);
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
    addMsg('err', '⚠ Cannot reach Flask server.');
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

      mediaRecorder.ondataavailable = e => {
        if (e.data.size > 0) chunks.push(e.data);
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/wav' });
        sendAudio(blob);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      recording = true;
      micBtn.classList.add('active');
      waveform.classList.add('show');
      micHint.textContent = 'recording… tap to stop';

    } catch (err) {
      console.error(err);
      alert('Microphone permission denied or unavailable.');
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
  stopCurrentAudio();
});

setTimeout(() => {
  addMsg('ai', "Hello! Tap the mic or type a message. I'll reply in voice too.");
}, 600);