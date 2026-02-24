/**
 * ArielOS GAS Search & Sandbox Template
 * This script handles 'search_and_filter' requests from the ArielOS Bridge.
 */

function doPost(e) {
  var data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    return createJsonResponse("error", "Invalid JSON payload");
  }

  var action = data.action;
  if (action === "search_and_filter") {
    return handleSearchAndFilter(data);
  }

  return createJsonResponse("error", "Unknown action: " + action);
}

function handleSearchAndFilter(params) {
  var query = params.query || "";
  var filterCode = params.filterCode || "";
  
  // 1. Search Logic
  // In a real scenario, you might use UrlFetchApp to fetch data from a search API
  // For demonstration, we'll fetch a public JSON or search results.
  var searchResults = performMockSearch(query);
  
  // 2. Sandbox Filtering & Sorting Logic
  // We use 'new Function' to create a "sandbox" for the JS filter.
  var filteredResult;
  try {
    // We pass 'data' to the function. The filterCode should manipulate 'data'.
    // Example filterCode: 
    // "data = data.filter(item => item.includes('AI')).sort().reverse()"
    var filterFunc = new Function('data', filterCode + '; return data;');
    filteredResult = filterFunc(searchResults);
  } catch (err) {
    return createJsonResponse("error", "JS Sandbox Error: " + err.message);
  }
  
  return createJsonResponse("success", {
    query: query,
    result: filteredResult
  });
}

function performMockSearch(query) {
  // Mock data for demonstration
  var database = [
    "Google announces new AI features for Workspace",
    "Apple Vision Pro review: The future is here",
    "OpenAI releases GPT-5 (mock)",
    "Microsoft integrates Copilot into Windows 12",
    "NVIDIA stock hits all-time high due to AI demand",
    "Tesla FSD version 13 released"
  ];
  
  // Simple keyword filter as a "search"
  return database.filter(function(item) {
    return item.toLowerCase().indexOf(query.toLowerCase()) !== -1;
  });
}

function createJsonResponse(status, payload) {
  var response = { status: status };
  if (status === "success") {
    response.data = payload;
  } else {
    response.error = payload;
  }
  return ContentService.createTextOutput(JSON.stringify(response))
    .setMimeType(ContentService.MimeType.JSON);
}
