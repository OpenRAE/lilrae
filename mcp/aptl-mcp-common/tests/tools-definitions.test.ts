import { describe, it, expect } from 'vitest';
import Ajv2020 from 'ajv/dist/2020.js';
import { generateToolDefinitions } from '../src/tools/definitions.js';

describe('generateToolDefinitions', () => {
  const mockServerConfig = {
    toolPrefix: 'test',
    targetName: 'Test Container'
  };

  it('generates tools with correct names using toolPrefix', () => {
    const tools = generateToolDefinitions(mockServerConfig);

    expect(tools[0].name).toBe('test_info');
    expect(tools[1].name).toBe('test_run_command');
    expect(tools[2].name).toBe('test_interactive_session');
    expect(tools[3].name).toBe('test_background_session');
    expect(tools[4].name).toBe('test_session_command');
    expect(tools[5].name).toBe('test_list_sessions');
    expect(tools[6].name).toBe('test_close_session');
    expect(tools[7].name).toBe('test_get_session_output');
    expect(tools[8].name).toBe('test_close_all_sessions');
  });

  it('generates descriptions using targetName', () => {
    const tools = generateToolDefinitions(mockServerConfig);

    expect(tools[0].description).toContain('Test Container');
    expect(tools[1].description).toContain('Test Container');
  });

  it('generates expected number of tools', () => {
    const tools = generateToolDefinitions(mockServerConfig);
    expect(tools).toHaveLength(9);
  });

  it('works with different server configs', () => {
    const kaliConfig = {
      toolPrefix: 'kali',
      targetName: 'Kali Linux'
    };

    const tools = generateToolDefinitions(kaliConfig);

    expect(tools[0].name).toBe('kali_info');
    expect(tools[1].name).toBe('kali_run_command');
    expect(tools[0].description).toContain('Kali Linux');
  });

  it('handles empty toolPrefix', () => {
    const emptyConfig = {
      toolPrefix: '',
      targetName: 'Test Container'
    };

    const tools = generateToolDefinitions(emptyConfig);
    expect(tools[0].name).toBe('_info');
    expect(tools[1].name).toBe('_run_command');
  });

  it('handles empty targetName', () => {
    const emptyConfig = {
      toolPrefix: 'test',
      targetName: ''
    };

    const tools = generateToolDefinitions(emptyConfig);
    expect(tools[0].description).toContain(' instance in the lab');
    expect(tools[1].description).toContain(' instance (creates temporary session)');
  });

  it('all tools have required properties', () => {
    const tools = generateToolDefinitions(mockServerConfig);

    tools.forEach(tool => {
      expect(tool.name).toBeDefined();
      expect(tool.description).toBeDefined();
      expect(tool.inputSchema).toBeDefined();
      expect(tool.inputSchema.type).toBe('object');
    });
  });

  // Node timers run only for 1 to 2^31-1 ms and fire after 1 ms otherwise, and
  // a line count below 1 would return the whole buffer or drop its oldest lines.
  it.each([
    ['test_interactive_session', 'timeout_ms', [1, 2_147_483_647], [0, -1, 2_147_483_648]],
    ['test_background_session', 'timeout_ms', [1, 2_147_483_647], [0, -1, 2_147_483_648]],
    ['test_session_command', 'timeout', [1, 2_147_483_647], [0, -1, 2_147_483_648]],
    ['test_get_session_output', 'lines', [1, 10_000], [0, -1]],
  ])('bounds %s %s to what the backend honors', (toolName, field, accepted, rejected) => {
    const tool = generateToolDefinitions(mockServerConfig).find(({ name }) => name === toolName);
    const validate = new Ajv2020().compile(tool!.inputSchema.properties![field]);

    expect(accepted.filter((value) => !validate(value))).toEqual([]);
    expect(rejected.filter((value) => validate(value))).toEqual([]);
  });
});
