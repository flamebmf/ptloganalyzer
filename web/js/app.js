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

function openLogModal(logId, deviceId) {
  var overlay = document.getElementById('logModal');
  var body = document.getElementById('modalBody');
  document.getElementById('modalLogId').textContent = logId;
  body.innerHTML = '<span style="color:var(--pt-muted)">Загрузка...</span>';
  overlay.style.display = 'flex';

  var url = '/api/logs/' + logId;
  if (deviceId) url += '?device_id=' + deviceId;
  apiGet(url)
    .then(function(data) {
      if (!data || data.error) {
        body.innerHTML = '<span style="color:#ff5252">Запись не найдена</span>';
        return;
      }
      if (data._device_mismatch) {
        body.innerHTML = '<div style="color:#ffa726;padding:8px;margin-bottom:8px;background:rgba(255,167,38,.1);border-radius:6px;font-size:.8rem"><i class="bi bi-exclamation-triangle"></i> Этот #ID относится к устройству <strong>' + escHtml(data.hostname||'другому') + '</strong></div>'
          + body.innerHTML;
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

function convertLogIds(text, deviceId) {
  if (!text) return '';
  var idAttr = deviceId ? ',' + deviceId : '';
  return text.replace(/#(\d+)\b/g, '<a href="#" onclick="event.preventDefault();openLogModal($1' + idAttr + ');return false" class="log-ref">#$1</a>');
}

function mdToHtml(text) {
  if (!text) return '';
  var codeBlocks = [];
  var codeBlockId = 0;
  text = text.replace(/```(\w*)\n([\s\S]*?)```/g, function(m, lang, code) {
    var id = 'cb_' + (codeBlockId++);
    codeBlocks[id] = {lang: lang || 'bash', code: code.trim()};
    return '%%%' + id + '%%%';
  });
  // AI-generated headers: === TITLE ===
  text = text.replace(/^===\s*(.+?)\s*===$/gm, '%%H2%%$1%%/H2%%');
  text = escHtml(text);
  // Restore code blocks
  for (var id in codeBlocks) {
    var cb = codeBlocks[id];
    var html = '<div class="code-block" id="' + id + '">'
      + '<div class="code-block-header">'
      + '<span>' + escHtml(cb.lang) + '</span>'
      + '<button class="code-copy-btn" onclick="copyCode(\'' + id + '\')"><i class="bi bi-clipboard"></i></button>'
      + '</div>'
      + '<pre><code>' + escHtml(cb.code) + '</code></pre>'
      + '</div>';
    text = text.replace('%%%' + id + '%%%', html);
  }
  // Restore headers
  text = text.replace(/%%H2%%(.+?)%%\/H2%%/g, '<h2 class="summary-h2">$1</h2>');
  // Markdown headers
  text = text.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  text = text.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  text = text.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // Bold/italic
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Inline code
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Numbered lists: group 1. 2. 3. into <ol>
  text = text.replace(/((?:^\d+\.\s+.+\n?)+)/gm, function(m) {
    return '<ol>' + m.replace(/^\d+\.\s+(.+)/gm, '<li>$1</li>') + '</ol>';
  });
  // Bullet lists: group • or - items into <ul>
  text = text.replace(/((?:^[•\-]\s+.+\n?)+)/gm, function(m) {
    return '<ul>' + m.replace(/^[•\-]\s+(.+)/gm, '<li>$1</li>') + '</ul>';
  });
  // Wrap <li> items NOT inside <ol>/<ul> — catch stray bullets
  text = text.replace(/^[•\-]\s+(.+)$/gm, '<li>$1</li>');
  // Line break consolidation
  text = text.replace(/\n{2,}/g, '<br><br>');
  text = text.replace(/\n/g, '<br>');
  return text;
}

function copyCode(id) {
  var block = document.getElementById(id);
  if (!block) return;
  var code = block.querySelector('pre code');
  if (!code) return;
  var text = code.textContent;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function() {
      var btn = block.querySelector('.code-copy-btn');
      btn.innerHTML = '<i class="bi bi-check-lg"></i>';
      setTimeout(function() { btn.innerHTML = '<i class="bi bi-clipboard"></i>'; }, 2000);
    }).catch(function(){});
  } else {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.left = '-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    var btn = block.querySelector('.code-copy-btn');
    btn.innerHTML = '<i class="bi bi-check-lg"></i>';
    setTimeout(function() { btn.innerHTML = '<i class="bi bi-clipboard"></i>'; }, 2000);
  }
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

function createSeverityDropdown(container) {
  const items = [
    {value:'', label:'Severity', cls:''},
    {value:'0', label:'EMERG', cls:'emerg'},
    {value:'1', label:'ALERT', cls:'alert'},
    {value:'2', label:'CRIT', cls:'crit'},
    {value:'3', label:'ERR', cls:'err'},
    {value:'4', label:'WARNING', cls:'warning'},
    {value:'5', label:'NOTICE', cls:'notice'},
    {value:'6', label:'INFO', cls:'info'},
    {value:'7', label:'DEBUG', cls:'debug'},
  ];
  container.classList.add('sev-dropdown');
  container.innerHTML = '<div class="sev-dropdown-selected" tabindex="0"><span>Severity</span><i class="bi bi-chevron-down"></i></div>'
    + '<div class="sev-dropdown-menu">'
    + items.map(function(o) {
        var dot = o.cls ? '<span class="severity-badge ' + o.cls + '"></span>' : '';
        return '<div class="sev-dropdown-item" data-value="' + o.value + '">' + dot + o.label + '</div>';
      }).join('')
    + '</div>';
  container._value = '';
  var sel = container.querySelector('.sev-dropdown-selected');
  var menu = container.querySelector('.sev-dropdown-menu');

  sel.addEventListener('click', function(e) {
    e.stopPropagation();
    menu.classList.toggle('open');
  });

  container.querySelectorAll('.sev-dropdown-item').forEach(function(el) {
    el.addEventListener('click', function(e) {
      e.stopPropagation();
      container.querySelectorAll('.sev-dropdown-item').forEach(function(x) { x.classList.remove('selected'); });
      el.classList.add('selected');
      container._value = el.dataset.value;
      var label = el.textContent.trim();
      sel.innerHTML = el.innerHTML + '<i class="bi bi-chevron-down"></i>';
      menu.classList.remove('open');
      container.dispatchEvent(new Event('change'));
    });
  });

  document.addEventListener('click', function() { menu.classList.remove('open'); });

  Object.defineProperty(container, 'value', {
    get: function() { return container._value; },
    set: function(v) {
      container._value = v || '';
      container.querySelectorAll('.sev-dropdown-item').forEach(function(el) {
        if (el.dataset.value === container._value) {
          el.classList.add('selected');
          sel.innerHTML = el.innerHTML + '<i class="bi bi-chevron-down"></i>';
        } else {
          el.classList.remove('selected');
        }
      });
    }
  });

  Object.defineProperty(container, 'disabled', {
    get: function() { return container.classList.contains('disabled'); },
    set: function(v) {
      container.classList.toggle('disabled', !!v);
    }
  });
}

// Load from hash on initial page load (skip if already on index)
(function() {
  const page = window.location.hash.replace(/^#/, '');
  if (page && page !== 'index.html' && document.getElementById('mainContent')) {
    loadPage(page);
  }
})();
