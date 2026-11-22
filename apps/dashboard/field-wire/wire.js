for (const poster of document.querySelectorAll(".poster")) {
  const frames = Array.from(poster.querySelectorAll("article"));
  if (frames.length < 2) continue;
  let index = 0;
  const controls = document.createElement("div");
  controls.className = "controls";
  const status = document.createElement("span");
  status.setAttribute("aria-live", "polite");
  function select(next) {
    index = (next + frames.length) % frames.length;
    frames.forEach((frame, i) => { frame.hidden = i !== index; });
    status.textContent = (index + 1) + " / " + frames.length;
  }
  for (const [step, label] of [[-1, "Previous"], [1, "Next"]]) {
    const button = document.createElement("button");
    button.textContent = step < 0 ? "←" : "→";
    button.setAttribute("aria-label", label + " " + poster.querySelector("h2").textContent + " dispatch");
    button.onclick = () => select(index + step);
    controls.append(button);
    if (step < 0) controls.append(status);
  }
  poster.append(controls);
  select(0);
}
