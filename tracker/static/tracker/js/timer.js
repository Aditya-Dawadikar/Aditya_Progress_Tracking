(function () {
  function formatElapsed(totalSeconds) {
    var s = Math.max(0, Math.floor(totalSeconds));
    var m = Math.floor(s / 60);
    var sec = s % 60;
    return (m < 10 ? "0" : "") + m + ":" + (sec < 10 ? "0" : "") + sec;
  }

  function tick(el) {
    var baseline = parseInt(el.dataset.baselineSeconds || "0", 10);
    var startedAt = el.dataset.phaseStartedAt;
    var elapsed = baseline;
    if (startedAt) {
      var startMs = new Date(startedAt).getTime();
      elapsed = baseline + Math.floor((Date.now() - startMs) / 1000);
    }
    el.textContent = formatElapsed(elapsed);
  }

  document.querySelectorAll(".phase-timer").forEach(function (el) {
    tick(el);
    setInterval(function () { tick(el); }, 1000);
  });
})();
