export const LAST_PROJECT_KEY = 'openrpa.last-project-root.v1';

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export function readLastProject(storage: StorageLike): string {
  try { return storage.getItem(LAST_PROJECT_KEY)?.trim() ?? ''; }
  catch { return ''; }
}

export function rememberProject(storage: StorageLike, root: string): void {
  try {
    if (root.trim()) storage.setItem(LAST_PROJECT_KEY, root.trim());
    else storage.removeItem(LAST_PROJECT_KEY);
  } catch { /* Project opening and saving must work if browser storage is unavailable. */ }
}
