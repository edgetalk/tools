# Flight Information Tool

A tool for retrieving detailed flight information using a flight number through the Aviation Stack API.

## Tool Description

The flight-info tool provides a simple interface to:
- Query flight details using IATA flight numbers (e.g. SQ123)
- Get real-time flight status and information
- Return formatted flight details including timing, status, and route information

## How It Works

The tool uses the Aviation Stack API to:
1. Take a flight number as input in IATA format
2. Query the Aviation Stack API for flight details
3. Return comprehensive flight information for up to 5 matching flights
4. Format and display the results in a clean format

Note: Requires an Aviation Stack API key set in the environment as `aviationstack-api-key`