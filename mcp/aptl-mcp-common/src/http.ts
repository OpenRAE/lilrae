import https from 'node:https';
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { LabConfig, TLS_VERIFICATION_REQUIRED } from './config.js';
import { resolveApiRequestUrl } from './endpoint-url.js';
import { knownToolFailure, toolAbortSignal } from './lilrae-tool-outcome.js';

export interface HTTPError extends Error {
  statusCode?: number;
  response?: any;
}

/** A request, or its token exchange, that did not finish within its timeout. */
export class HTTPTimeoutError extends Error {}

export interface HTTPResponse {
  ok: boolean;
  status: number;
  data: any;
  text: string;
}

/**
 * Generic HTTP client for API operations
 */
export class HTTPClient {
  // SEC-006 / ADR-034: per-instance CA-aware agent. Built once at
  // construction when `ca_cert_path` is set. Cached
  // here so the CA file is read once per HTTPClient, not per request.
  // `null` means "no custom CA — fall back to fetch() with system trust";
  // an instantiated Agent means "use node:https with this CA, rejectUnauthorized=true".
  private readonly caAgent: https.Agent | null;

  constructor(private config: LabConfig['api']) {
    if (!config) {
      throw knownToolFailure(new Error('API configuration is required'));
    }
    // SEC-009: the client always verifies TLS. A service with a private CA
    // names that CA in ca_cert_path.
    if (config.verify_ssl === false) {
      throw knownToolFailure(new Error(TLS_VERIFICATION_REQUIRED));
    }
    this.caAgent = buildCaAgent(config);
  }

  // cached JWT for wazuh-jwt mode (per HTTPClient instance)
  private cachedJwt: string | null = null;

  /**
   * Build authentication headers based on config (sync paths only).
   * For 'wazuh-jwt' use getAuthHeadersAsync.
   */
  private buildAuthHeaders(): Record<string, string> {
    const { auth } = this.config!;

    switch (auth.type) {
      case 'basic':
        if (!auth.username || !auth.password) {
          throw knownToolFailure(new Error('Username and password required for basic auth'));
        }
        const basicAuth = Buffer.from(`${auth.username}:${auth.password}`).toString('base64');
        return { 'Authorization': `Basic ${basicAuth}` };

      case 'bearer':
        if (!auth.token) {
          throw knownToolFailure(new Error('Token required for bearer auth'));
        }
        return { 'Authorization': `Bearer ${auth.token}` };

      case 'apikey':
        if (!auth.apiKey || !auth.header) {
          throw knownToolFailure(new Error('API key and header name required for API key auth'));
        }
        return { [auth.header]: auth.apiKey };

      case 'custom':
        if (!auth.header || !auth.token) {
          throw knownToolFailure(new Error('Header name and token required for custom auth'));
        }
        return { [auth.header]: auth.token };

      case 'wazuh-jwt':
        if (this.cachedJwt) {
          return { 'Authorization': `Bearer ${this.cachedJwt}` };
        }
        // Should have been exchanged before sync call; placeholder so auth runs anyway
        return {};

      default:
        return {};
    }
  }

  /**
   * Async-aware auth header builder. For 'wazuh-jwt' mode, performs a one-time
   * POST {auth_url} with basic credentials, caches the returned JWT, and
   * returns a Bearer header. Subsequent calls reuse the cached token.
   */
  private async getAuthHeadersAsync(): Promise<Record<string, string>> {
    const { auth } = this.config!;
    if (auth.type !== 'wazuh-jwt') return this.buildAuthHeaders();

    if (this.cachedJwt) {
      return { 'Authorization': `Bearer ${this.cachedJwt}` };
    }

    if (!auth.username || !auth.password || !auth.auth_url) {
      throw knownToolFailure(new Error('wazuh-jwt requires username, password, auth_url'));
    }

    const basicAuth = Buffer.from(`${auth.username}:${auth.password}`).toString('base64');
    const tokenResp = await this.lowLevelRequest(
      auth.auth_url,
      'POST',
      { 'Authorization': `Basic ${basicAuth}` },
      undefined,
      this.config!.timeout || 30000,
    );
    let parsed: any;
    try { parsed = JSON.parse(tokenResp.text); } catch { parsed = {}; }
    const token = parsed?.data?.token;
    if (!token) {
      const error: HTTPError = new Error(
        `wazuh-jwt: no token in auth response (status ${tokenResp.status})`,
      );
      error.statusCode = tokenResp.status;
      knownToolFailure(error);
      error.response = parsed;
      throw error;
    }
    this.cachedJwt = token;
    return { 'Authorization': `Bearer ${token}` };
  }

