// Copyright (c) 2026 PlurumTech.com
// SPDX-License-Identifier: LicenseRef-Personal-Use-Only
var ptChartTheme = ptChartTheme || {
  color: ['#00d4ff','#7b61ff','#00e676','#ffd740','#ff5252'],
  tooltip: {
    theme: 'dark',
    x: { show: true, format: 'dd.MM HH:mm' },
    style: { fontSize: '12px', fontFamily: 'Roboto' }
  },
  grid: {
    show: true,
    strokeDashArray: 3,
    borderColor: 'rgba(255,255,255,.04)',
    xaxis: { lines: { show: true } },
    yaxis: { lines: { show: true } }
  },
  xaxis: {
    labels: { style: { colors: '#7a8294', fontSize: '11px', fontFamily: 'Roboto' } },
    axisBorder: { show: false },
    axisTicks: { show: false }
  },
  yaxis: {
    labels: { style: { colors: '#7a8294', fontSize: '11px', fontFamily: 'Roboto' } },
  },
  legend: {
    labels: { colors: '#e4e8ee', fontFamily: 'Roboto' }
  }
};

function createLogVolumeD2DChart(elId, data, dataYesterday) {
  var series = [{
    name: 'Today',
    data: data.map(d => ({ x: d.hour, y: d.count }))
  }];
  if (dataYesterday && dataYesterday.length) {
    series.push({
      name: 'Yesterday',
      data: dataYesterday.map(d => ({ x: d.hour, y: d.count }))
    });
  }
  var options = {
    ...ptChartTheme,
    chart: { type: 'area', height: 225, toolbar: { show: false },
             background: 'transparent', foreColor: '#7a8294',
             fontFamily: 'Roboto' },
    series: series,
    stroke: { curve: 'smooth', width: 2 },
    colors: ['#00d4ff', 'rgba(122,130,148,.4)'],
    fill: {
      type: 'gradient',
      gradient: { shadeIntensity: 1, opacityFrom: 0.3, opacityTo: 0 }
    },
    dataLabels: { enabled: false },
    markers: { size: 0 },
    xaxis: {
      type: 'datetime',
      labels: {
        datetimeUTC: false,
        format: 'dd.MM HH:00',
        style: { colors: '#7a8294', fontSize: '10px', fontFamily: 'Roboto' }
      },
      axisBorder: { show: false },
      axisTicks: { show: false }
    }
  };
  const chart = new ApexCharts(document.getElementById(elId), options);
  chart.render();
  return chart;
}

function createLogVolumeWeekChart(elId, data, dataPrev) {
  var series = [{
    name: 'This week',
    data: data.map(d => ({ x: d.day, y: d.count }))
  }];
  if (dataPrev && dataPrev.length) {
    series.push({
      name: 'Last week',
      data: dataPrev.map(d => ({ x: d.day, y: d.count }))
    });
  }
  var options = {
    ...ptChartTheme,
    chart: { type: 'area', height: 225, toolbar: { show: false },
             background: 'transparent', foreColor: '#7a8294',
             fontFamily: 'Roboto' },
    series: series,
    colors: ['#00d4ff', 'rgba(122,130,148,.4)'],
    stroke: { curve: 'smooth', width: 2 },
    fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.3, opacityTo: 0, stops: [0, 100] } },
    dataLabels: { enabled: false },
    markers: { size: 0 },
    xaxis: {
      type: 'datetime',
      labels: {
        datetimeUTC: false,
        format: 'dd.MM',
        style: { colors: '#7a8294', fontSize: '10px', fontFamily: 'Roboto' }
      },
      axisBorder: { show: false },
      axisTicks: { show: false }
    },
    yaxis: {
      labels: { style: { colors: '#7a8294', fontSize: '10px', fontFamily: 'Roboto' } },
      forceNiceScale: true
    }
  };
  const chart = new ApexCharts(document.getElementById(elId), options);
  chart.render();
  return chart;
}

function createLogVolumeMonthChart(elId, data, dataPrev) {
  var series = [{
    name: 'This month',
    data: data.map(d => ({ x: d.day, y: d.count }))
  }];
  if (dataPrev && dataPrev.length) {
    series.push({
      name: 'Last month',
      data: dataPrev.map(d => ({ x: d.day, y: d.count }))
    });
  }
  var options = {
    ...ptChartTheme,
    chart: { type: 'area', height: 225, toolbar: { show: false },
             background: 'transparent', foreColor: '#7a8294',
             fontFamily: 'Roboto' },
    series: series,
    colors: ['#7b61ff', 'rgba(122,130,148,.4)'],
    stroke: { curve: 'smooth', width: 2 },
    fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.3, opacityTo: 0, stops: [0, 100] } },
    dataLabels: { enabled: false },
    markers: { size: 0 },
    xaxis: {
      type: 'datetime',
      labels: {
        datetimeUTC: false,
        format: 'dd.MM',
        style: { colors: '#7a8294', fontSize: '9px', fontFamily: 'Roboto' }
      },
      axisBorder: { show: false },
      axisTicks: { show: false }
    },
    yaxis: {
      labels: { style: { colors: '#7a8294', fontSize: '10px', fontFamily: 'Roboto' } },
      forceNiceScale: true
    }
  };
  const chart = new ApexCharts(document.getElementById(elId), options);
  chart.render();
  return chart;
}

var _volChart = null;

