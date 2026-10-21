import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { filterRunHistory, RunHistoryPanel } from './RunHistoryPanel';
import type { RunHistoryDetail, RunHistorySummary } from './bridge';

const interrupted:RunHistoryDetail={
  runId:'run-12345678',projectPath:'C:/private/project',projectName:'Invoice processing',workflow:'Main',workflowSha256:'a'.repeat(64),status:'interrupted',startedAt:'2026-10-20T10:00:00.000Z',endedAt:'2026-10-20T10:01:00.000Z',
  error:null,recoveryNote:'Application stopped before completion. External side effects are unknown; inspect them before manually restarting.',
  result:{status:'interrupted',activities:{'submit-1':{status:'running',type:'http_request'}}},
  events:[{event:'activity-started',activityId:'submit-1',type:'http_request',recordedAt:'2026-10-20T10:00:01.000Z'}],
};

describe('RunHistoryPanel',()=>{
  it('shows interruption uncertainty and inspection guidance without offering replay',()=>{
    const html=renderToStaticMarkup(createElement(RunHistoryPanel,{runs:[interrupted],selectedId:interrupted.runId,detail:interrupted,loading:false,onSelect:()=>undefined}));
    expect(html).toContain('Interrupted run');
    expect(html).toContain('External side effects may already have occurred');
    expect(html).toContain('Workflow SHA-256');
    expect(html).toContain('activity started');
    expect(html).not.toMatch(/resume|replay|restart run/i);
    expect(html).not.toContain('C:/private/project');
  });

  it('shows loading and empty selection states',()=>{
    const loading=renderToStaticMarkup(createElement(RunHistoryPanel,{runs:[],selectedId:'',detail:null,loading:true,onSelect:()=>undefined}));
    const empty=renderToStaticMarkup(createElement(RunHistoryPanel,{runs:[],selectedId:'',detail:null,loading:false,onSelect:()=>undefined}));
    expect(loading).toContain('Loading run record');
    expect(empty).toContain('No saved runs yet');
  });

  it('exposes accessible search and status controls',()=>{
    const html=renderToStaticMarkup(createElement(RunHistoryPanel,{runs:[interrupted],selectedId:'',detail:null,loading:false,onSelect:()=>undefined}));
    expect(html).toContain('aria-label="Search run history"');
    expect(html).toContain('aria-label="Filter run history by status"');
    expect(html).toContain('1 of 1 runs');
  });

  it('filters saved runs by status and searchable error evidence',()=>{
    const succeeded:RunHistorySummary={...interrupted,runId:'run-success-01',workflow:'Import',status:'succeeded',recoveryNote:null};
    const failed:RunHistorySummary={...interrupted,runId:'run-failed-01',workflow:'Export',status:'failed',error:{code:'file-permission-denied',message:'Blocked output path'},recoveryNote:null};
    const runs=[interrupted,succeeded,failed];
    expect(filterRunHistory(runs,'','failed').map(run=>run.runId)).toEqual(['run-failed-01']);
    expect(filterRunHistory(runs,'permission','all').map(run=>run.runId)).toEqual(['run-failed-01']);
    expect(filterRunHistory(runs,'run-123456','all').map(run=>run.runId)).toEqual([interrupted.runId]);
    expect(filterRunHistory(runs,'missing','all')).toEqual([]);
  });
});