  /**
   * Low-level helper used by the JWT exchange path. Does not apply auth.
   */
  private lowLevelRequest(
    url: string,
    method: string,
    headers: Record<string, string>,
    body: string | undefined,
    timeout: number,
  ): Promise<{ status: number; text: string }> {
    return new Promise((resolve, reject) => {
      const parsed = new URL(url);
      const transport = parsed.protocol === 'https:' ? https : http;
      const reqOpts: https.RequestOptions = {
        signal: toolAbortSignal(),
        hostname: parsed.hostname,
        port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
        path: parsed.pathname + parsed.search,
        method,
        headers: {
          ...headers,
          ...(body ? { 'Content-Length': String(Buffer.byteLength(body)) } : {}),
        },
        timeout,
        ...(parsed.protocol === 'https:' ? this.httpsAgentOpts() : {}),
      };
      const req = transport.request(reqOpts, (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (c: Buffer) => chunks.push(c));
        res.on('end', () => resolve({
          status: res.statusCode ?? 0,
          text: Buffer.concat(chunks).toString(),
        }));
      });
      req.on('timeout', () => { req.destroy(); reject(new HTTPTimeoutError(`token timeout after ${timeout}ms`)); });
      req.on('error', reject);
      if (body) req.write(body);
      req.end();
    });
  }

  /**
   * Append query-string params to an absolute URL. The endpoint may already
   * carry a query string (`/_search?size=1`) or a fragment, so the params
   * join the existing query with `&` and go before any fragment. The
   * endpoint's own query text is kept as written.
   */
  private appendParams(url: string, params: Record<string, any> | undefined): string {
    if (!params) return url;
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });
    const qs = searchParams.toString();
    if (!qs) return url;
    const target = new URL(url);
    const existing = target.search.slice(1);
    target.search = existing ? `${existing}&${qs}` : qs;
    return target.href;
  }

  /**
   * Encode a request body, set Content-Type for raw string bodies, and
   * return the encoded payload. Mutates *headers* in place when a raw
   * body needs a default Content-Type (matches the pre-refactor behaviour).
   */
  private encodeBody(
    body: any,
    headers: Record<string, string>,
    callerHeaders: Record<string, string> | undefined
  ): string | undefined {
    if (body === undefined || body === null) return undefined;
    if (typeof body === 'string') {
      if (!('Content-Type' in (callerHeaders || {}))) {
        headers['Content-Type'] = 'application/octet-stream';
      }
      return body;
    }
    return JSON.stringify(body);
  }

  /**
   * Issue the request via the fetch() path (system trust, no custom CA).
   * Split from makeRequest so the orchestrator's decision-tree complexity
   * stays inside SonarTS's gate.
   */
  private async fetchRequest(
    url: string,
    method: string,
    headers: Record<string, string>,
    bodyStr: string | undefined,
    timeout: number,
    responseType?: 'json' | 'text'
  ): Promise<HTTPResponse> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, {
        method,
        headers,
        body: bodyStr,
        signal: toolAbortSignal()
          ? AbortSignal.any([controller.signal, toolAbortSignal()!])
          : controller.signal,
      });
      return await this.parseResponse(response, responseType);
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw new HTTPTimeoutError(`Request timeout after ${timeout}ms`);
      }
      throw error;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /**
   * Make HTTP request with automatic auth and error handling
   */
  async makeRequest(
    endpoint: string,
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET',
    options: {
      params?: Record<string, any>;
      body?: any;
      headers?: Record<string, string>;
      responseType?: 'json' | 'text';
    } = {}
  ): Promise<HTTPResponse> {
    toolAbortSignal()?.throwIfAborted();
    const { baseUrl = '', timeout = 30000, default_headers = {} } = this.config!;

    // Resolve against configured baseUrl and reject cross-origin destinations before auth.
    const baseFullUrl = resolveApiRequestUrl(endpoint, baseUrl);
    const url = this.appendParams(baseFullUrl, options.params);

    // Build headers (await for wazuh-jwt path, no-op for others)
    const authHeaders = await this.getAuthHeadersAsync();
    toolAbortSignal()?.throwIfAborted();
    // `Accept: application/json` is required for JSON APIs that content-negotiate
    // their responses: MISP, for one, HTTP 302-redirects a POST (e.g.
    // /attributes/add) to its web UI when the client does not explicitly accept
    // JSON, which silently breaks writes like add_indicator. Declared first so
    // callers (default_headers / per-call headers) can still override it.
    const headers: Record<string, string> = {
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      ...default_headers,
      ...authHeaders,
      ...options.headers,
    };

    // String body passes through raw (e.g. XML for Wazuh rule upload). Set
    // Content-Type to octet-stream unless caller already set one.
    const bodyStr = this.encodeBody(options.body, headers, options.headers);

    // SEC-006, SEC-009: Node's `fetch` cannot accept a custom CA bundle.
    // With ca_cert_path, node:https verifies against the CA-aware agent built
    // once at construction (`this.caAgent`). Without it, fetch() verifies
    // against the system trust.
    if (this.caAgent) {
      return this.makeRequestWithAgent(
        url, method, headers, { ...options, body: bodyStr } as any, timeout
      );
    }
    return this.fetchRequest(url, method, headers, bodyStr, timeout, options.responseType);
  }

  /**
   * Parse response body text into data, falling back to raw text on JSON errors.
   */
  private parseBody(text: string, responseType?: 'json' | 'text'): any {
    if (responseType === 'text') return text;
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  /**
   * Build an HTTPError from a status code, status text, and parsed body.
   */
  private buildHTTPError(status: number, statusText: string, body: any): HTTPError {
    const error = new Error(`HTTP ${status}: ${statusText}`) as HTTPError;
    error.statusCode = status;
    error.response = body;
    return knownToolFailure(error);
  }

  /**
   * Make HTTP request using node:https with the CA-aware agent (SEC-006,
   * SEC-009: ``ca_cert_path`` set).
   */
  private makeRequestWithAgent(
    url: string,
    method: string,
    headers: Record<string, string>,
    options: { body?: any; responseType?: 'json' | 'text' },
    timeout: number,
  ): Promise<HTTPResponse> {
    return new Promise((resolve, reject) => {
      const parsed = new URL(url);
      const transport = parsed.protocol === 'https:' ? https : http;
      // body may already be a pre-stringified raw payload (XML / JSON) at this point
      const bodyStr = serializeAgentBody(options.body);

      const reqOptions: https.RequestOptions = {
        signal: toolAbortSignal(),
        hostname: parsed.hostname,
        port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
        path: parsed.pathname + parsed.search,
        method,
        headers: {
          ...headers,
          ...(bodyStr ? { 'Content-Length': String(Buffer.byteLength(bodyStr)) } : {}),
        },
        timeout,
        ...(parsed.protocol === 'https:' ? this.httpsAgentOpts() : {}),
      };

      const req = transport.request(reqOptions, (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (chunk: Buffer) => chunks.push(chunk));
        res.on('end', () => {
          const responseText = Buffer.concat(chunks).toString();
          const responseData = this.parseBody(responseText, options.responseType);
          const status = res.statusCode ?? 0;
          const ok = status >= 200 && status < 300;

          if (!ok) {
            reject(this.buildHTTPError(status, res.statusMessage ?? '', responseData));
            return;
          }

          resolve({ ok, status, data: responseData, text: responseText });
        });
      });

      req.on('timeout', () => {
        req.destroy();
        reject(new HTTPTimeoutError(`Request timeout after ${timeout}ms`));
      });

      req.on('error', (error) => {
        reject(error);
      });

      if (bodyStr) {
        req.write(bodyStr);
      }
      req.end();
    });
  }

  /**
   * Return the agent options for an HTTPS URL (SEC-006, SEC-009).
   *
   * With a configured CA, the per-instance CA-aware agent verifies the
   * server. Without one, ``{}`` lets Node verify against the system trust;
   * the JWT exchange's ``lowLevelRequest`` path always uses node:https.
   */
  private httpsAgentOpts(): { agent?: https.Agent } {
    return this.caAgent ? { agent: this.caAgent } : {};
  }

  /**
   * Parse a fetch Response into our HTTPResponse format
   */
  private async parseResponse(
    response: Response,
    responseType?: 'json' | 'text'
  ): Promise<HTTPResponse> {
    const responseText = await response.text();
    const responseData = this.parseBody(responseText, responseType);

    if (!response.ok) {
      throw this.buildHTTPError(response.status, response.statusText, responseData);
    }

    return {
      ok: response.ok,
      status: response.status,
      data: responseData,
      text: responseText,
    };
  }
}

