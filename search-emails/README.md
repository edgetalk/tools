# Email Search Tool

A tool for searching and retrieving emails from Gmail using Google's Gmail API.

## Tool Description

The search-emails tool provides a powerful interface to:
- Search through Gmail inbox using Google's search syntax
- Retrieve detailed email information including subjects, senders, and snippets
- Support for complex search queries with labels and time filters
- Return formatted email details in an easy to read format

## How It Works

The tool uses the Gmail API to:
1. Take a search query using Gmail search syntax
2. Authenticate with Google using OAuth
3. Search through emails matching the query
4. Retrieve metadata for matching emails
5. Format and return email details including:
   - Email ID
   - Sender information
   - Subject
   - Date
   - Content snippet

Note: Requires Google authentication token with Gmail API access permissions