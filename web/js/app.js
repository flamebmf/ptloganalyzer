// Copyright (c) 2026 PlurumTech.com
// SPDX-License-Identifier: LicenseRef-Personal-Use-Only
function __(key) {
  if (window.LANG && window.LANG[key]) return window.LANG[key];
  return key;
}

function formatTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    year:'numeric',month:'2-digit',day:'2-digit',
    hour:'2-digit',minute:'2-digit',second:'2-digit'
  });
}

function severityClass(sev) {
  const map = {0:'emerg',1:'alert',2:'crit',3:'err',
               4:'warning',5:'notice',6:'info',7:'debug'};
  return map[sev] || 'info';
}

function severityBadge(sev) {
  const cls = severityClass(sev);
  return `<span class="severity-badge ${cls}" title="${cls}"></span>`;
}

async function apiGet(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function apiPatch(url, data) {
  const r = await fetch(url, {
    method:'PATCH',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(data),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function apiDelete(url) {
  const r = await fetch(url, {method:'DELETE'});
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function apiPost(url, data) {
  const r = await fetch(url, {
    method:'POST',
    headers: data ? {'Content-Type':'application/json'} : {},
    body: data ? JSON.stringify(data) : undefined,
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function showToast(msg, type) {
  let wrap = document.getElementById('toastWrap');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'toastWrap';
    wrap.className = 'toast-wrap';
    document.body.appendChild(wrap);
  }
  const t = document.createElement('div');
  t.className = 'toast-item';
  t.textContent = msg;
  if (type === 'error') t.style.borderLeftColor = '#ff5252';
  else if (type === 'success') t.style.borderLeftColor = '#00e676';
  else t.style.borderLeftColor = 'var(--pt-accent)';
  wrap.appendChild(t);
  setTimeout(() => { t.remove(); }, 4000);
}

function openLogModal(logId) {
  var overlay = document.getElementById('logModal');
  var body = document.getElementById('modalBody');
  document.getElementById('modalLogId').textContent = logId;
  body.innerHTML = '<span style="color:var(--pt-muted)">Загрузка...</span>';
  overlay.style.display = 'flex';

  apiGet('/api/logs/' + logId)
    .then(function(data) {
      if (!data || data.error) {
        body.innerHTML = '<span style="color:#ff5252">Запись не найдена</span>';
        return;
      }
      var sevNames = {0:'EMERG',1:'ALERT',2:'CRIT',3:'ERR',4:'WARNING',5:'NOTICE',6:'INFO',7:'DEBUG'};
      var facNames = {0:'kern',1:'user',2:'mail',3:'daemon',4:'auth',5:'syslog',6:'lpr',7:'news',8:'uucp',9:'cron',10:'authpriv',11:'ftp',16:'local0',17:'local1',18:'local2',19:'local3',20:'local4',21:'local5',22:'local6',23:'local7'};

      var sev = sevNames[data.severity] || data.severity;
      var fac = facNames[data.facility] || data.facility;
      var ts = formatTime(data.ts);
      var raw = data.raw || '';
      var msg = data.message || '';

      body.innerHTML =
        '<table style="width:100%;border-collapse:collapse">'
        + '<tr><td style="color:var(--pt-muted);width:100px;padding:4px 8px 4px 0">Устройство</td><td style="padding:4px 0"><strong>' + escHtml(data.hostname||'') + '</strong></td></tr>'
        + '<tr><td style="color:var(--pt-muted);padding:4px 8px 4px 0">Время</td><td style="padding:4px 0">' + ts + '</td></tr>'
        + '<tr><td style="color:var(--pt-muted);padding:4px 8px 4px 0">Severity</td><td style="padding:4px 0"><span class="severity-badge ' + severityClass(data.severity) + '"></span> ' + sev + '</td></tr>'
        + '<tr><td style="color:var(--pt-muted);padding:4px 8px 4px 0">Facility</td><td style="padding:4px 0">' + fac + '</td></tr>'
        + '<tr><td style="color:var(--pt-muted);padding:4px 8px 4px 0">App</td><td style="padding:4px 0">' + escHtml(data.app_name||'-') + '</td></tr>'
        + '<tr><td style="color:var(--pt-muted);padding:4px 8px 4px 0">Message</td><td style="padding:4px 0;word-break:break-all;font-family:\'Roboto Mono\',monospace;font-size:.8rem">' + escHtml(msg) + '</td></tr>'
        + (raw && raw !== msg ? '<tr><td style="color:var(--pt-muted);padding:4px 8px 4px 0">Raw</td><td style="padding:4px 0;word-break:break-all;font-family:\'Roboto Mono\',monospace;font-size:.75rem;color:var(--pt-muted)">' + escHtml(raw) + '</td></tr>' : '')
        + '</table>';
    })
    .catch(function(err) {
      body.innerHTML = '<span style="color:#ff5252">Ошибка загрузки: ' + err + '</span>';
    });
}

function closeLogModal() {
  document.getElementById('logModal').style.display = 'none';
}

function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function convertLogIds(text) {
  if (!text) return '';
  return text.replace(/#(\d+)\b/g, '<a href="#" onclick="event.preventDefault();openLogModal($1);return false" class="log-ref">#$1</a>');
}

(function() {
  var bg=document.getElementById('bgBars');
  if (!bg) {
    bg = document.createElement('div');
    bg.className = 'bg-bars';
    bg.id = 'bgBars';
    document.body.insertBefore(bg, document.body.firstChild);
  }
})();

// Page navigation
function loadPage(page) {
  const main = document.getElementById('mainContent');
  if (!main) return;
  if (page === 'index.html' || page === '' || page === '/') {
    location.reload();
    return;
  }
  main.dataset.page = page;
  const cb = page.includes('?') ? '&_t=' : '?_t=';
  fetch(page + cb + Date.now())
    .then(r => r.text())
    .then(html => {
      main.innerHTML = html;
      main.querySelectorAll('script').forEach(old => {
        const s = document.createElement('script');
        if (old.src) {
          const src = old.getAttribute('src');
          const srcPath = src.split('?')[0];
          const allScripts = document.querySelectorAll('script[src]');
          const alreadyLoaded = Array.from(allScripts).some(s => !main.contains(s) && s.getAttribute('src').split('?')[0] === srcPath);
          if (!alreadyLoaded) {
            s.src = src;
          }
        } else {
          s.textContent = old.textContent.replace(/\b(const|let)\s+/g, 'var ');
        }
        try {
          old.parentNode.replaceChild(s, old);
        } catch(e) {
          console.warn('loadPage script:', e.message);
        }
      });
      document.querySelectorAll('.nav-links a').forEach(a => a.classList.remove('active'));
      const pageName = page.split('?')[0].split('#')[0];
      const link = document.querySelector(`.nav-links a[href="#${pageName}"]`);
      if (link) link.classList.add('active');
      window.location.hash = page;
    })
    .catch(err => showToast('Failed to load page: '+err, 'error'));
}

// SPA hash navigation
window.addEventListener('hashchange', () => {
  const page = window.location.hash.replace(/^#/, '') || 'index.html';
  if (page === 'index.html' || page === '') {
    if (window.location.hash) {
      history.pushState('', document.title, window.location.pathname);
    }
    location.reload();
    return;
  }
  loadPage(page);
});

// Load from hash on initial page load (skip if already on index)
(function() {
  const page = window.location.hash.replace(/^#/, '');
  if (page && page !== 'index.html' && document.getElementById('mainContent')) {
    loadPage(page);
  }
})();
