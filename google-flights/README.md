# Google Flights Tools

Tools for searching flights and fare calendars on Google Flights. They drive the
**public Google Flights website** (not the internal JSON RPC), because that RPC
(`batchexecute` / `FlightsFrontendService`) is blocked for cookieless callers from
most IPs — TLS impersonation and session warmup don't reliably get around it. No API
key or authentication is required.

The approach mirrors the reference projects
[fli](https://github.com/punitarani/fli) (RPC wire format) and
[fast-flights](https://github.com/AWeirdDev/fast-flights) (HTML route):

1. Build the deterministic **`tfs` protobuf itinerary token** (airports, dates, trip
   type, cabin, passengers) — the Shards encoder produces a byte-identical token to
   fast-flights.
2. GET `https://www.google.com/travel/flights/search?tfs=…`.
3. Parse the flight data Google embeds server-side in the page's `ds:1`
   `AF_initDataCallback` script block (`payload[3][0]`).

Using the `tfs` token (rather than a natural-language `?q=` search) matters: the `q`
route silently returns a smaller, pricier subset that omits the cheap LCC fares.

## Tools

### `google_flights_search` (search-flights.shs)

One-way or round-trip search between two airports on given dates. One HTTP request
(with a small retry on a degraded page), so it's fast and reliable.

- Inputs: `from`, `to` (IATA codes), `date`, optional `return-date`, `adults`,
  `children`, `seat` (economy / premium-economy / business / first), `max-stops`
  (0 = nonstop, 1, 2 — applied client-side), `sort` (best / cheapest / duration),
  `currency` (ISO 4217, default USD).
- Output: up to 12 itineraries with price, total duration, stops, per-leg
  airline / flight number / airports / times / aircraft, layover details, and a
  deterministic Google Flights link that opens the exact itinerary.
- Round trips are priced as full-trip totals; the listed options are the outbound
  legs (pick the return leg via the link when booking).
- One request per call — fast and reliable.

### `google_flights_cheap_dates` (cheap-dates.shs)

Cheapest fare per departure date across a range — for finding the cheapest dates to
fly. There is no HTML page that embeds the whole price calendar (the website loads
that grid via the same blocked RPC), so this tool reconstructs it honestly by running
**one real flight search per date** and taking each date's cheapest bookable fare.

- Inputs: `from`, `to`, `from-date`, `to-date`, optional `duration` (trip length in
  days — when set, prices are round-trip totals for a trip of exactly that length),
  `adults`, `seat`, `currency`.
- Output: one price per date (departure ~ return pairs for round trips), the cheapest
  date found, and a note if some dates couldn't be fetched.
- One request per date, issued **sequentially** — ~0.5s/date, so a two-week scan is
  ~8s and the 45-day cap is ~25s. Range capped at `gf-max-days` (45); scan wider spans
  in chunks.

**Why sequential matters (do not parallelise this).** Fetching the dates concurrently
(e.g. with `TryMany`) makes Shards' reqwest client multiplex the requests over a single
HTTP/2 connection, and Google responds to *that* pattern with degraded pages that carry
no flight rows — which looks exactly like rate-limiting but isn't. Issued one at a time,
the requests are not throttled at all (verified 15/15 dates in ~8s, matching what curl
and fast-flights get looping sequentially). If you ever need more throughput, use
separate connections / separate processes, not concurrent requests on one client.

## Notes

The response layout is positional and undocumented, so parsing is defensive: malformed
rows are skipped rather than failing the whole call. If Google changes the wire format,
re-map indices against fast-flights' `parser.py` and fli's `.reverse-eng` notes.
