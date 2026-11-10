// Adds a close button to the announcement banner and keeps it closed.
// Loaded in <head>, so a closed banner never flashes on page load.
// The key comes from conf.py: a new announcement shows again for everyone.
(function () {
  var key = "announcement-dismissed:" + document.currentScript.dataset.key;
  var root = document.documentElement;
  try {
    if (localStorage.getItem(key)) root.classList.add("announcement-dismissed");
  } catch (e) {}

  document.addEventListener("DOMContentLoaded", function () {
    var banner = document.querySelector(".bd-header-announcement");
    if (!banner) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "announcement-close";
    button.setAttribute("aria-label", "Dismiss announcement");
    button.innerHTML = "&times;";
    button.addEventListener("click", function () {
      root.classList.add("announcement-dismissed");
      try {
        localStorage.setItem(key, "1");
      } catch (e) {}
    });
    banner.appendChild(button);
  });
})();