function switchVolTab(tab) {
  document.querySelectorAll('.chart-tab').forEach(function(b) {
    b.classList.toggle('active', b.getAttribute('data-voltab') === tab);
  });
  if (_volChart) { _volChart.destroy(); _volChart = null; }
  var el = document.getElementById('dashVolumeChart');
  if (!el) return;
  if (tab === 'd2d') {
    _volChart = createLogVolumeD2DChart('dashVolumeChart', window._volD2D || [], window._volD2DPrev || []);
  } else if (tab === 'week') {
    _volChart = createLogVolumeWeekChart('dashVolumeChart', window._volWeek || [], window._volWeekPrev || []);
  } else if (tab === 'month') {
    _volChart = createLogVolumeMonthChart('dashVolumeChart', window._volMonth || [], window._volMonthPrev || []);
  }
}

function createAnomalyTrendChart(elId, data, forecast) {
  var series = [{
    name: 'Anomalies',
    type: 'bar',
    data: data.map(d => ({ x: d.hour, y: d.count }))
  }];
  if (forecast && forecast.length) {
    series.push({
      name: 'Trend',
      type: 'line',
      data: forecast.map(d => ({ x: d.hour, y: d.count }))
    });
  }
  var options = {
    ...ptChartTheme,
    chart: { type: 'line', height: 180, toolbar: { show: false },
             background: 'transparent', foreColor: '#7a8294',
             fontFamily: 'Roboto', sparkline: { enabled: false } },
    series: series,
    colors: ['#ff5252', '#ffd740'],
    stroke: { width: [0, 2] },
    plotOptions: {
      bar: { columnWidth: '60%', borderRadius: 2, distributed: false }
    },
    dataLabels: { enabled: false },
    markers: { size: [0, 0] },
    xaxis: {
      type: 'datetime',
      labels: {
        datetimeUTC: false,
        format: 'HH:00',
        style: { colors: '#7a8294', fontSize: '10px', fontFamily: 'Roboto' }
      },
      axisBorder: { show: false },
      axisTicks: { show: false }
    },
    yaxis: {
      labels: { style: { colors: '#7a8294', fontSize: '10px', fontFamily: 'Roboto' } },
      forceNiceScale: true
    }
  };
  const chart = new ApexCharts(document.getElementById(elId), options);
  chart.render();
  return chart;
}

function createLogVolumeChart(elId, data) {
  var options = {
    ...ptChartTheme,
    chart: { type: 'area', height: 225, toolbar: { show: false },
             background: 'transparent', foreColor: '#7a8294',
             fontFamily: 'Roboto' },
    series: [{ name: 'Volume', data: data.map(d => ({ x: d.hour, y: d.count })) }],
    stroke: { curve: 'smooth', width: 2 },
    colors: ['#00d4ff'],
    fill: {
      type: 'gradient',
      gradient: { shadeIntensity: 1, opacityFrom: 0.3, opacityTo: 0 }
    },
    dataLabels: { enabled: false },
    markers: { size: 0 },
    xaxis: {
      type: 'datetime',
      labels: {
        datetimeUTC: false,
        format: 'dd.MM HH:00',
        style: { colors: '#7a8294', fontSize: '10px', fontFamily: 'Roboto' }
      },
      axisBorder: { show: false },
      axisTicks: { show: false }
    }
  };
  const chart = new ApexCharts(document.getElementById(elId), options);
  chart.render();
  return chart;
}

function createApexLineChart(elId, datasets) {
  var series = datasets.map(function(ds) {
    return { name: ds.label, data: ds.data.map(function(p) { return { x: p.x, y: p.y }; }) };
  });
  var colors = ['#00d4ff','#ff5252','#ffd740','#00e676','#7c4dff','#ff6d00','#00bcd4','#e040fb'];
  var options = {
    ...ptChartTheme,
    chart: { type: 'line', height: 160, toolbar: { show: false },
             background: 'transparent', foreColor: '#7a8294',
             fontFamily: 'Roboto', animations: { enabled: false } },
    series: series,
    stroke: { curve: 'straight', width: 1.5 },
    colors: colors.slice(0, datasets.length),
    dataLabels: { enabled: false },
    markers: { size: 0 },
    grid: { ...ptChartTheme.grid, yaxis: { lines: { show: true } } },
    xaxis: {
      type: 'datetime',
      labels: {
        datetimeUTC: false,
        format: 'HH:00',
        style: { colors: '#7a8294', fontSize: '9px', fontFamily: 'Roboto' }
      },
      axisBorder: { show: false },
      axisTicks: { show: false }
    },
    yaxis: {
      labels: { style: { colors: '#7a8294', fontSize: '9px', fontFamily: 'Roboto' } }
    },
    legend: {
      show: true,
      labels: { colors: '#aaa' },
      fontSize: '10px',
      itemMargin: { horizontal: 8 }
    }
  };
  const chartEl = document.getElementById(elId);
  const chart = new ApexCharts(chartEl, options);
  chart.render();
  return chart;
}

function createSeverityChart(elId, data) {
  const colors = ['#ff1744','#ff5252','#d50000','#ff9100','#ffd740','#00e676','#00d4ff','#7a8294'];
  const labels = ['Emerg','Alert','Crit','Error','Warning','Notice','Info','Debug'];
  const filtered = data.filter(d => d.count > 0);

  const options = {
    ...ptChartTheme,
    chart: { type: 'donut', height: 200, background: 'transparent',
             foreColor: '#7a8294', fontFamily: 'Roboto' },
    series: filtered.map(d => d.count),
    labels: filtered.map(d => labels[d.severity] || `Sev ${d.severity}`),
    colors: filtered.map(d => colors[d.severity] || '#7a8294'),
    dataLabels: { enabled: false },
    legend: { position: 'bottom', labels: { colors: '#e4e8ee' } },
    plotOptions: {
      pie: {
        donut: { size: '65%', labels: {
          show: true, total: { show: true, label: 'Total', color: '#e4e8ee' }
        }}
      }
    }
  };
  const chart = new ApexCharts(document.getElementById(elId), options);
  chart.render();
  return chart;
}
