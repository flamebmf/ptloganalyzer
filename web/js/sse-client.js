// Copyright (c) 2026 PlurumTech.com
// SPDX-License-Identifier: LicenseRef-Personal-Use-Only
function connectSSE() {
  const evtSource = new EventSource('/api/sse/events');

  evtSource.addEventListener('anomaly', function(e) {
    try {
      const data = JSON.parse(e.data);
      showToast('Anomaly: ' + data.title, 'error');
      // Update badge if on dashboard
      const badge = document.getElementById('anomalyBadge');
      if (badge) {
        const cur = parseInt(badge.textContent) || 0;
        badge.textContent = cur + 1;
      }
    } catch(err) {}
  });

  evtSource.addEventListener('heartbeat', function() {
    // Keep-alive, no action needed
  });

  evtSource.onerror = function() {
    // Reconnect after 5s
    setTimeout(connectSSE, 5000);
  };
}

// Auto-connect when page loads
if (document.getElementById('sseEnabled')) {
  connectSSE();
}
