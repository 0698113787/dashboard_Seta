/* ── Real-time updates via Socket.IO + REST polling ─────────────────────── */

const socket = io();

/* Connection status */
const dot   = document.getElementById('connDot');
const label = document.getElementById('connLabel');

socket.on('connect', () => {
  dot.classList.add('live');
  label.textContent = 'Live';
});
socket.on('disconnect', () => {
  dot.classList.remove('live');
  label.textContent = 'Offline';
});

/* ── Live sensor update ───────────────────────────────────────────────────── */
socket.on('sensor_update', data => {
  const ts = new Date(data.timestamp);
  const timeLabel = ts.toLocaleTimeString('en-ZA', { hour:'2-digit', minute:'2-digit', second:'2-digit' });

  // KPI cards
  setText('kpiWater',     data.water_level.toFixed(1));
  setText('kpiRain',      data.rainfall_now.toFixed(1));
  setText('kpiPredicted', data.predicted_level.toFixed(1));
  setText('kpiValve',     data.valve_status);

  // Risk badge
  const badge = document.getElementById('globalRisk');
  badge.textContent = data.risk_level;
  badge.className   = 'risk-badge ' + data.risk_level.toLowerCase();

  // Charts
  pushWaterPoint(timeLabel, data.water_level, data.predicted_level);
  updateGauge(data.water_level);
  updatePredChart(
    +(data.predicted_level - 3).toFixed(1),
    data.predicted_level,
    +(data.predicted_level + 3).toFixed(1)
  );
});

/* ── Clock ───────────────────────────────────────────────────────────────── */
function tickClock() {
  const el = document.getElementById('liveClock');
  if (el) el.textContent = new Date().toLocaleString('en-ZA', {
    dateStyle: 'medium', timeStyle: 'medium'
  });
}
tickClock();
setInterval(tickClock, 1000);

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

/* ── Load Alerts ─────────────────────────────────────────────────────────── */
window.loadAlerts = async function() {
  try {
    const res    = await fetch('/api/alerts?limit=20');
    const alerts = await res.json();
    const tbody  = document.getElementById('alertsBody');
    if (!alerts.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="loading-row">No alerts found.</td></tr>';
      return;
    }
    tbody.innerHTML = alerts.map(a => {
      const t   = new Date(a.timestamp).toLocaleString('en-ZA');
      const cls = 'sev-' + a.severity.toLowerCase();
      const ack = a.acknowledged
        ? '<span style="color:var(--text-dim);font-size:.65rem">✓ Acked</span>'
        : `<button class="btn-ack" onclick="ackAlert(${a.id},this)">Ack</button>`;
      return `<tr>
        <td>${t}</td>
        <td>${a.alert_type}</td>
        <td class="${cls}">${a.severity}</td>
        <td>${a.message}</td>
        <td>${a.water_level ? a.water_level.toFixed(1)+' cm' : '—'}</td>
        <td>${ack}</td>
      </tr>`;
    }).join('');
  } catch(e) { console.error('Alerts error:', e); }
};

window.ackAlert = async function(id, btn) {
  btn.disabled = true;
  try {
    await fetch(`/api/alerts/${id}/acknowledge`, { method:'POST' });
    btn.textContent = '✓ Acked';
    btn.style.color = 'var(--safe)';
  } catch(e) { btn.disabled = false; }
};

loadAlerts();
setInterval(loadAlerts, 10000);

/* ── Load Dataset Info ───────────────────────────────────────────────────── */
async function loadDatasetInfo() {
  try {
    const res  = await fetch('/api/dataset/info');
    const data = await res.json();
    setText('dsSource',   data.source || '—');
    setText('dsRecords',  (data.total_records || 0).toLocaleString());
    setText('dsEarliest', data.earliest_date || '—');
    setText('dsLatest',   data.latest_date   || '—');
    setText('dsFull',     data.full_size_mb  + ' MB');
    setText('dsRecent',   data.recent_size_mb + ' MB');

    // KPI dataset count
    setText('kpiRecords', (data.total_records || 0).toLocaleString());
  } catch(e) { console.error('Dataset info error:', e); }
}
loadDatasetInfo();

/* ── Load ML Metrics ─────────────────────────────────────────────────────── */
async function loadModelMetrics() {
  try {
    const res  = await fetch('/api/model/metrics');
    const data = await res.json();
    if (data.r2_score != null) {
      setText('kpiR2', (data.r2_score * 100).toFixed(1) + '%');
    }
  } catch(e) {}
}
loadModelMetrics();

/* ── Load System Status ──────────────────────────────────────────────────── */
async function loadSystemStatus() {
  try {
    const res  = await fetch('/api/system/status');
    const data = await res.json();

    setSysCard('sysESP32', data.esp32_online,     data.esp32_online ? 'ONLINE' : 'OFFLINE');
    setSysCard('sysCAM',   data.esp32_cam_online, data.esp32_cam_online ? 'ONLINE' : 'OFFLINE');
    setSysCard('sysPI',    data.raspberry_pi_online, data.raspberry_pi_online ? 'ONLINE' : 'OFFLINE');
    setSysCard('sysBatt',  true, (data.battery_level || 0).toFixed(1) + '%');
    setSysCard('sysSolar', data.solar_charging,   data.solar_charging ? 'CHARGING ☀️' : 'IDLE');
  } catch(e) {}
}

function setSysCard(id, online, text) {
  const card   = document.getElementById(id);
  const status = card ? card.querySelector('.sys-status') : null;
  if (card) {
    card.classList.toggle('online',  online);
    card.classList.toggle('offline', !online);
  }
  if (status) {
    status.textContent = text;
    status.style.color = online ? 'var(--safe)' : 'var(--danger)';
  }
}

loadSystemStatus();
setInterval(loadSystemStatus, 5000);

/* ── Sidebar Navigation ──────────────────────────────────────────────────── */
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    item.classList.add('active');

    const section = item.dataset.section;
    const titles = {
      overview:    ['Overview',     'Real-time drain monitoring · South Africa'],
      water:       ['Water Level',  'Live sensor feed from ESP32 ultrasonic'],
      rainfall:    ['Rainfall',     'Historical data from OCHA HDX dataset'],
      predictions: ['ML Predict',   'Random Forest & Gradient Boosting models'],
      alerts:      ['Alerts',       'Threshold-based event notifications'],
      system:      ['System',       'Hardware connectivity & diagnostics'],
    };
    if (titles[section]) {
      setText('pageTitle', titles[section][0]);
      setText('pageSub',   titles[section][1]);
    }
  });
});