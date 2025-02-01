# Flight Search Tool

A Shards-based tool for searching real-time flight information between airports using the Aviation Stack API.

## Tool Description

The flight-search tool provides a simple interface to:
- Query flights between two airports using IATA codes
- Get real-time flight information for the current date
- Return formatted flight details including airline, flight number, and timing information

## How It Works

The tool leverages Shards' powerful wire system to:
1. Take departure and arrival airport codes as input
2. Query the Aviation Stack API
3. Filter flights for the current date
4. Return relevant flight information in a clean format

## Code Structure

```shards
@wire(find-flights {
  {Take("from") | ExpectString = from}
  {Take("to") | ExpectString = to}
  ...
})
```

The implementation showcases Shards' elegant syntax for:
- Parameter handling and validation
- HTTP requests and JSON processing
- Data filtering and transformation
- Clean error handling

## Why Shards Excels for API Tools

1. **Declarative Flow**: Shards' wire-based approach makes data flow clear and maintainable
2. **Built-in Type Safety**: Strong type checking prevents runtime errors
3. **Composable Operations**: The pipe operator `|` enables clean function composition
4. **HTTP Integration**: Simple, powerful HTTP request handling
5. **JSON Processing**: Native JSON support with type-safe parsing

## Usage Example

```shards
{
  from: "KIX"
  to: "SIN"
} | find-flights
```

Note: Requires an Aviation Stack API key set in the environment as `aviationstack-api-key`.