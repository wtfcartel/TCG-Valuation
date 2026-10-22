// Small progressive enhancements only; every page works without JavaScript.
document.addEventListener("DOMContentLoaded", () => {
  // Refresh the runs page while a run is in progress.
  const running = document.querySelector(".run-now button[disabled]");
  if (running && location.pathname.startsWith("/runs")) {
    setTimeout(() => location.reload(), 8000);
  }
});
