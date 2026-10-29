/**
 * Generic APTL MCP Server
 *
 * Provides AI agents with secure access to container operations
 * in the APTL (Advanced Purple Team Lab) environment.
 * Server configuration determines the specific target and capabilities.
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  CallToolRequest,
  Tool,
} from '@modelcontextprotocol/sdk/types.js';
import Ajv2020, { type ErrorObject, type ValidateFunction } from 'ajv/dist/2020.js';
import { type LabConfig } from './config.js';
import { SSHConnectionManager } from './ssh.js';
import { HTTPClient } from './http.js';
import { initTracing, recordToolResultSize, shutdownTracing, traceToolCall } from './telemetry.js';
import { DEFAULT_MAX_TOOL_RESULT_TOKENS, boundToolResult, type ToolResult } from './tool-output-cap.js';
import { generateToolDefinitions } from './tools/definitions.js';
import { errorMessage, generateToolHandlers, type ToolHandler, type ToolContext } from './tools/handlers.js';
import { generateAPIToolDefinitions } from './tools/api-definitions.js';
import { generateAPIToolHandlers, type APIToolHandler, type APIToolContext } from './tools/api-handlers.js';

/**
 * Information passed to a `postToolHook` after a tool call resolves or rejects.
 */
export interface PostToolHookInfo {
  toolName: string;
  args: Record<string, unknown>;
  result?: unknown;
  durationMs: number;
  error?: Error;
}

/**
 * Hook fired after every MCP tool call. May return a Promise — async SIEM
 * transports (HTTP shipping, queued buffer flushes) are first-class. The
 * server awaits the returned promise inside its own try/catch, so a
 * rejected promise becomes a stderr diagnostic, not an unhandled rejection,
 * and the tool response is never disturbed (per ADR-027 best-effort
 * guarantee).
 */
export type PostToolHook = (info: PostToolHookInfo) => void | Promise<void>;

export interface CreateMCPServerOptions {
  postToolHook?: PostToolHook;
  /**
   * Maximum milliseconds to wait for an async `postToolHook` before the
   * tool response is returned anyway. Prevents a slow/hung SIEM transport
   * from blocking command execution (ADR-027 best-effort guarantee).
   * Defaults to 2000 ms; set to 0 to disable the timeout.
   */
  postToolHookTimeoutMs?: number;
}

/**
 * Create and configure an MCP server with the provided lab configuration.
 *
 * `options.postToolHook` is fired once per tool call (success or error). It is
 * the extension point ADR-027 reserves for SIEM-event emission attached to MCP
 * command execution; common itself never imports red-team logic.
 */
const DEFAULT_HOOK_TIMEOUT_MS = 2000;

