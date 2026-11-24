// Fix guidance: copy buttons, and reloading the section after the review changes.

const section = document.getElementById("guidance");

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false; // no clipboard access (plain http from another machine): select it instead
  }
}

function select(el) {
  const range = document.createRange();
  range.selectNodeContents(el);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

async function onClick(event) {
  const button = event.target.closest("button.copy");
  if (!button) return;
  const pre = button.parentElement.querySelector("pre");
  const copied = await copyText(pre.textContent);
  if (!copied) select(pre);
  button.textContent = copied ? "Copied" : "Selected: press ctrl/cmd + C";
  setTimeout(() => { button.textContent = "Copy"; }, 2500);
}

// Fetch the section again; the last request made is the one shown.
let latest = 0;
export async function refreshGuidance() {
  if (!section) return;
  const mine = ++latest;
  try {
    const response = await fetch("guidance", {cache: "no-store"});
    if (response.ok && mine === latest) section.innerHTML = await response.text();
  } catch {
    // the section keeps what it showed; the next save tries again
  }
}

if (section) section.addEventListener("click", onClick);
