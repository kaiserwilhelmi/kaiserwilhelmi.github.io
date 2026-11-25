/* Background fitting for the forecast page. The page starts this worker from the engine's own
 * source (engine.js, inlined in the page) followed by this file, so the numbers are exactly those
 * of the main-thread engine. One request: fit every method at origins lo .. hi-1, report progress,
 * and send the forecasts back. */
self.onmessage = function (ev) {
  var q = ev.data, E = self.FCEngine, t0 = Date.now(), lastPost = 0;
  try {
    var fc = E.fitRange(q.y, q.m, q.lo, q.hi, function (done, total) {
      var now = Date.now();
      if (now - lastPost > 100 || done === total) { lastPost = now; self.postMessage({ job: q.job, done: done, total: total }); }
    });
    self.postMessage({ job: q.job, fc: fc, lo: q.lo, fut: q.fut ? E.futures(q.y, q.m) : null, ms: Date.now() - t0 });
  } catch (e) {
    self.postMessage({ job: q.job, error: e && e.message || String(e) });
  }
};
