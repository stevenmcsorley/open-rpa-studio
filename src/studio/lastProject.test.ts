import { describe, expect, it } from 'vitest';
import { LAST_PROJECT_KEY, readLastProject, rememberProject } from './lastProject';

function memoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, String(value)); },
    removeItem: key => { values.delete(key); },
    clear: () => values.clear(),
    key: index => [...values.keys()][index] ?? null,
    get length() { return values.size; },
  };
}

describe('last opened project', () => {
  it('remembers and reads a project root', () => {
    const storage = memoryStorage();
    rememberProject(storage, ' C:/Automation/Project ');
    expect(readLastProject(storage)).toBe('C:/Automation/Project');
    expect(storage.getItem(LAST_PROJECT_KEY)).toBe('C:/Automation/Project');
  });

  it('clears the stored root when no project is open', () => {
    const storage = memoryStorage();
    rememberProject(storage, 'C:/Automation/Project');
    rememberProject(storage, ' ');
    expect(readLastProject(storage)).toBe('');
  });

  it('tolerates unavailable browser storage', () => {
    const storage = { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); }, removeItem: () => { throw new Error('blocked'); } } as unknown as Storage;
    expect(readLastProject(storage)).toBe('');
    expect(() => rememberProject(storage, 'C:/Automation/Project')).not.toThrow();
  });
});
