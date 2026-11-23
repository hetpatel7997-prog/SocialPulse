// Builds every chart on a page from the JSON in <script id="chart-data">.
(function () {
  var dataEl = document.getElementById("chart-data");
  if (!dataEl || typeof Chart === "undefined") return;
  var D = JSON.parse(dataEl.textContent);
  var C = { primary: "#7C5CFC", secondary: "#20C997", text: "#9AA4B2", grid: "rgba(255,255,255,.07)" };
  var PALETTE = [C.primary, C.secondary, "#F5B942", "#FF6B6B", "#4DABF7", "#E599F7"];
  Chart.defaults.color = C.text;
  Chart.defaults.font.family = "Manrope, system-ui, sans-serif";
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.responsive = true;

  function axisTitle(text) { return text ? { display: true, text: text } : { display: false }; }

  function scales(card, stacked) {
    return {
      x: { grid: { display: false }, title: axisTitle(card.dataset.xlabel) },
      y: { beginAtZero: true, grid: { color: C.grid }, title: axisTitle(card.dataset.ylabel), ticks: { precision: 0 } }
    };
  }

  function showEmpty(card, message) {
    card.querySelector(".chart-box").classList.add("d-none");
    var e = card.querySelector(".chart-empty");
    e.classList.remove("d-none");
    e.querySelector("span").textContent = message || "No data available.";
    var t = card.querySelector(".chart-toggle");
    if (t) t.classList.add("d-none");
  }

  function datasets(series, kind) {
    return series.map(function (s, i) {
      var color = PALETTE[i % PALETTE.length];
      var d = { label: s.name, data: s.data, backgroundColor: color, borderColor: color };
      if (kind === "line") { d.fill = false; d.tension = 0.3; d.pointRadius = 3; d.backgroundColor = color; }
      if (kind === "bar") { d.borderRadius = 6; }
      return d;
    });
  }

  function heatmap(card, p) {
    var box = card.querySelector(".chart-box");
    box.style.height = "auto";
    box.innerHTML = "";
    var wrap = document.createElement("div");
    wrap.className = "heat";
    var table = document.createElement("table");
    var head = table.createTHead().insertRow();
    head.appendChild(document.createElement("th"));
    p.cols.forEach(function (c) { var th = document.createElement("th"); th.textContent = c; head.appendChild(th); });
    var body = table.createTBody();
    p.rows.forEach(function (r, i) {
      var tr = body.insertRow();
      var th = document.createElement("th"); th.textContent = r; tr.appendChild(th);
      p.values[i].forEach(function (v, j) {
        var td = tr.insertCell();
        td.textContent = v || "";
        td.style.background = v ? "rgba(124,92,252," + (0.18 + 0.82 * v / (p.max || 1)).toFixed(2) + ")" : "transparent";
        td.title = r + " " + p.cols[j] + ": " + v + (v === 1 ? " post" : " posts");
      });
    });
    wrap.appendChild(table);
    box.appendChild(wrap);
  }

  document.querySelectorAll(".chart-card").forEach(function (card) {
    var p = D[card.dataset.chart], type = card.dataset.type;
    var loading = card.querySelector(".chart-loading");
    if (loading) loading.remove();
    if (!p || p.empty) { showEmpty(card, p && p.empty); return; }
    if (p.note) card.querySelector(".chart-note").textContent = p.note;
    if (type === "heatmap") { heatmap(card, p); return; }
    var canvas = card.querySelector("canvas"), chart;
    if (type === "pie") {
      chart = new Chart(canvas, { type: "doughnut", data: { labels: p.labels, datasets: [{ data: p.series[0].data, backgroundColor: PALETTE, borderColor: "#1E2430", borderWidth: 2 }] },
        options: { plugins: { legend: { position: "right" } } } });
    } else if (type === "line") {
      chart = new Chart(canvas, { type: "line", data: { labels: p.labels, datasets: datasets(p.series, "line") },
        options: { scales: scales(card), plugins: { legend: { display: p.series.length > 1 } }, interaction: { mode: "index", intersect: false } } });
      var toggle = card.querySelector(".chart-toggle");
      if (toggle && p.daily) {
        toggle.querySelectorAll("button").forEach(function (btn) {
          btn.addEventListener("click", function () {
            toggle.querySelectorAll("button").forEach(function (b) { b.classList.remove("active"); });
            btn.classList.add("active");
            var daily = btn.dataset.mode === "daily";
            chart.data.labels = daily ? p.daily.labels : p.labels;
            chart.data.datasets[0].data = daily ? p.daily.data : p.series[0].data;
            chart.update();
          });
        });
      } else if (toggle) { toggle.classList.add("d-none"); }
    } else {
      chart = new Chart(canvas, { type: "bar", data: { labels: p.labels, datasets: datasets(p.series, "bar") },
        options: { scales: scales(card), plugins: { legend: { display: p.series.length > 1 } } } });
    }
  });
})();