async function runHookWithTimeout(
  hook: PostToolHook,
  info: PostToolHookInfo,
  timeoutMs: number,
): Promise<void> {
  const ret = hook(info);
  if (!ret || typeof ret.then !== 'function') return;
  if (timeoutMs <= 0) {
    await ret;
    return;
  }
  let timer: NodeJS.Timeout | undefined;
  const timeout = new Promise<void>((_, reject) => {
    timer = setTimeout(
      () => reject(new Error(`postToolHook timeout after ${timeoutMs}ms`)),
      timeoutMs,
    );
  });
  try {
    await Promise.race([ret, timeout]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/**
 * Close a tool's top-level arguments unless its schema sets
 * `additionalProperties` itself. Each handler reads only the arguments its
 * schema lists, so an unlisted name is a caller mistake: a misspelt optional
 * argument such as `timeout` for `timeout_ms` would otherwise be dropped and
 * the call would run with the default. The closed schema is the one the
 * server advertises, so clients see the rule the server enforces.
 */
function withClosedArguments(tool: Tool): Tool {
  if (tool.inputSchema.additionalProperties !== undefined) {
    return tool;
  }
  return { ...tool, inputSchema: { ...tool.inputSchema, additionalProperties: false } };
}

/**
 * Compile one validator per advertised tool schema, as JSON Schema 2020-12
 * (the dialect the MCP SDK documents for `inputSchema`). `allErrors` reports
 * every violation at once. The other Ajv defaults stay on purpose: strict
 * schema checks, no type coercion, no default insertion and no removal of
 * unknown properties, so a call is either dispatched exactly as sent or
 * refused. A schema Ajv cannot compile stops the server at creation instead of
 * leaving its tool unchecked.
 */
function compileArgumentValidators(tools: Tool[]): Map<string, ValidateFunction> {
  const ajv = new Ajv2020({ allErrors: true });
  const validators = new Map<string, ValidateFunction>();
  for (const tool of tools) {
    try {
      validators.set(tool.name, ajv.compile(tool.inputSchema));
    } catch (err) {
      throw new Error(`Cannot compile the input schema of ${tool.name}: ${errorMessage(err)}`);
    }
  }
  return validators;
}

/**
 * Look up a tool's handler and argument validator. A handler without an
 * advertised schema is not a callable tool.
 */
function lookUpTool(
  name: string,
  handlers: Record<string, ToolHandler | APIToolHandler>,
  validators: Map<string, ValidateFunction>,
): { handler: ToolHandler | APIToolHandler; validateArguments: ValidateFunction } {
  const handler = handlers[name];
  const validateArguments = validators.get(name);
  if (!handler || !validateArguments) {
    throw new Error(`Unknown tool: ${name}`);
  }
  return { handler, validateArguments };
}

/**
 * Describe one violation by its argument path and rule. The rejected value
 * never appears: arguments carry commands, request bodies and credentials.
 */
function describeViolation({ keyword, instancePath, params, message }: ErrorObject): string {
  const path = `arguments${instancePath}`;
  if (keyword === 'additionalProperties') {
    return `${path} must NOT have additional property ${JSON.stringify(params.additionalProperty)}`;
  }
  return `${path} ${message}`;
}

/**
 * The tool error returned for arguments outside the tool's schema. Like the
 * SDK's own `McpServer`, it is a tool result with `isError` rather than a
 * protocol error, so the calling agent can read it and correct the call.
 */
function invalidArgumentsResult(toolName: string, errors: ErrorObject[] | null | undefined) {
  const violations = (errors ?? []).map(describeViolation).join('; ');
  return {
    isError: true,
    content: [
      {
        type: 'text',
        text: JSON.stringify({
          success: false,
          error: `Invalid arguments for ${toolName}: ${violations}`,
        }, null, 2),
      },
    ],
  };
}

export function createMCPServer(labConfig: LabConfig, options: CreateMCPServerOptions = {}) {
  const { postToolHook } = options;
  const hookTimeoutMs = options.postToolHookTimeoutMs ?? DEFAULT_HOOK_TIMEOUT_MS;
  const maxToolResultTokens =
    labConfig.server.maxToolResultTokens ?? DEFAULT_MAX_TOOL_RESULT_TOKENS;
  // Initialize clients and OTel tracing based on config
  const sshManager = labConfig.containers ? new SSHConnectionManager() : null;
  const httpClient = labConfig.api ? new HTTPClient(labConfig.api) : null;
  initTracing(labConfig.server.name);

  // Pre-generate tools and handlers based on available capabilities
  let cachedTools: Tool[] = [];
  let cachedHandlers: Record<string, ToolHandler | APIToolHandler> = {};

  if (sshManager) {
    cachedTools.push(...generateToolDefinitions(labConfig.server));
    Object.assign(cachedHandlers, generateToolHandlers(labConfig.server));
  }

  if (httpClient) {
    // Only include generic tools if no predefined queries exist
    const includeGeneric = !labConfig.queries || Object.keys(labConfig.queries).length === 0;
    cachedTools.push(...generateAPIToolDefinitions(labConfig.server, labConfig.queries, includeGeneric));
    Object.assign(cachedHandlers, generateAPIToolHandlers(labConfig.server, labConfig.queries, includeGeneric));
  }

  // The advertised schemas are the enforced ones, read from the generated
  // definitions so every tool, including predefined queries, is covered.
  cachedTools = cachedTools.map(withClosedArguments);
  const argumentValidators = compileArgumentValidators(cachedTools);

  console.error(`[MCP] Initialized ${labConfig.server.name} with lab: ${labConfig.lab.name}`);
  console.error(`[MCP] Available capabilities: ${sshManager ? 'SSH' : ''}${sshManager && httpClient ? ' + ' : ''}${httpClient ? 'HTTP API' : ''}`);

  // Create MCP server
  const server = new Server(
    {
      name: labConfig.server.name,
      version: labConfig.server.version,
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );

  // Setup request handlers
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
      tools: cachedTools,
    };
  });

  server.setRequestHandler(CallToolRequestSchema, async (request: CallToolRequest) => {
    const { name, arguments: args } = request.params;
    const { handler, validateArguments } = lookUpTool(name, cachedHandlers, argumentValidators);

    // Refuse arguments outside the tool's schema before the context, the
    // trace span, the hook, any session or any backend call.
    const safeArgs: Record<string, unknown> = args ?? {};
    if (!validateArguments(safeArgs)) {
      return invalidArgumentsResult(name, validateArguments.errors);
    }

    // Determine context type based on tool name and available clients
    let context: ToolContext | APIToolContext;

    if (name.includes('_api_') || (labConfig.queries && Object.keys(labConfig.queries).some(q => name.endsWith(`_${q}`)))) {
      // API tool context
      if (!httpClient) {
        throw new Error('API tool requested but HTTP client not configured');
      }
      context = {
        httpClient,
        labConfig,
      };
    } else {
      // SSH tool context
      if (!sshManager) {
        throw new Error('SSH tool requested but SSH manager not configured');
      }
      context = {
        sshManager,
        labConfig,
      };
    }

    const t0 = Date.now();
    try {
      // Context is narrowed to the correct type above based on tool name
      const result = await traceToolCall<ToolResult>(
        name,
        labConfig.server.name,
        safeArgs,
        async () => {
          const bounded = boundToolResult<ToolResult>(
            await (handler as any)(safeArgs, context),
            maxToolResultTokens,
          );
          recordToolResultSize(bounded);
          if (bounded.truncated) {
            console.error(
              `[MCP] tool result truncated: tool=${name} ` +
                `chars=${bounded.originalChars}->${bounded.returnedChars}`,
            );
          }
          return bounded.result;
        },
      );
      if (postToolHook) {
        // Fire-and-forget: telemetry must NEVER add latency to the tool
        // response. Errors and timeouts are logged to stderr so a bad
        // hook is observable without blocking. The hook timeout still
        // applies to the lifetime of the in-flight task — we don't
        // await it on the response path.
        void runHookWithTimeout(
          postToolHook,
          { toolName: name, args: safeArgs, result, durationMs: Date.now() - t0 },
          hookTimeoutMs,
        ).catch((hookErr) => {
          console.error('[MCP] postToolHook error:', hookErr);
        });
      }
      return result;
    } catch (err) {
      if (postToolHook) {
        const error = err instanceof Error ? err : new Error(String(err));
        void runHookWithTimeout(
          postToolHook,
          { toolName: name, args: safeArgs, durationMs: Date.now() - t0, error },
          hookTimeoutMs,
        ).catch((hookErr) => {
          console.error('[MCP] postToolHook error:', hookErr);
        });
      }
      throw err;
    }
  });

  // Setup graceful shutdown handlers (once per process)
  let handlersSetup = false;

  // Return server with start method
  return {
    async start() {
      const transport = new StdioServerTransport();
      await server.connect(transport);
      console.error(`[MCP] ${labConfig.server.description.split(' - ')[0]} server running on stdio`);

      // Setup graceful shutdown only once
      if (!handlersSetup) {
        const gracefulShutdown = async (signal: string): Promise<void> => {
          console.error(`[MCP] Shutting down gracefully (${signal})...`);
          await shutdownTracing();
          if (sshManager) {
            // disconnectAll now propagates SSHError on teardown contract
            // failures so callers can detect unclean shutdown. The signal
            // handler still needs to exit; log the failure non-zero rather
            // than letting an unhandled rejection terminate Node abruptly.
            try {
              await sshManager.disconnectAll();
            } catch (err) {
              console.error('[MCP] disconnectAll failed during shutdown:', err);
              process.exit(1);
              return;
            }
          }
          process.exit(0);
        };

        process.on('SIGINT', () => { void gracefulShutdown('SIGINT'); });
        process.on('SIGTERM', () => { void gracefulShutdown('SIGTERM'); });

        handlersSetup = true;
      }
    }
  };
}
