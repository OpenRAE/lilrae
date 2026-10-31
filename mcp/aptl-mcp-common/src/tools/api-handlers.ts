import { HTTPClient, HTTPTimeoutError, type HTTPError } from '../http.js';
import { LabConfig } from '../config.js';
import { assertPathOnlyEndpoint } from '../endpoint-url.js';
import { redact } from '../redaction.js';
import Ajv2020, { type ValidateFunction } from 'ajv/dist/2020.js';

export interface APIToolContext {
  httpClient: HTTPClient;
  labConfig: LabConfig;
}

// Argument interfaces for API handlers
interface APICallArgs {
  endpoint: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  params?: Record<string, unknown>;
  body?: unknown;
  headers?: Record<string, string>;
  response_type?: 'json' | 'text';
}

interface APIInfoArgs {}

interface PredefinedQueryArgs {
  params?: Record<string, unknown>;
  body?: unknown;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- MCP SDK provides untyped args; validated by JSON Schema before reaching handlers
export type APIToolHandler = (args: any, context: APIToolContext) => Promise<{ content: { type: string; text: string }[] }>;

type QueryConfig = NonNullable<LabConfig['queries']>[string];

class QueryArgumentError extends Error {}

interface FailureDetail {
  status?: number;
  failure?: 'timeout';
  api_error?: string;
}

const API_ERROR_MAX_LENGTH = 512;

function nonEmptyString(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() !== '' ? value : undefined;
}

// The error message an API put in its response body: RFC 7807 `detail`
// (Wazuh), `error.reason` (OpenSearch), `message` (MISP), `reason`
// (Shuffle), or a plain string `error`.
function apiErrorMessage(body: unknown): string | undefined {
  if (!argumentMapping(body)) {
    return undefined;
  }
  const nestedError = body.error;
  return nonEmptyString(body.detail)
    ?? (argumentMapping(nestedError) ? nonEmptyString(nestedError.reason) : undefined)
    ?? nonEmptyString(body.message)
    ?? nonEmptyString(body.reason)
    ?? nonEmptyString(body.error);
}

// Return the API's error message, redacted and then bounded. The message can
// echo supplied values (issue #1488); the exception text never appears.
function boundedApiError(body: unknown): string | undefined {
  const message = apiErrorMessage(body);
  if (message === undefined) {
    return undefined;
  }
  const redacted = String(redact(message));
  return redacted.length > API_ERROR_MAX_LENGTH
    ? `${redacted.slice(0, API_ERROR_MAX_LENGTH)}…`
    : redacted;
}

// Classify a failed call by the HTTP status of the exchange that failed, with
// the API's own error message when its response body has one, or as a timeout.
function failureDetail(error: unknown): FailureDetail {
  const httpError = error instanceof Error ? (error as HTTPError) : undefined;
  if (typeof httpError?.statusCode === 'number') {
    const apiError = boundedApiError(httpError.response);
    return apiError === undefined
      ? { status: httpError.statusCode }
      : { status: httpError.statusCode, api_error: apiError };
  }
  return error instanceof HTTPTimeoutError ? { failure: 'timeout' } : {};
}

function argumentMapping(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

// Resolve the effective request body for a predefined query. A string passes
// through as a raw payload (e.g. XML for Wazuh rule uploads); undefined/null
// falls back to the template body; otherwise the provided body is merged over
// the template object.
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- body is untyped (MCP SDK args); behavior must match the prior `any` flow
function resolveQueryBody(body: unknown, queryConfig: QueryConfig): any {
  if (typeof body === 'string') {
    return body;
  }
  if (body === undefined || body === null) {
    return queryConfig.body;
  }
  return queryConfig.body ? { ...queryConfig.body, ...(body as Record<string, unknown>) } : body;
}

// A path segment is a string or a finite number. Stringifying any other shape
// would let an array such as ["rules.xml"] pass a pattern as "rules.xml".
function pathSegmentValue(key: string, value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  throw new QueryArgumentError(`path parameter ${key} must be a string`);
}

// Reject a path parameter value that would change the request path. Encoding
// removes separators, but an empty, `.` or `..` segment still moves the path.
function assertSafePathParam(queryConfig: QueryConfig, key: string, value: string): void {
  if (value === '' || value === '.' || value === '..') {
    throw new QueryArgumentError(`path parameter ${key} must be a single non-empty path segment`);
  }
  const pattern = queryConfig.path_param_patterns?.[key];
  const match = pattern === undefined ? undefined : new RegExp(`^(?:${pattern})$`).exec(value);
  if (pattern !== undefined && match?.[0].length !== value.length) {
    throw new QueryArgumentError(`path parameter ${key} does not match the required format`);
  }
}

// Substitute `{key}` path parameters into the query URL and collect the
// remaining params as query-string params.
function buildQueryUrl(
  queryConfig: QueryConfig,
  finalParams: Record<string, unknown>,
): { url: string; queryParams: Record<string, unknown> } {
  let url = queryConfig.url;
  const queryParams: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(finalParams)) {
    const placeholder = `{${key}}`;
    if (url.includes(placeholder)) {
      const segment = pathSegmentValue(key, value);
      assertSafePathParam(queryConfig, key, segment);
      url = url.replace(placeholder, encodeURIComponent(segment));
    } else {
      queryParams[key] = value;
    }
  }
  const missing = /\{(\w+)\}/.exec(url);
  if (missing) {
    throw new QueryArgumentError(`path parameter ${missing[1]} is required`);
  }
  return { url, queryParams };
}

// Execute a predefined query, using per-query auth when specified (via a
// temporary HTTP client) otherwise the default client.
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- finalBody is untyped (MCP SDK args); behavior must match the prior `any` flow
function runPredefinedQuery(
  queryConfig: QueryConfig,
  context: APIToolContext,
  url: string,
  queryParams: Record<string, unknown>,
  finalBody: any,
) {
  if (queryConfig.auth) {
    // Create temporary HTTP client with query-specific auth.
    // SEC-006 / ADR-034 § Gotchas: both `verify_ssl` and
    // `ca_cert_path` must inherit from the top-level api config
    // when the query does not override them. Treating
    // `queryConfig.verify_ssl !== false` as the verify decision
    // forced verification on whenever a query had its own auth
    // block but no explicit `verify_ssl`, which silently broke the
    // documented local-debug override at the api level and made
    // every predefined query repeat the flag. Explicit query
    // override first, then fall back to the api setting.
    const queryAPIConfig = {
      baseUrl: '', // Not used since we have full URL
      auth: queryConfig.auth,
      verify_ssl: queryConfig.verify_ssl ?? context.labConfig.api?.verify_ssl ?? true,
      ca_cert_path: queryConfig.ca_cert_path ?? context.labConfig.api?.ca_cert_path,
    };
    const queryClient = new HTTPClient(queryAPIConfig);
    return queryClient.makeRequest(url, queryConfig.method, {
      params: queryParams,
      body: finalBody,
      responseType: queryConfig.response_type || 'json',
    });
  }
  return context.httpClient.makeRequest(url, queryConfig.method, {
    params: queryParams,
    body: finalBody,
    responseType: queryConfig.response_type || 'json',
  });
}

// Base API handler functions — each casts args to its specific interface.
// MCP SDK validates args against the JSON Schema before handlers run.
const baseAPIHandlers = {
  api_call: async (args: APICallArgs, { httpClient }: APIToolContext) => {
    const {
      endpoint,
      method = 'GET',
      params,
      body,
      headers,
      response_type = 'json'
    } = args;

    try {
      assertPathOnlyEndpoint(endpoint);
      const result = await httpClient.makeRequest(endpoint, method, {
        params,
        body,
        headers,
        responseType: response_type,
      });

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              success: true,
              method,
              endpoint,
              status: result.status,
              data: result.data,
            }, null, 2),
          },
        ],
      };
    } catch (error) {
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              success: false,
              method,
              endpoint,
              error: error instanceof Error ? error.message : 'Unknown error',
              ...failureDetail(error),
            }, null, 2),
          },
        ],
      };
    }
  },

  api_info: async (_args: APIInfoArgs, { labConfig }: APIToolContext) => {
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            target_name: labConfig.server.targetName,
            lab_name: labConfig.lab.name,
            lab_network: labConfig.lab.network_subnet,
            api_base_url: labConfig.api?.baseUrl || 'Not configured',
            available_queries: labConfig.queries ? Object.keys(labConfig.queries) : [],
            note: `Use ${labConfig.server.targetName} for SIEM operations and log analysis.`,
          }, null, 2),
        },
      ],
    };
  },

  predefined_query: async (args: PredefinedQueryArgs, context: APIToolContext, queryConfig: QueryConfig, validateParams?: ValidateFunction) => {
    try {
      if (!argumentMapping(args) || (args.params !== undefined && !argumentMapping(args.params))) {
        throw new QueryArgumentError('query arguments and params must be objects');
      }
      const finalParams = { ...queryConfig.params, ...args.params };
      if (validateParams && !validateParams(finalParams)) {
        throw new QueryArgumentError('query parameters do not match the required schema');
      }
      const finalBody = resolveQueryBody(args.body, queryConfig);
      const { url, queryParams } = buildQueryUrl(queryConfig, finalParams);
      const result = await runPredefinedQuery(queryConfig, context, url, queryParams, finalBody);

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              success: true,
              query: queryConfig.description,
              endpoint: url,
              method: queryConfig.method,
              status: result.status,
              data: result.data,
            }, null, 2),
          },
        ],
      };
    } catch (error) {
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify({
              success: false,
              query: queryConfig.description,
              endpoint: queryConfig.url,
              error: error instanceof QueryArgumentError ? error.message : 'API query failed',
              ...failureDetail(error),
            }, null, 2),
          },
        ],
      };
    }
  },
};

/**
 * Generate API tool handlers with server-specific names
 */
export function generateAPIToolHandlers(
  serverConfig: LabConfig['server'],
  queries?: LabConfig['queries'],
  includeGenericTools: boolean = true
): Record<string, APIToolHandler> {
  const handlers: Record<string, APIToolHandler> = {};

  // Map server-specific tool names to base handlers
  if (includeGenericTools) {
    handlers[`${serverConfig.toolPrefix}_api_call`] = baseAPIHandlers.api_call;
    handlers[`${serverConfig.toolPrefix}_api_info`] = baseAPIHandlers.api_info;
  }

  // Add predefined query handlers
  if (queries) {
    Object.entries(queries).forEach(([queryName, queryConfig]) => {
      const validateParams = queryConfig.params_schema
        ? new Ajv2020().compile(queryConfig.params_schema)
        : undefined;
      handlers[`${serverConfig.toolPrefix}_${queryName}`] = async (args: any, context: APIToolContext) => {
        return baseAPIHandlers.predefined_query(args, context, queryConfig, validateParams);
      };
    });
  }

  return handlers;
}
