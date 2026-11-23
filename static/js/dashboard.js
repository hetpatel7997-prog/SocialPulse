// Shared UI behaviour: mobile sidebar and dismissible notifications.
document.addEventListener("DOMContentLoaded", function () {
  var toggle = document.getElementById("sidebarToggle");
  var sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", function () { sidebar.classList.toggle("open"); });
  }
  document.querySelectorAll(".sp-toast").forEach(function (t) {
    var close = t.querySelector(".toast-close");
    if (close) close.addEventListener("click", function () { t.remove(); });
    setTimeout(function () { t.remove(); }, 6000);
  });
});
