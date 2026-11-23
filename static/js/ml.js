// Charts for the machine learning page, built from <script id="ml-data">.
(function () {
  var el = document.getElementById("ml-data");
  if (!el || typeof Chart === "undefined") return;
  var R = JSON.parse(el.textContent);
  var PAL = ["#FF6B6B", "#F5B942", "#4DABF7", "#20C997"];
  Chart.defaults.color = "#9AA4B2";
  Chart.defaults.font.family = "Manrope, system-ui, sans-serif";
  Chart.defaults.maintainAspectRatio = false;
  var grid = { color: "rgba(255,255,255,.07)" };

  var k = R.kmeans;
  if (k && k.available && document.getElementById("kmeansChart")) {
    var sets = k.clusters.map(function (c, i) {
      return { label: c.name, backgroundColor: PAL[(i + (4 - k.clusters.length)) % 4], pointRadius: 4,
        data: k.points.filter(function (p) { return p.c === i; }).map(function (p) { return { x: p.x, y: p.y }; }) };
    });
    new Chart(document.getElementById("kmeansChart"), { type: "scatter", data: { datasets: sets },
      options: { scales: { x: { title: { display: true, text: k.x_label }, grid: grid }, y: { title: { display: true, text: k.y_label }, grid: grid } } } });
  }
  var t = R.trends;
  if (t && t.available) {
    t["items"].forEach(function (item, i) {
      var c = document.getElementById("trend" + (i + 1));
      if (!c) return;
      new Chart(c, { type: "line", data: { labels: item.months, datasets: [{ label: item.label, data: item.values, borderColor: "#7C5CFC", backgroundColor: "#7C5CFC", tension: 0.3, spanGaps: true }] },
        options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, grid: grid }, x: { grid: { display: false } } } } });
    });
  }
  var f = R.forecast;
  if (f && f.available && document.getElementById("forecastChart")) {
    new Chart(document.getElementById("forecastChart"), { type: "line", data: { labels: f.labels, datasets: [
      { label: "Actual (avg likes + comments)", data: f.actual, borderColor: "#7C5CFC", backgroundColor: "#7C5CFC", tension: 0.3 },
      { label: "Trend forecast", data: f.forecast, borderColor: "#20C997", backgroundColor: "#20C997", borderDash: [6, 4], tension: 0.3 }] },
      options: { scales: { y: { beginAtZero: true, grid: grid }, x: { grid: { display: false } } } } });
  }
})();
