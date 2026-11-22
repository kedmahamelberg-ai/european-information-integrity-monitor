const filters = document.querySelector("#filters");
if (filters) {
  filters.hidden = false;
  const rows = document.querySelectorAll("tr[data-desk]");
  function select(desk) {
    for (const row of rows) row.hidden = desk !== "All" && row.dataset.desk !== desk;
    for (const button of filters.querySelectorAll("button")) {
      button.setAttribute("aria-pressed", String(button.dataset.filter === desk));
    }
  }
  filters.onclick = event => {
    const button = event.target.closest("button[data-filter]");
    if (button) select(button.dataset.filter);
  };
  window.addEventListener("hashchange", () => {
    const target = document.getElementById(location.hash.slice(1));
    if (target?.hidden && target.dataset.desk) {
      select("All");
      target.scrollIntoView();
    }
  });
}
