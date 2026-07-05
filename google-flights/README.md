# Google Flights Tools

Tools for searching flights and fare calendars directly against Google Flights'
internal `FlightsFrontendService` RPC endpoints (the same wire format
reverse-engineered by the [fli](https://github.com/punitarani/fli) and
[fast-flights](https://github.com/AWeirdDev/flights) projects). No API key or
authentication required.

## Tools

### `google_flights_search` (search-flights.shs)

Search one-way or round-trip flights between two airports on given dates via
the `GetShoppingResults` endpoint.

- Inputs: `from`, `to` (IATA codes), `date`, optional `return-date`, `adults`,
  `seat` (economy / premium-economy / business / first), `max-stops` (0/1/2),
  `sort` (best / top / cheapest / departure-time / arrival-time / duration)
  and `currency` (ISO 4217, default USD).
- Output: up to 12 itineraries with price, total duration, stops, per-leg
  airline / flight number / airports / times / aircraft, layover details, and
  a Google Flights link for booking.
- Round trips are priced as full-trip totals; the listed options are the
  outbound legs (the return leg is picked on Google Flights when booking).

### `google_flights_cheap_dates` (cheap-dates.shs)

Scan a date range and return the lowest fare for each departure date via the
`GetCalendarGraph` endpoint — useful for finding the cheapest dates to fly.

- Inputs: `from`, `to`, `from-date`, `to-date` (max 61 days per call),
  optional `duration` (trip length in days — when set, prices become
  round-trip totals for trips of exactly that length), `adults`, `seat`,
  `currency`.
- Output: one price per date (departure ~ return pairs for round trips) plus
  the cheapest date found.

## How It Works

Both tools build the nested-array `f.req` payload Google's own web UI sends
(URL-encoded JSON wrapped in JSON), POST it as a form body, then parse the
`)]}'`-prefixed `wrb.fr` chunked response. Prices are requested in the
currency given via the `curr` URL parameter.

The response layout is positional and undocumented, so parsing is defensive:
malformed rows are skipped instead of failing the whole call. If Google
changes the wire format, see the fli project's `.reverse-eng` notes for
re-mapping the indices.
