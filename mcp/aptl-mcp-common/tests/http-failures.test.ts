import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createServer, type Server } from 'node:http';
import { once } from 'node:events';
import type { AddressInfo } from 'node:net';

import { HTTPClient, HTTPTimeoutError } from '../src/http.js';
import { markToolFailure, observeToolOutcome } from '../src/lilrae-tool-outcome.js';

// The node:http request path (verify_ssl=false) and the wazuh-jwt token
// exchange, against a local server: a failure keeps its HTTP status and body,
// and a timeout is an HTTPTimeoutError, so tool responses can classify both.
describe('HTTPClient failure classification', () => {
  let server: Server;
  let baseUrl: string;

  beforeAll(async () => {
    server = createServer((request, response) => {
      if (request.url === '/slow') {
        return;
      }
      const status = request.url === '/auth' ? 401 : 403;
      response.writeHead(status, { 'Content-Type': 'application/json' });
      response.end('{"error":"refused"}');
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  });

  afterAll(async () => {
    server.closeAllConnections();
    server.close();
    await once(server, 'close');
  });

  function client(auth?: object): HTTPClient {
    return new HTTPClient({
      baseUrl,
      auth: auth ?? { type: 'apikey', header: 'X-Test-Key', apiKey: 'fixture' },
      verify_ssl: false,
      timeout: 200,
    } as any);
  }

  function jwtClient(authPath: string): HTTPClient {
    return client({
      type: 'wazuh-jwt',
      username: 'fixture-user',
      password: 'fixture-password',
      auth_url: `${baseUrl}${authPath}`,
    });
  }

  it('raises a request timeout as HTTPTimeoutError', async () => {
    await expect(client().makeRequest('/slow')).rejects.toBeInstanceOf(HTTPTimeoutError);
  });

  it('keeps the HTTP status of a refused request', async () => {
    await expect(client().makeRequest('/refused')).rejects.toMatchObject({ statusCode: 403 });
  });

  it('keeps the token endpoint status and body when the exchange returns no token', async () => {
    await expect(jwtClient('/auth').makeRequest('/refused')).rejects.toMatchObject({
      statusCode: 401,
      response: { error: 'refused' },
    });
  });

  it('raises a token exchange timeout as HTTPTimeoutError', async () => {
    await expect(jwtClient('/slow').makeRequest('/refused')).rejects.toBeInstanceOf(
      HTTPTimeoutError,
    );
  });

  it.each(['fetch', 'agent', 'token'])('cancels the pending %s request when participant authority ends', async (path) => {
    const stopped = new AbortController();
    const started = once(server, 'request');
    const requester = path === 'token' ? jwtClient('/slow') : new HTTPClient({
      baseUrl, auth: { type: 'none' }, verify_ssl: path === 'fetch', timeout: 10000,
    } as any);
    const execution = observeToolOutcome(async () => {
      try { await requester.makeRequest('/slow'); }
      catch (error) { markToolFailure(error); return 'interrupted'; }
      return 'unexpected completion';
    }, stopped.signal);
    await started;
    stopped.abort();
    expect(await execution).toMatchObject({ result: 'interrupted', uncertain: true });
  }, 2000);

  it('retains a completed HTTP rejection as known even when the request is unsuccessful', async () => {
    const execution = await observeToolOutcome(async () => {
      try { await client().makeRequest('/refused'); }
      catch (error) { markToolFailure(error); return (error as any).statusCode; }
    });
    expect(execution).toMatchObject({ result: 403, uncertain: false });
  });
});
