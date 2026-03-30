/**
 * AWS Lambda Entry Point — AI Workflow Automation Agent
 *
 * Handles API Gateway proxy events and routes them to the FastAPI backend.
 * Optimized for cold-start performance:
 *   - No heavy imports at module level
 *   - Reuses HTTP connections across warm invocations via global fetch (Node 20+)
 *   - Structured JSON logging for CloudWatch
 *
 * Deployment:
 *   Runtime: Node.js 20.x
 *   Memory:  512MB (provisioned concurrency for peak hours)
 *   Timeout: 30s
 */

import { APIGatewayProxyEvent, APIGatewayProxyResult, Context } from "aws-lambda";
import { route } from "./router";
import { LambdaResponse } from "./types";

const COLD_START = true;
let initialized = false;

function log(level: "INFO" | "WARN" | "ERROR", message: string, extra?: Record<string, unknown>): void {
  console.log(JSON.stringify({
    level,
    message,
    timestamp: new Date().toISOString(),
    service: "ai-workflow-automation-agent",
    ...extra,
  }));
}

async function warmUp(): Promise<void> {
  if (initialized) return;
  log("INFO", "Lambda cold start — initializing");
  // Connection warm-up happens lazily on first request
  initialized = true;
  log("INFO", "Lambda initialized");
}

export const handler = async (
  event: APIGatewayProxyEvent,
  context: Context
): Promise<APIGatewayProxyResult> => {
  const requestStart = Date.now();

  await warmUp();

  log("INFO", "Request received", {
    method: event.httpMethod,
    path: event.path,
    request_id: context.awsRequestId,
    cold_start: COLD_START,
  });

  let response: LambdaResponse;

  try {
    response = await route(event);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Internal server error";
    log("ERROR", "Unhandled error in route handler", {
      error: message,
      request_id: context.awsRequestId,
    });
    response = {
      statusCode: 500,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
      body: JSON.stringify({
        error: "InternalServerError",
        message,
        request_id: context.awsRequestId,
      }),
    };
  }

  const latencyMs = Date.now() - requestStart;

  log("INFO", "Request completed", {
    method: event.httpMethod,
    path: event.path,
    status_code: response.statusCode,
    latency_ms: latencyMs,
    request_id: context.awsRequestId,
  });

  return response;
};