/**
 * Encode a body for the node:https agent path.
 *
 * Returns `undefined` for null/undefined bodies, pass-through for already-stringified
 * payloads (e.g. raw XML for Wazuh rule uploads), and JSON-stringified output for
 * structured bodies. Extracted to its own function so the agent path body assignment
 * is one named call, not a nested ternary (SonarTS S3358).
 */
function serializeAgentBody(body: any): string | undefined {
  if (body === undefined || body === null) return undefined;
  if (typeof body === 'string') return body;
  return JSON.stringify(body);
}

/**
 * Build the per-instance CA-aware HTTPS agent (SEC-006 / ADR-034).
 *
 * Returns `null` when the config has no `ca_cert_path`, and otherwise an
 * `https.Agent({ ca, rejectUnauthorized: true })`.
 *
 * The CA bundle is read at construction time and cached on the agent —
 * subsequent requests do not re-read the file. If `ca_cert_path` is set
 * but the file cannot be read, this throws synchronously so the failure
 * surfaces at HTTPClient construction (fail-closed) rather than at the
 * first request, and never silently degrades to "verify against system
 * trust".
 */
function buildCaAgent(config: NonNullable<LabConfig['api']>): https.Agent | null {
  const caPath = config.ca_cert_path;
  if (!caPath) return null;
  let ca: Buffer;
  try {
    ca = readFileSync(caPath);
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    throw knownToolFailure(new Error(`ca_cert_path "${caPath}" not readable: ${reason}`));
  }
  return new https.Agent({ ca, rejectUnauthorized: true });
}
