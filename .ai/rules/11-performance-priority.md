# R-Performance-Priority

Fastest provider response is PRIORITY 1. Always.

Priority order:
  1. Latency from send -> first delta -> complete
  2. Correctness under load
  3. Code cleanliness
  4. Everything else

When 1 and 3 conflict, 1 wins. Every hot-path change must be measured
before/after. No compensating correctness gain -> revert.

Hot path = dispatcher.stream_reply -> runtime.execute -> prompt submit
          -> response capture -> first delta emitted.
Nothing inside it may poll, sleep, re-render, re-scan, serialize, or log
unless load-bearing.
