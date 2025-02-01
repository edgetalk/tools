# Flight Search Tool

A tool for searching real-time flight information between airports using the Aviation Stack API.

## Tool Description

The find-flights tool provides a simple interface to:
- Query flights between two airports using IATA codes
- Get real-time flight information for the current date
- Return formatted flight details including airline, flight number, and timing information

## How It Works

The tool Aviation Stack API to:
1. Take departure and arrival airport codes as input
2. Query the Aviation Stack API
3. Filter flights for the current date
4. Return relevant flight information in a clean format

Note: Requires an Aviation Stack API key set in the environment as `aviationstack-api-key`.