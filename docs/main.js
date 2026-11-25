(function () {
  var REPO = "https://github.com/Bobo0925-a/PhoneAudioSink";
  var btn = document.getElementById("clone-copy");
  if (!btn) return;

  var label = btn.querySelector(".copy-label");
  var state = btn.querySelector(".copy-state");
  var resetTimer = null;

  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    var ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  }

  function flash(msg, ok) {
    state.textContent = msg;
    state.style.color = ok ? "#4c8dff" : "#e07070";
    btn.disabled = true;
    clearTimeout(resetTimer);
    resetTimer = setTimeout(function () {
      state.textContent = "";
      btn.disabled = false;
    }, 1600);
  }

  btn.addEventListener("click", function () {
    function done(ok) { flash(ok ? "已复制" : "复制失败，请手动复制", ok); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(REPO).then(function () { done(true); },
        function () { done(fallbackCopy(REPO)); });
    } else {
      done(fallbackCopy(REPO));
    }
  });
})();
