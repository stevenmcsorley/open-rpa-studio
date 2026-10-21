import { describe, expect, it } from 'vitest';
import { buildExecutionPlan, canStartWithPlan } from './executionPlan';
import type { Workflow } from './types';

const base: Workflow = { format: 'openrpa.workflow', formatVersion: 1, name: 'Main', variables: [], arguments: [], activities: [] };

describe('run impact plan', () => {
  it('finds file, network and desktop actions nested under control flow', () => {
    const plan = buildExecutionPlan({ ...base, activities: [{ id: 'retry', type: 'retry', body: [
      { id: 'read', type: 'csv_read', path: 'data/orders.csv' },
      { id: 'send', type: 'http_request', method: 'POST', url: 'https://api.example.test/orders' },
      { id: 'click', type: 'desktop_ui_click', selector: 'Save' },
    ] }] });
    expect(plan.actions.map(action => action.id)).toEqual(['read', 'send', 'click']);
    expect(plan.needsNetwork).toBe(true);
    expect(plan.needsDesktop).toBe(true);
    expect(plan.actions[1].detail).toBe('POST https://api.example.test/orders');
  });

  it('labels deletes and moves as destructive and omits pure workflow logic', () => {
    const plan = buildExecutionPlan({ ...base, activities: [
      { id: 'assign', type: 'assign' }, { id: 'parse', type: 'json_parse' }, { id: 'delete', type: 'file_delete', path: 'output/old.csv' },
      { id: 'move', type: 'file_move', source: 'in.csv', destination: 'archive/in.csv' },
    ] });
    expect(plan.actions).toHaveLength(2);
    expect(plan.actions[0]).toMatchObject({ risk: 'destructive', detail: 'output/old.csv' });
    expect(plan.actions[1]).toMatchObject({ risk: 'destructive', detail: 'in.csv → archive/in.csv' });
    expect(plan.hasDestructiveActions).toBe(true);
  });

  it('treats typed row filtering as local data logic without requesting permissions', () => {
    const plan=buildExecutionPlan({...base,activities:[{id:'filter',type:'filter_rows',rows:'orders',conditions:[{field:'status',operator:'equals',value:'open'}]}]});
    expect(plan).toMatchObject({needsNetwork:false,needsDesktop:false,hasDestructiveActions:false,actions:[]});
  });

  it('requires the file-read review for local OCR documents',()=>{
    const plan=buildExecutionPlan({...base,activities:[{id:'ocr',type:'image_ocr',path:'scans/invoice.png',language:'eng'}]});
    expect(plan.needsNetwork).toBe(false);expect(plan.needsDesktop).toBe(false);expect(plan.actions).toMatchObject([{id:'ocr',risk:'read',label:'OCR image (local Tesseract)',detail:'scans/invoice.png'}]);
  });

  it('treats bounded row joins as local data logic without requesting permissions',()=>{
    const plan=buildExecutionPlan({...base,activities:[{id:'join',type:'join_rows',left:'orders',right:'buyers',leftKey:'buyerId',rightKey:'id'}]});
    expect(plan).toMatchObject({needsNetwork:false,needsDesktop:false,hasDestructiveActions:false,actions:[]});
  });

  it('treats row grouping as local data logic without requesting permissions',()=>{
    const plan=buildExecutionPlan({...base,activities:[{id:'group',type:'group_rows',rows:'orders',groupBy:['department'],aggregations:[{operation:'count_rows',as:'records'}]}]});
    expect(plan).toMatchObject({needsNetwork:false,needsDesktop:false,hasDestructiveActions:false,actions:[]});
  });

  it('treats row sorting as local data logic without requesting permissions',()=>{
    const plan=buildExecutionPlan({...base,activities:[{id:'sort',type:'sort_rows',rows:'orders',keys:[{field:'date',direction:'ascending'}]}]});
    expect(plan).toMatchObject({needsNetwork:false,needsDesktop:false,hasDestructiveActions:false,actions:[]});
  });

  it('reports copy and screenshot output paths as writes while keeping desktop permission visible', () => {
    const plan = buildExecutionPlan({ ...base, activities: [
      { id: 'copy', type: 'file_copy', source: 'in.csv', destination: 'out.csv' },
      { id: 'screen', type: 'desktop_screenshot', path: 'evidence/screen.png' },
      { id: 'web-screen', type: 'browser_screenshot', path: 'evidence/page.png' },
      { id: 'type', type: 'desktop_type', text: 'sample' },
    ] });
    expect(plan.actions.map(action => action.detail)).toEqual(['in.csv → out.csv', 'evidence/screen.png', 'evidence/page.png', 'Interacts with the selected desktop application']);
    expect(plan.actions.map(action => action.risk)).toEqual(['write', 'write', 'write', 'external']);
    expect(plan.needsNetwork).toBe(false);
    expect(plan.needsDesktop).toBe(true);
  });

  it('shows PDF extraction as a file read in the pre-run impact plan', () => {
    const plan = buildExecutionPlan({ ...base, activities: [{ id: 'pdf', type: 'pdf_read_text', path: 'invoices/current.pdf' }] });
    expect(plan.actions).toEqual([expect.objectContaining({ id: 'pdf', label: 'Read PDF text', detail: 'invoices/current.pdf', risk: 'read' })]);
  });

  it('shows SQLite queries as bounded local database reads', () => {
    const plan = buildExecutionPlan({ ...base, activities: [{ id: 'query', type: 'sqlite_query', path: 'data/orders.sqlite', query: 'SELECT * FROM orders' }] });
    expect(plan.actions).toEqual([expect.objectContaining({ id: 'query', label: 'Query SQLite database', detail: 'data/orders.sqlite', risk: 'read' })]);
    expect(plan.needsNetwork).toBe(false);
  });

  it('shows reading a browser table as a bounded page-data read', () => {
    const plan = buildExecutionPlan({ ...base, activities: [{ id: 'table', type: 'browser_table_read', selectorKind: 'css', selector: '#results', maxRows: 50, maxColumns: 10 }] });
    expect(plan.actions).toEqual([expect.objectContaining({ id: 'table', label: 'Read web table', risk: 'read' })]);
  });

  it('covers flowchart nodes and state-machine activities', () => {
    const flowchart = buildExecutionPlan({ ...base, executionModel: 'flowchart', flowchart: {
      start: 's', nodes: [{ id: 's', kind: 'start' }, { id: 'a', kind: 'action', activity: { id: 'web', type: 'browser_navigate', url: 'https://example.org' } }, { id: 'e', kind: 'end' }],
      transitions: [{ from: 's', to: 'a' }, { from: 'a', to: 'e' }],
    } });
    expect(flowchart.needsNetwork).toBe(true);
    expect(flowchart.actions[0].detail).toBe('https://example.org');
    const machine = buildExecutionPlan({ ...base, executionModel: 'state_machine', stateMachine: {
      initial: 'start', states: [{ id: 'start', label: 'Start', activities: [{ id: 'write', type: 'xlsx_write', path: 'out.xlsx' }], final: true }], transitions: [],
    } });
    expect(machine.actions[0]).toMatchObject({ risk: 'write', detail: 'out.xlsx' });
  });

  it('recursively lists child workflow operations and requests fail-safe grants for missing children', () => {
    const child: Workflow = { ...base, name: 'Child', activities: [{ id: 'remote', type: 'http_request', url: 'https://service.example/api' }] };
    const parent: Workflow = { ...base, activities: [{ id: 'invoke', type: 'invoke_workflow', workflow: 'Child' }] };
    const expanded = buildExecutionPlan(parent, { Main: parent, Child: child }, 'Main');
    expect(expanded.needsNetwork).toBe(true);
    expect(expanded.actions).toEqual([expect.objectContaining({ scope: 'Main › Main.invoke › Child', id: 'remote' })]);
    const unresolved = buildExecutionPlan(parent, { Main: parent }, 'Main');
    expect(unresolved.needsNetwork).toBe(true);
    expect(unresolved.needsDesktop).toBe(true);
    expect(unresolved.actions[0].detail).toContain('could not be inspected');
    const twice = buildExecutionPlan({ ...parent, activities: [
      { id: 'call-a', type: 'invoke_workflow', workflow: 'Child' },
      { id: 'call-b', type: 'invoke_workflow', workflow: 'Child' },
    ] }, { Main: parent, Child: child }, 'Main');
    expect(twice.actions).toHaveLength(2);
    expect(twice.actions[0].scope).not.toBe(twice.actions[1].scope);
  });

  it('requires per-run network, desktop and destructive confirmations independently', () => {
    const plan = buildExecutionPlan({ ...base, activities: [
      { id: 'web', type: 'browser_navigate', url: 'https://example.org' },
      { id: 'click', type: 'desktop_ui_click', selector: 'Submit' },
      { id: 'delete', type: 'file_delete', path: 'out.csv' },
    ] });
    expect(canStartWithPlan(plan, true, true, false)).toBe(false);
    expect(canStartWithPlan(plan, true, false, true)).toBe(false);
    expect(canStartWithPlan(plan, true, true, true)).toBe(true);
    const local = buildExecutionPlan({ ...base, activities: [{ id: 'write', type: 'file_write_text', path: 'out.txt' }] });
    expect(canStartWithPlan(local, false, false, false)).toBe(true);
  });
});
