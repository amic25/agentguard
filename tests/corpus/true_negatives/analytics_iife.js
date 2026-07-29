// An immediately-invoked function expression is not an agent tool definition.
// Measured false positive in crewAI (docs/common-room-tracking.js).
(function () {
  window.analyticsReady = true;
})();
