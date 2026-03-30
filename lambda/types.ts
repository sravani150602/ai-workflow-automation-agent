/**
 * TypeScript type definitions for the AWS Lambda Workflow Agent handler.
 */

export interface QueryPayload {
  user_id: string;
  query: string;
  transaction_id?: string;
  category?: QueryCategory;
}

export type QueryCategory =
  | "payment_status"
  | "refund_request"
  | "dispute"
  | "account_inquiry"
  | "fraud_alert"
  | "billing_error"
  | "general";

export type WorkflowState = "received" | "context_loaded" | "llm_processing" | "resolved" | "escalated";

export interface QueryResolution {
  query_id: string;
  workflow_state: WorkflowState;
  resolution: string;
  confidence: number;
  escalated: boolean;
  escalation_reason: string | null;
  actions_taken: string[];
  latency_ms: number;
  resolved_at: string;
}

export interface LambdaResponse {
  statusCode: number;
  headers: Record<string, string>;
  body: string;
}

export interface ErrorResponse {
  error: string;
  message: string;
  request_id?: string;
}
