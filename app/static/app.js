const $ = (selector) => document.querySelector(selector);

function htmlToText(value) {
  const element = document.createElement('div');
  element.innerHTML = value;
  return element.textContent || element.innerText || '';
}

function setState(id, ready, label) {
  const dot = $(`#${id}-dot`);
  const text = $(`#${id}-status`);
  dot.className = `status-dot ${ready ? 'is-ready' : 'is-warn'}`;
  text.textContent = label;
}

function formatDate(value) {
  try { return new Intl.DateTimeFormat(undefined, { day:'numeric', month:'short', hour:'2-digit', minute:'2-digit' }).format(new Date(value)); }
  catch { return value; }
}

function renderStatus(data) {
  const r = data.readiness;
  setState('telegram', r.telegram, r.telegram ? 'Connected' : 'Needs setup');
  setState('notion', r.notion, r.notion ? 'Connected' : 'Needs setup');
  setState('ai', r.ai_parser, r.ai_parser ? 'Natural language ready' : 'Command mode');
  $('#system-state').textContent = r.telegram && r.notion ? 'Your private pipeline is ready.' : 'Finish the connection steps in the README.';
  $('#summary-time').textContent = `Daily brief · ${data.daily_summary_time}`;
  $('#timezone-note').textContent = `Timezone: ${data.timezone}`;
  const reminderList = $('#reminder-list');
  reminderList.innerHTML = '';
  if (!data.upcoming_reminders.length) reminderList.innerHTML = '<li class="empty-state">No scheduled reminders yet.</li>';
  data.upcoming_reminders.forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item.title;
    const time = document.createElement('time'); time.textContent = formatDate(item.remind_at); li.append(time); reminderList.append(li);
  });
  const list = $('#capture-list'); list.innerHTML = '';
  $('#capture-count').textContent = `${data.recent_captures.length} recent`;
  if (!data.recent_captures.length) list.innerHTML = '<p class="empty-state">Nothing captured from this device yet.</p>';
  data.recent_captures.forEach((item) => {
    const entry = item.notion_url ? document.createElement('a') : document.createElement('div');
    entry.className = 'capture-entry'; if (item.notion_url) { entry.href = item.notion_url; entry.target = '_blank'; entry.rel = 'noreferrer'; }
    const type = document.createElement('span'); type.className = 'capture-type'; type.textContent = item.item_type;
    const title = document.createElement('span'); title.className = 'capture-title'; title.textContent = item.title;
    const date = document.createElement('span'); date.className = 'capture-date'; date.textContent = formatDate(item.created_at);
    entry.append(type, title, date); list.append(entry);
  });
}

async function loadLogs() {
  const list = $('#logs-list');
  try {
    const response = await fetch('/api/logs');
    if (!response.ok) throw new Error('Could not load logs.');
    const logs = await response.json();
    list.innerHTML = '';
    if (!logs.length) {
      list.innerHTML = '<p class="empty-state">No logs available.</p>';
      return;
    }
    logs.forEach((log) => {
      const entry = document.createElement('div');
      entry.className = 'capture-entry';
      entry.style.display = 'block';
      entry.style.padding = '0.75rem';
      
      const date = document.createElement('div');
      date.className = 'capture-date';
      date.textContent = formatDate(log.created_at);
      date.style.marginBottom = '0.5rem';
      
      const req = document.createElement('div');
      req.innerHTML = `<strong>You:</strong> ${log.user_message.replace(/</g, '&lt;')}`;
      req.style.marginBottom = '0.25rem';
      
      const res = document.createElement('div');
      res.innerHTML = `<strong>Bot:</strong> ${log.bot_reply.replace(/\\n/g, '<br>')}`;
      res.style.color = 'var(--text-dim)';
      
      entry.append(date, req, res);
      list.append(entry);
    });
  } catch (error) {
    list.innerHTML = `<p class="empty-state">${error.message}</p>`;
  }
}

async function refresh() {
  const response = await fetch('/api/status');
  if (!response.ok) throw new Error('Could not load dashboard status.');
  renderStatus(await response.json());
  await loadLogs();
}

$('#refresh-logs').addEventListener('click', () => {
  const btn = $('#refresh-logs');
  btn.textContent = 'Loading...';
  loadLogs().finally(() => { btn.innerHTML = 'Refresh <span>↺</span>'; });
});

function updateClock() {
  const now = new Date();
  $('#local-date').textContent = new Intl.DateTimeFormat(undefined, { weekday:'short', day:'numeric', month:'short' }).format(now);
  $('#local-time').textContent = new Intl.DateTimeFormat(undefined, { hour:'2-digit', minute:'2-digit' }).format(now);
}

$('#capture-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = $('#capture-text').value.trim(); if (!text) return;
  const button = event.currentTarget.querySelector('button'); const result = $('#capture-result');
  button.disabled = true; button.textContent = 'Saving…'; result.hidden = true;
  try {
    const response = await fetch('/api/capture', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ text }) });
    const payload = await response.json(); if (!response.ok) throw new Error(payload.detail || 'Capture failed.');
    result.textContent = htmlToText(payload.reply); result.hidden = false; $('#capture-text').value = ''; await refresh();
  } catch (error) { result.textContent = error.message; result.hidden = false; }
  finally { button.disabled = false; button.innerHTML = 'Save to Notion <span>→</span>'; }
});

$('#test-connections').addEventListener('click', async (event) => {
  const button = event.currentTarget; button.disabled = true; button.textContent = 'Testing…';
  try { await fetch('/api/test-connections', {method:'POST'}); await refresh(); }
  finally { button.disabled = false; button.innerHTML = 'Test connections <span>↗</span>'; }
});

updateClock(); setInterval(updateClock, 1000); refresh().catch((error) => { $('#system-state').textContent = error.message; });
