import type { Workflow } from './types';

export type PlannedAction = {
  id: string;
  scope: string;
  type: string;
  label: string;
  detail: string;
  risk: 'read' | 'write' | 'external' | 'destructive';
};

export type ExecutionPlan = {
  actions: PlannedAction[];
  needsNetwork: boolean;
  needsDesktop: boolean;
  hasDestructiveActions: boolean;
};

export function canStartWithPlan(plan: ExecutionPlan, networkGranted: boolean, desktopGranted: boolean, destructiveConfirmed: boolean): boolean {
  return (!plan.needsNetwork || networkGranted) && (!plan.needsDesktop || desktopGranted) && (!plan.hasDestructiveActions || destructiveConfirmed);
}

const LABELS: Record<string, string> = {
  file_read_text: 'Read text file', file_write_text: 'Write text file', file_copy: 'Copy file',
  file_move: 'Move file', file_delete: 'Delete file', file_list: 'List files',
  csv_read: 'Read CSV', csv_write: 'Write CSV', xlsx_read: 'Read Excel workbook', pdf_read_text: 'Read PDF text', image_ocr: 'OCR image (local Tesseract)', sqlite_query: 'Query SQLite database',
  xlsx_write: 'Write Excel workbook', json_parse: 'Parse JSON', json_write: 'Write JSON',
  http_request: 'Send HTTP request', http_paginate: 'Read paginated API data', api_request: 'Call a saved API connection', browser_navigate: 'Open browser page', browser_goto: 'Open browser page',
  browser_click: 'Click browser control', browser_hover: 'Hover browser control', browser_press: 'Press browser key', browser_upload: 'Upload files through browser', browser_download: 'Download file through browser', browser_fill: 'Fill browser control', browser_select: 'Select browser option', browser_select_many: 'Select multiple browser options',
  browser_check: 'Change browser checkbox', browser_uncheck: 'Change browser checkbox', browser_wait: 'Wait for browser control', browser_wait_response: 'Wait for browser response',
  browser_assert: 'Check browser page', browser_text: 'Read browser text', browser_accessibility_snapshot: 'Read accessibility snapshot', browser_extract_records: 'Extract repeated web items', browser_table_read: 'Read web table', browser_scroll: 'Scroll web page', browser_record: 'Record browser actions',
  browser_launch: 'Launch browser', browser_new_tab: 'Open browser tab', browser_capture_popup: 'Capture browser popup', browser_switch_tab: 'Switch browser tab', browser_close_tab: 'Close browser tab', browser_screenshot: 'Capture browser screenshot', browser_close: 'Close browser',
  desktop_ui_click: 'Click desktop control', desktop_ui_scroll_into_view: 'Scroll desktop control into view', desktop_ui_drag: 'Drag desktop control', desktop_ui_grid_read: 'Read desktop data grid', desktop_ui_set_range_value: 'Set desktop slider or spinner', desktop_ui_invoke: 'Invoke desktop control', desktop_ui_press: 'Press key on desktop control', desktop_ui_fill: 'Set desktop text', desktop_ui_text: 'Read desktop text',
  desktop_ocr_click: 'Click exact OCR text in desktop window',
  desktop_ui_wait: 'Wait for desktop control', desktop_click: 'Click screen coordinates', desktop_type: 'Type into desktop app',
  desktop_ui_select: 'Select desktop option', desktop_ui_select_many: 'Set desktop list selection', desktop_ui_check: 'Check desktop control', desktop_ui_uncheck: 'Uncheck desktop control', desktop_ui_expand: 'Expand desktop tree item', desktop_ui_collapse: 'Collapse desktop tree item',
  desktop_window_wait: 'Wait for desktop window', desktop_window_activate: 'Activate desktop window', desktop_window_minimize: 'Minimize desktop window', desktop_window_restore: 'Restore desktop window', desktop_window_close: 'Close desktop window',
  desktop_launch_app: 'Launch desktop application',
  desktop_hotkey: 'Press desktop hotkey', desktop_press: 'Press desktop key', desktop_screenshot: 'Capture desktop screenshot',
  credential_get: 'Read saved credential', invoke_workflow: 'Call reusable workflow',
};

const FILE_READ = new Set(['file_read_text', 'file_list', 'csv_read', 'xlsx_read', 'pdf_read_text', 'image_ocr', 'sqlite_query']);
const FILE_WRITE = new Set(['file_write_text', 'file_copy', 'csv_write', 'xlsx_write', 'json_write', 'desktop_screenshot', 'browser_screenshot']);
const DESTRUCTIVE = new Set(['file_delete', 'file_move', 'desktop_window_close']);

function allActivities(workflow: Workflow): Record<string, unknown>[] {
  const found: Record<string, unknown>[] = [];
  const walk = (items: unknown) => {
    if (!Array.isArray(items)) return;
    for (const raw of items) {
      if (!raw || typeof raw !== 'object') continue;
      const item = raw as Record<string, unknown>;
      found.push(item);
      for (const key of ['body', 'then', 'else', 'default', 'catch', 'finally']) walk(item[key]);
      if (Array.isArray(item.cases)) for (const branch of item.cases) walk((branch as Record<string, unknown>)?.activities);
      if (Array.isArray(item.catches)) for (const branch of item.catches) walk((branch as Record<string, unknown>)?.activities);
    }
  };
  if (workflow.executionModel === 'flowchart') {
    for (const node of workflow.flowchart?.nodes ?? []) if (node.kind === 'action' && node.activity) walk([node.activity]);
  } else if (workflow.executionModel === 'state_machine') {
    for (const state of workflow.stateMachine?.states ?? []) walk(state.activities);
  } else walk(workflow.activities);
  return found;
}

