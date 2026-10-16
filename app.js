const API_URL = "http://localhost:8000";
let livePollInterval = null;
let currentSelectedSessionId = null;
let sessionsData = [];

// Transición fluida entre pantallas (1, 2, 3 o 4) con reinicio de animación
function showScreen(screenNum) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const targetScreen = document.getElementById(`screen-${screenNum}`);
  if (targetScreen) {
    targetScreen.classList.add('active');
  }
}

// Botón Logo: Regresa siempre a la Pantalla 1 (Inicio)
function goToHome() {
  stopLivePolling();
  showScreen(1);
}

// --- PANTALLA 1: BOTÓN INICIAR ---
document.getElementById('btn-iniciar').addEventListener('click', async () => {
  try {
    await fetch(`${API_URL}/sesiones/nueva?nombre=Nueva Sesión`, { method: 'POST' });
  } catch (e) {
    console.warn("Servidor backend no disponible, navegando en modo maqueta.");
  }
  showScreen(2);
  startLivePolling();
});

// --- PANTALLA 2: BOTÓN SESIONES ---
document.getElementById('btn-sesiones').addEventListener('click', async () => {
  stopLivePolling();
  await loadAndRenderSessions();
  showScreen(3);
});

// --- PANTALLAS 3 Y 4: BOTÓN DATOS (RETORNO A TIEMPO REAL) ---
document.getElementById('btn-datos').addEventListener('click', () => {
  showScreen(2);
  startLivePolling();
});

document.getElementById('btn-datos-p4').addEventListener('click', () => {
  showScreen(2);
  startLivePolling();
});

// --- POLLING DE DATOS EN TIEMPO REAL (PANTALLA 2) ---
function startLivePolling() {
  stopLivePolling();
  livePollInterval = setInterval(async () => {
    try {
      const res = await fetch(`${API_URL}/live`);
      const data = await res.json();

      if (data.activa) {
        document.getElementById('live-rpm').innerText = data.rpm ? data.rpm.toFixed(0) : "000";
        document.getElementById('live-ppm').innerText = data.ppm ? data.ppm.toFixed(0) : "000";
        document.getElementById('live-dist').innerText = data.distancia ? `${data.distancia.toFixed(2)}m` : "00.00m";

        if (data.presencia && data.angulo !== undefined && data.distancia !== undefined) {
          positionRedDot(data.angulo, data.distancia);
        } else {
          document.getElementById('person-dot').style.display = 'none';
        }
      }
    } catch (err) {
      // Ignora errores si el servidor no está encendido aún
    }
  }, 200);
}

function stopLivePolling() {
  if (livePollInterval) clearInterval(livePollInterval);
}

// Posicionamiento cartesiano del punto rojo en el radar
function positionRedDot(angleDeg, distanceMeters) {
  const dot = document.getElementById('person-dot');
  const PIXELS_PER_METER = 106.5; 

  const angleRad = (90 - (angleDeg - 60)) * (Math.PI / 180);
  const xPx = (distanceMeters * PIXELS_PER_METER) * Math.cos(angleRad);
  const yPx = (distanceMeters * PIXELS_PER_METER) * Math.sin(angleRad);

  const canvasWidth = document.getElementById('radar-canvas').offsetWidth;
  const canvasHeight = document.getElementById('radar-canvas').offsetHeight;

  dot.style.left = `${(canvasWidth / 2) + xPx}px`;
  dot.style.top = `${canvasHeight - 20 - yPx}px`;
  dot.style.display = 'block';
}

// --- CARGA DE HISTORIAL Y SELECCIÓN DE SESIÓN ---
async function loadAndRenderSessions() {
  try {
    const res = await fetch(`${API_URL}/sesiones/historial`);
    sessionsData = await res.json();

    // Filtra las últimas 3 sesiones
    const last3Sessions = sessionsData.slice(0, 3);
    renderSessionList('sessions-list-p3', last3Sessions);
    renderSessionList('sessions-list-p4', last3Sessions);
  } catch (err) {
    console.warn("Cargando vista previa de lista.");
  }
}

function renderSessionList(containerId, sessions) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = '';

  sessions.forEach(s => {
    const dateObj = new Date(s.fecha_inicio);
    const dateStr = dateObj.toLocaleDateString();
    const timeStr = dateObj.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const labelText = s.nombre && s.nombre !== "Nueva Sesión" ? s.nombre : `${dateStr} ${timeStr}`;

    const card = document.createElement('div');
    card.className = `session-card ${s.id === currentSelectedSessionId ? 'selected' : ''}`;
    card.innerHTML = `<span>${labelText}</span> <span>☰</span>`;
    card.onclick = () => selectSession(s.id);

    container.appendChild(card);
  });
}

// PANTALLA 4: Selección de una sesión de la lista
function selectSession(sessionId) {
  currentSelectedSessionId = sessionId;
  const session = sessionsData.find(s => s.id === sessionId);
  if (!session) return;

  const nameInput = document.getElementById('input-session-name');
  if (nameInput) {
    nameInput.value = session.nombre !== "Nueva Sesión" ? session.nombre : "";
  }

  const tbody = document.getElementById('telemetry-rows');
  if (tbody) {
    tbody.innerHTML = '';

    // Filtra los últimos 7 registros de telemetría
    const last7Measurements = (session.mediciones || []).slice(-7);

    last7Measurements.forEach(m => {
      const time = new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      tbody.innerHTML += `
        <tr>
          <td>${time}</td>
          <td>${m.distancia ? m.distancia.toFixed(2) + 'm' : '00.00m'}</td>
          <td>${m.rpm || 0}</td>
          <td>${m.ppm || 0}</td>
        </tr>
      `;
    });
  }

  loadAndRenderSessions();
  showScreen(4);
}

// Renombrado dinámico mediante el campo de texto superior
const inputSessionName = document.getElementById('input-session-name');
if (inputSessionName) {
  inputSessionName.addEventListener('change', async (e) => {
    const newName = e.target.value.trim();
    if (!newName || !currentSelectedSessionId) return;

    try {
      await fetch(`${API_URL}/sesiones/${currentSelectedSessionId}/nombre?nombre=${encodeURIComponent(newName)}`, {
        method: 'PUT'
      });
    } catch (e) {
      console.warn("No se pudo persistir el nombre en el servidor.");
    }

    const session = sessionsData.find(s => s.id === currentSelectedSessionId);
    if (session) {
      session.nombre = newName;
      loadAndRenderSessions();
    }
  });
}