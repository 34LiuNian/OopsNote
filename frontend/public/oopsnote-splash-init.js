(function () {
  try {
    var k = "oopsnote-visited";
    // if (window.localStorage && localStorage.getItem(k)) {
    //   document.documentElement.classList.add('oops-splash-skip');
    //   return;
    // }
    var startedAt = Date.now();
    var minVisibleMs = 1500;
    var appReady = false;
    var resourcesLoaded = false;
    var finished = false;
    var pendingTimer = null;

    function cleanupAndPersist() {
      var el = document.getElementById("oops-splash");
      if (!el) return;
      el.classList.add("loaded");
      setTimeout(function () {
        document.documentElement.classList.add("oops-splash-done");
      }, 500);
      if (window.localStorage) localStorage.setItem(k, "1");
      // setTimeout(function() { el.remove(); }, 2000);
    }

    function tryFinish() {
      if (finished) return;
      if (!appReady || !resourcesLoaded) return;

      var elapsed = Date.now() - startedAt;
      var remain = minVisibleMs - elapsed;
      if (remain > 0) {
        if (pendingTimer) clearTimeout(pendingTimer);
        pendingTimer = setTimeout(tryFinish, remain);
        return;
      }

      finished = true;
      cleanupAndPersist();
    }

    window.__markOopsSplashAppReady = function () {
      appReady = true;
      tryFinish();
    };

    function onResourcesLoaded() {
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(function () {
          resourcesLoaded = true;
          tryFinish();
        });
      } else {
        resourcesLoaded = true;
        tryFinish();
      }
    }

    if (document.readyState === "complete") {
      onResourcesLoaded();
    } else {
      window.addEventListener("load", onResourcesLoaded, { once: true });
    }

    setTimeout(function () {
      appReady = true;
      resourcesLoaded = true;
      tryFinish();
    }, 15000);
  } catch (e) {}
})();
