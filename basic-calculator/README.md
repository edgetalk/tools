# Find Flights Tool

This tool demonstrates the power and simplicity of writing tools in Shards. It provides functionality to find flights between two airports using the Aviation Stack API.

## Tool Description

The find-flights tool is a simple yet powerful example that:
- Takes departure and arrival airports in IATA format
- Queries the Aviation Stack API for flight information
- Filters flights for the current date
- Returns a formatted list of flights with relevant information

## How It Works

The tool is written in Shards, showcasing several key features:

1. **Wire Definition**: The main functionality is encapsulated in a wire called `find-flights`
2. **Parameter Handling**: Uses Shards' built-in parameter validation and type checking
3. **API Integration**: Demonstrates HTTP requests and JSON handling
4. **Data Processing**: Shows how to filter and transform data efficiently

## Code Structure

```shards
@wire(find-flights {
  {Take("from") | ExpectString = from}
  {Take("to") | ExpectString = to}
  ...
})
```

The tool definition is clean and self-documenting, showing how easy it is to:
- Define input parameters
- Handle API calls
- Process and transform data
- Return formatted results

## Why Shards is Great for Tools

1. **Declarative Syntax**: Shards' wire-based approach makes it natural to express data flow
2. **Built-in Type Safety**: Strong type checking with `ExpectString`, `ExpectTable`, etc.
3. **Composability**: Easy to combine operations with the pipe operator `|`
4. **API Integration**: Simple HTTP requests and JSON handling
5. **Error Handling**: Built-in error propagation and validation

## Usage

```shards
{
  from: "KIX"
  to: "SIN"
} | find-flights
```

This tool requires an Aviation Stack API key set in the environment as `aviationstack-api-key`.