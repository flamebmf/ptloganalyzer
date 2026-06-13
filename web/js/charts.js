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

function createLogVolumeChart(elId, data, dataYesterday) {
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
    chart: { type: 'area', height: 200, toolbar: { show: false },
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

function createAnomalyTrendChart(elId, data) {
  var options = {
    ...ptChartTheme,
    chart: { type: 'bar', height: 180, toolbar: { show: false },
             background: 'transparent', foreColor: '#7a8294',
             fontFamily: 'Roboto', sparkline: { enabled: false } },
    series: [{
      name: 'Anomalies',
      data: data.map(d => ({ x: d.hour, y: d.count }))
    }],
    colors: ['#ff5252'],
    plotOptions: {
      bar: { columnWidth: '60%', borderRadius: 2, distributed: false }
    },
    dataLabels: { enabled: false },
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
