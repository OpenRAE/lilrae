import { describe, it, expect, vi, beforeEach } from 'vitest';
import { HTTPClient, HTTPTimeoutError } from '../src/http.js';

// Mock fetch globally
global.fetch = vi.fn();

describe('HTTPClient', () => {
  const mockFetch = vi.mocked(global.fetch);

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('creates client with valid API config', () => {
    const config = {
      baseUrl: 'https://api.example.com',
      auth: { type: 'basic' as const, username: 'user', password: 'pass' }
    };

    const client = new HTTPClient(config);
    expect(client).toBeDefined();
  });

  it('throws error with no API config', () => {
    expect(() => new HTTPClient(undefined)).toThrow('API configuration is required');
  });

  it('builds basic auth headers correctly', async () => {
    const config = {
      baseUrl: 'https://api.example.com',
      auth: { type: 'basic' as const, username: 'user', password: 'pass' }
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      text: () => Promise.resolve('{"result": "success"}')
    } as any);

    const client = new HTTPClient(config);
    await client.makeRequest('/test');

    const expectedAuth = Buffer.from('user:pass').toString('base64');
    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/test',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': `Basic ${expectedAuth}`
        })
      })
    );
  });

  it('sends Accept: application/json by default', async () => {
    const config = {
      baseUrl: 'https://api.example.com',
      auth: { type: 'apikey' as const, header: 'Authorization', apiKey: 'k' }
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      text: () => Promise.resolve('{"ok":true}')
    } as any);

    const client = new HTTPClient(config);
    await client.makeRequest('/attributes/add/1', 'POST', { body: { type: 'ip-dst' } });

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/attributes/add/1',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Accept': 'application/json'
        })
      })
    );
  });

  it('lets a per-call header override the default Accept', async () => {
    const config = {
      baseUrl: 'https://api.example.com',
      auth: { type: 'apikey' as const, header: 'Authorization', apiKey: 'k' }
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      text: () => Promise.resolve('ok')
    } as any);

    const client = new HTTPClient(config);
    await client.makeRequest('/raw', 'GET', { headers: { 'Accept': 'text/plain' } });

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/raw',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Accept': 'text/plain'
        })
      })
    );
  });

  it('builds bearer auth headers correctly', async () => {
    const config = {
      baseUrl: 'https://api.example.com',
      auth: { type: 'bearer' as const, token: 'abc123' }
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      text: () => Promise.resolve('{"result": "success"}')
    } as any);

    const client = new HTTPClient(config);
    await client.makeRequest('/test');

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/test',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': 'Bearer abc123'
        })
      })
    );
  });

  it('handles query parameters', async () => {
    const config = {
      baseUrl: 'https://api.example.com',
      auth: { type: 'bearer' as const, token: 'abc123' }
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      text: () => Promise.resolve('{"result": "success"}')
    } as any);

    const client = new HTTPClient(config);
    await client.makeRequest('/search', 'GET', {
      params: { q: 'test', limit: 10 }
    });

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.example.com/search?q=test&limit=10',
      expect.any(Object)
    );
  });

  // An api_call endpoint or a predefined query URL may already carry a query
  // string; params must join it with `&` instead of opening a second `?`.
  it.each([
    {
      name: 'joins params onto an existing query string',
      endpoint: '/_search?size=1',
      params: { q: 'agent.name:kali' },
      expected: 'https://api.example.com/_search?size=1&q=agent.name%3Akali',
    },
    {
      name: 'keeps an existing key and appends the new value',
      endpoint: '/alerts?limit=5',
      params: { limit: 10, offset: 0 },
      expected: 'https://api.example.com/alerts?limit=5&limit=10&offset=0',
    },
    {
      name: 'keeps the endpoint query text as written',
      endpoint: '/_search?q=a%20b',
      params: { size: 1 },
      expected: 'https://api.example.com/_search?q=a%20b&size=1',
    },
    {
      name: 'treats a bare trailing ? as an empty query',
      endpoint: '/search?',
      params: { q: 'test' },
      expected: 'https://api.example.com/search?q=test',
    },
    {
      name: 'places params before a fragment',
      endpoint: '/search#top',
      params: { q: 'test' },
      expected: 'https://api.example.com/search?q=test#top',
    },
    {
      name: 'leaves the URL unchanged when every param is empty',
      endpoint: '/_search?size=1',
      params: { q: undefined, limit: null },
      expected: 'https://api.example.com/_search?size=1',
    },
  ])('$name', async ({ endpoint, params, expected }) => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      text: () => Promise.resolve('{"result": "success"}')
    } as any);

    const client = new HTTPClient({
      baseUrl: 'https://api.example.com',
      auth: { type: 'bearer' as const, token: 'abc123' }
    });
    await client.makeRequest(endpoint, 'GET', { params });

    expect(mockFetch).toHaveBeenCalledWith(expected, expect.any(Object));
  });

  it('throws error on HTTP failure', async () => {
    const config = {
      baseUrl: 'https://api.example.com',
      auth: { type: 'bearer' as const, token: 'abc123' }
    };

    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      text: () => Promise.resolve('{"error": "Not found"}')
    } as any);

    const client = new HTTPClient(config);

    await expect(client.makeRequest('/missing')).rejects.toThrow('HTTP 404: Not Found');
  });

  it('handles timeout', async () => {
    const config = {
      baseUrl: 'https://api.example.com',
      auth: { type: 'bearer' as const, token: 'abc123' },
      timeout: 100
    };

    mockFetch.mockImplementationOnce(() => {
      const controller = new AbortController();
      setTimeout(() => controller.abort(), 50);
      return Promise.reject(new DOMException('AbortError', 'AbortError'));
    });

    const client = new HTTPClient(config);

    const failure = client.makeRequest('/slow');
    await expect(failure).rejects.toThrow('Request timeout after 100ms');
    await expect(failure).rejects.toBeInstanceOf(HTTPTimeoutError);
  });
});
