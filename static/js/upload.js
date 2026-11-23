// Drag-and-drop upload with per-file progress and an import summary.
(function () {
  var zone = document.getElementById("dropzone"), input = document.getElementById("fileInput");
  var queue = document.getElementById("queue");
  var csrf = document.querySelector('meta[name="csrf-token"]').content;
  var ALLOWED = ["json", "csv", "xlsx", "html", "htm"];

  document.getElementById("browseBtn").addEventListener("click", function (e) { e.stopPropagation(); input.click(); });
  zone.addEventListener("click", function () { input.click(); });
  zone.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  ["dragenter", "dragover"].forEach(function (ev) { zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add("over"); }); });
  ["dragleave", "drop"].forEach(function (ev) { zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.remove("over"); }); });
  zone.addEventListener("drop", function (e) { handle(e.dataTransfer.files); });
  input.addEventListener("change", function () { handle(input.files); input.value = ""; });

  function size(b) { return b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB"; }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }

  function handle(files) {
    Array.prototype.forEach.call(files, function (f) { enqueue(f); });
  }

  function enqueue(file) {
    var row = el("div", "upload-row");
    var head = el("div", "d-flex justify-content-between gap-2");
    head.appendChild(el("strong", "", file.name));
    head.appendChild(el("span", "muted small", size(file.size)));
    var bar = el("div", "progress sp-progress"), fill = el("div", "progress-bar"); bar.appendChild(fill);
    var status = el("div", "small mt-2 muted", "Waiting…");
    row.appendChild(head); row.appendChild(bar); row.appendChild(status);
    queue.prepend(row);

    var ext = file.name.split(".").pop().toLowerCase();
    if (ALLOWED.indexOf(ext) < 0) return fail("Unsupported file type. Use .json, .csv, .xlsx or .html.");

    var fd = new FormData();
    fd.append("file", file);
    fd.append("kind", document.getElementById("kind").value);
    fd.append("snapshot_date", document.getElementById("snapshot").value);
    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/upload/file");
    xhr.setRequestHeader("X-CSRFToken", csrf);
    xhr.upload.onprogress = function (e) {
      if (e.lengthComputable) { var p = Math.round(e.loaded / e.total * 100); fill.style.width = p + "%"; status.textContent = p < 100 ? "Uploading " + p + "%" : "Processing…"; }
    };
    xhr.onerror = function () { fail("Network error. Check your connection and try again."); };
    xhr.onload = function () {
      var res = null;
      try { res = JSON.parse(xhr.responseText); } catch (e) { /* not JSON */ }
      if (xhr.status === 413) return fail("File is too large.");
      if (!res) return fail("The server returned an unexpected response (status " + xhr.status + ").");
      if (!res.ok) return fail(res.error);
      fill.style.width = "100%"; fill.classList.add("bg-success");
      status.className = "small mt-2 text-success"; status.textContent = "Imported successfully";
      row.appendChild(summary(res));
    };
    xhr.send(fd);

    function fail(msg) {
      fill.style.width = "100%"; fill.classList.add("bg-danger");
      status.className = "small mt-2 text-danger"; status.textContent = msg;
    }
  }

  function summary(res) {
    var box = el("div", "import-summary");
    var t = res.totals;
    [["Records imported", t.records], ["Duplicates skipped", t.duplicates], ["Missing values", t.missing], ["Invalid records", t.invalid]].forEach(function (x) {
      var c = el("div"); c.appendChild(el("div", "kpi-value", String(x[1]))); c.appendChild(el("div", "muted small", x[0])); box.appendChild(c);
    });
    var list = el("div", "w-100 small mt-2");
    res.datasets.forEach(function (d) { list.appendChild(el("div", "", "✓ " + d.kind + ": " + d.records + " records")); });
    (res.skipped || []).forEach(function (s) { list.appendChild(el("div", "muted", "Skipped: " + s)); });
    var link = el("a", "", "Open dashboard"); link.href = "/dashboard"; link.className = "d-inline-block mt-2";
    list.appendChild(link);
    box.appendChild(list);
    return box;
  }
})();
