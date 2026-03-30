/**
 * Query Router — dispatches incoming Lambda events to the correct workflow path.
 *
 * Routing logic:
 *   - POST /query         → submitQuery
 *   - GET  /query/{id}    → getQuery
 *   - GET  /queries       → listQueries
 *   - POST /query/{id}/escalate  → escalateQuery
 *   - GET  /metrics       → getMetrics
 */

import { APIGatewayProxyEvent } from "aws-lambda";
import { LambdaResponse } from "./types";

const API_BASE_URL = process.env.API_BASE_URL || "http://localhost:8000";

const HEADERS = {
  "Content-Type": "application/json",
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

async function forwardToApi(
  method: string,
  path: string,
  body?: unknown,
  queryParams?: Record<string, string>
): Promise<LambdaResponse> {
  const url = new URL(`${API_BASE_URL}${path}`);
  if (queryParams) {
    for (const [k, v] of Object.entries(queryParams)) {
      url.searchParams.set(k, v);
    }
  }

  const res = await fetch(url.toString(), {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });

  const responseBody = await res.text();
  return {
    statusCode: res.status,
    headers: HEADERS,
    body: responseBody,
  };
}

export async function route(event: APIGatewayProxyEvent): Promise<LambdaResponse> {
  const method = event.httpMethod.toUpperCase();
  const path = event.path;
  const queryParams = (event.queryStringParameters as Record<string, string>) || {};

  let body: unknown;
  if (event.body) {
    try {
      body = JSON.parse(event.body);
    } catch {
      return {
        statusCode: 400,
        headers: HEADERS,
        body: JSON.stringify({ error: "Invalid JSON", message: "Request body must be valid JSON" }),
      };
    }
  }

  // Route matching
  if (method === "POST" && path === "/query") {
    return forwardToApi("POST", "/query", body);
  }

  if (method === "GET" && path === "/queries") {
    return forwardToApi("GET", "/queries", undefined, queryParams);
  }

  if (method === "GET" && path.startsWith("/query/")) {
    const queryId = path.replace("/query/", "").split("/")[0];
    return forwardToApi("GET", `/query/${queryId}`);
  }

  if (method === "POST" && path.includes("/escalate")) {
    const queryId = path.split("/")[2];
    return forwardToApi("POST", `/query/${queryId}/escalate`, undefined, queryParams);
  }

  if (method === "POST" && path.includes("/feedback")) {
    const queryId = path.split("/")[2];
    return forwardToApi("POST", `/query/${queryId}/feedback`, body);
  }

  if (method === "GET" && path === "/metrics") {
    return forwardToApi("GET", "/metrics");
  }

  if (method === "GET" && path === "/health") {
    return forwardToApi("GET", "/health");
  }

  if (method === "OPTIONS") {
    return { statusCode: 200, headers: HEADERS, body: "" };
  }

  return {
    statusCode: 404,
    headers: HEADERS,
    body: JSON.stringify({ error: "Not Found", message: `No route for ${method} ${path}` }),
  };
}