function valueDetail(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return 'Path or target is configured at runtime';
  return value.length > 180 ? `${value.slice(0, 177)}…` : value;
}

export function buildExecutionPlan(workflow: Workflow, workflows: Record<string, Workflow> = {}, workflowName = workflow.name): ExecutionPlan {
  const actions: PlannedAction[] = [];
  const seen = new Set<string>();
  const visit = (current: Workflow, currentName: string, scopePath: string[], ancestorWorkflows: Set<string>) => {
    for (const item of allActivities(current)) {
    const type = typeof item.type === 'string' ? item.type : 'unknown';
    const id = typeof item.id === 'string' ? item.id : type;
    const scope = scopePath.join(' › ');
    const uniqueId = `${scope}\u0000${id}`;
    if (seen.has(uniqueId)) continue;
    seen.add(uniqueId);
    if (type === 'invoke_workflow') {
      const target = typeof item.workflow === 'string' ? item.workflow : '';
      const child = workflows[target];
      if (child && !ancestorWorkflows.has(target)) visit(child, target, [...scopePath, `${currentName}.${id}`, target], new Set([...ancestorWorkflows, target]));
      else actions.push({ id, scope, type, label: LABELS[type], detail: `Child workflow ${target || '(not specified)'} ${child ? 'contains a recursive call' : 'could not be inspected'}`, risk: 'external' });
      continue;
    }
    if (type === 'assign' || type === 'log' || type === 'if' || type === 'for_each' || type === 'while' || type === 'switch' || type === 'retry' || type === 'try' || type === 'wait' || type === 'json_parse' || type === 'transform_field' || type === 'filter_rows' || type === 'join_rows' || type === 'group_rows' || type === 'sort_rows' || type === 'map_rows' || type === 'distinct_rows' || type === 'validate_rows' || type === 'regex_replace' || type === 'regex_match') continue;
    const path = item.path ?? item.directory;
    const source = item.source;
    const destination = item.destination;
    const url = item.url ?? item.endpoint;
    const isBrowser = type.startsWith('browser_');
    const isDesktop = type.startsWith('desktop_');
    let risk: PlannedAction['risk'] = 'read';
    let detail = 'No external effect identified';
    if (DESTRUCTIVE.has(type)) { risk = 'destructive'; detail = type === 'file_move' ? `${valueDetail(source)} → ${valueDetail(destination)}` : type === 'desktop_window_close' ? `Close window ${valueDetail(item.windowTitle)}${item.processId?` (PID ${item.processId})`:''}` : valueDetail(path); }
    else if (FILE_WRITE.has(type)) { risk = 'write'; detail = type === 'file_copy' ? `${valueDetail(source)} → ${valueDetail(destination)}` : valueDetail(path); }
    else if (FILE_READ.has(type)) { risk = 'read'; detail = valueDetail(path); }
    else if (type === 'api_request') { const method=String(item.method??'GET').toUpperCase(); risk = method==='DELETE'?'destructive':'external'; detail = `${method} ${valueDetail(item.connectionId)} ${valueDetail(item.path)}${method==='DELETE'?' · removes remote data':''}`; }
    else if (type === 'http_request' || type === 'http_paginate') { risk = 'external'; detail = `${type === 'http_paginate' ? 'GET (bounded pagination)' : String(item.method ?? 'GET').toUpperCase()} ${valueDetail(url)}`; }
    else if (isBrowser) { risk = type === 'browser_text' || type === 'browser_accessibility_snapshot' || type === 'browser_extract_records' || type === 'browser_table_read' || type === 'browser_wait' || type === 'browser_assert' || type === 'browser_wait_response' ? 'read' : 'external'; detail = type === 'browser_navigate' || type === 'browser_goto' ? valueDetail(url) : 'Interacts with the active browser page'; }
    else if (isDesktop) { risk = type.includes('click') || type.includes('invoke') || type.includes('fill') || type.includes('select') || type.includes('check') || type.includes('expand') || type.includes('collapse') || type === 'desktop_type' || type === 'desktop_hotkey' || type === 'desktop_press' || type === 'desktop_launch_app' || type === 'desktop_window_activate' || type === 'desktop_window_minimize' || type === 'desktop_window_restore' ? 'external' : 'read'; detail = typeof item.selector === 'string' ? item.selector : type.startsWith('desktop_window_') ? `Window ${valueDetail(item.windowTitle)}${item.processId?` (PID ${item.processId})`:''}` : type === 'desktop_screenshot' ? valueDetail(path) : 'Interacts with the selected desktop application'; }
    else if (type === 'credential_get') { risk = 'read'; detail = 'Reads a credential by OS-vault reference'; }
    else { risk = 'external'; detail = 'Review the activity configuration before running'; }
    actions.push({ id, scope, type, label: LABELS[type] ?? type.replaceAll('_', ' '), detail, risk });
    }
  };
  visit(workflow, workflowName, [workflowName], new Set([workflowName]));
  return {
    actions,
    needsNetwork: actions.some(action => action.type === 'http_request' || action.type === 'http_paginate' || action.type === 'api_request' || action.type === 'browser_navigate' || (action.type.startsWith('browser_') && !['browser_launch','browser_close','browser_close_tab','browser_screenshot'].includes(action.type)) || (action.type === 'invoke_workflow' && (action.detail.includes('could not be inspected') || action.detail.includes('recursive call')))),
    needsDesktop: actions.some(action => action.type.startsWith('desktop_') || (action.type === 'invoke_workflow' && (action.detail.includes('could not be inspected') || action.detail.includes('recursive call')))),
    hasDestructiveActions: actions.some(action => action.risk === 'destructive'),
  };
}
