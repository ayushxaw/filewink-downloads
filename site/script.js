"use strict";

// Installation instructions remain usable when scripting or clipboard access is unavailable.
document.querySelectorAll("[data-copy]").forEach((button) => {
  const originalLabel = button.textContent;
  let resetTimer;
  button.addEventListener("click", async () => {
    const source = document.getElementById(button.dataset.copy);
    const status = document.getElementById("copy-status");
    if (!source || !status) return;

    window.clearTimeout(resetTimer);
    try {
      if (!navigator.clipboard || !window.isSecureContext)
        throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(source.textContent.trim());
      button.textContent = "Copied!";
      status.textContent = "Installation commands copied to your clipboard.";
      resetTimer = window.setTimeout(() => {
        button.textContent = originalLabel;
      }, 2200);
    } catch {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(source);
      if (selection) {
        selection.removeAllRanges();
        selection.addRange(range);
      }
      status.textContent =
        "Commands selected. Use your computer’s copy shortcut to copy them.";
      button.textContent = "Text selected";
      resetTimer = window.setTimeout(() => {
        button.textContent = originalLabel;
      }, 2200);
    }
  });
});
