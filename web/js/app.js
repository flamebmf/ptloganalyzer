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
