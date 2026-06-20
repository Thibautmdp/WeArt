// AI Studio — generate images and music
let currentGenType = 'image';
let generatedData = null;

function setType(type) {
  currentGenType = type;
  document.getElementById('gen-type').value = type;

  const btnImg = document.getElementById('btn-image');
  const btnMus = document.getElementById('btn-music');
  const exImg  = document.getElementById('examples-image');
  const exMus  = document.getElementById('examples-music');
  const hint   = document.getElementById('prompt-hint');
  const frame  = document.getElementById('result-frame');
  const placeholder = document.getElementById('result-placeholder');
  const savePanel = document.getElementById('save-panel');

  if (type === 'image') {
    btnImg.className = 'btn btn-primary';
    btnMus.className = 'btn btn-ghost';
    exImg.style.display = 'flex';
    exMus.style.display = 'none';
    hint.textContent = 'Sois précis : style artistique, couleurs, ambiance, sujet.';
  } else {
    btnImg.className = 'btn btn-ghost';
    btnMus.className = 'btn btn-primary';
    exImg.style.display = 'none';
    exMus.style.display = 'flex';
    hint.textContent = 'Décris le genre, l\'ambiance, les instruments, l\'usage (pour étudier, danser…)';
  }

  // Reset result
  if (placeholder) { placeholder.style.display = 'flex'; placeholder.innerHTML = '<div class="icon" style="font-size:2rem;opacity:.3;">✨</div><p>Ton œuvre apparaîtra ici</p>'; }
  if (savePanel) savePanel.style.display = 'none';
  generatedData = null;
}

function setPrompt(text) {
  document.getElementById('prompt-input').value = text;
}

async function generate() {
  const prompt = document.getElementById('prompt-input').value.trim();
  const errEl = document.getElementById('gen-error');
  const frame = document.getElementById('result-frame');
  const placeholder = document.getElementById('result-placeholder');
  const spinner = document.getElementById('result-spinner');
  const spinnerText = document.getElementById('spinner-text');
  const savePanel = document.getElementById('save-panel');
  const genBtn = document.getElementById('generate-btn');

  if (!prompt) {
    errEl.textContent = 'Entre une description avant de générer.';
    errEl.style.display = 'block';
    return;
  }

  errEl.style.display = 'none';
  if (placeholder) placeholder.style.display = 'none';
  if (savePanel) savePanel.style.display = 'none';
  if (spinner) spinner.style.display = 'flex';
  if (genBtn) { genBtn.disabled = true; genBtn.textContent = '⏳ Génération…'; }

  // Progress messages
  const messages = [
    'Génération en cours…',
    'L\'IA est en train de créer…',
    'Encore quelques secondes…',
    'Finalisation…'
  ];
  let msgIdx = 0;
  const msgTimer = setInterval(() => {
    if (spinnerText) spinnerText.textContent = messages[Math.min(++msgIdx, messages.length - 1)];
  }, 8000);

  try {
    const resp = await fetch('/api/ai/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, type: currentGenType })
    });
    const data = await resp.json();

    if (!resp.ok) {
      errEl.textContent = data.error || 'Erreur de génération.';
      errEl.style.display = 'block';
      if (placeholder) { placeholder.style.display = 'flex'; placeholder.innerHTML = '<div style="font-size:2rem;opacity:.3;">✨</div><p>Ton œuvre apparaîtra ici</p>'; }
      return;
    }

    generatedData = data;

    // Show result
    if (spinner) spinner.style.display = 'none';
    if (data.type === 'image' || data.subfolder === 'originals') {
      const img = document.createElement('img');
      img.src = `/media/${data.subfolder}/${data.token}/${data.filename}`;
      img.style.width = '100%';
      img.style.display = 'block';
      img.style.pointerEvents = 'none';
      frame.innerHTML = '';
      frame.appendChild(img);
    } else if (data.type === 'music' || data.subfolder === 'audio') {
      frame.innerHTML = `
        <div style="padding:30px;text-align:center;width:100%;">
          <div style="font-size:3rem;margin-bottom:16px;">🎵</div>
          <audio controls style="width:100%;" src="/media/${data.subfolder}/${data.token}/${data.filename}"></audio>
        </div>`;
    }
    if (savePanel) savePanel.style.display = 'block';

  } catch (e) {
    errEl.textContent = 'Erreur réseau. Vérifie ta connexion et réessaie.';
    errEl.style.display = 'block';
    if (placeholder) { placeholder.style.display = 'flex'; placeholder.innerHTML = '<div style="font-size:2rem;opacity:.3;">✨</div>'; }
  } finally {
    clearInterval(msgTimer);
    if (spinner) spinner.style.display = 'none';
    if (genBtn) { genBtn.disabled = false; genBtn.textContent = '✨ Générer'; }
  }
}

async function saveToPortfolio() {
  if (!generatedData) return;
  const title = document.getElementById('save-title').value.trim() || 'Création IA';
  const prompt = document.getElementById('prompt-input').value.trim();

  const resp = await fetch('/api/ai/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...generatedData, title, prompt })
  });
  if (resp.ok) {
    const d = await resp.json();
    window.location.href = d.redirect;
  }
}
