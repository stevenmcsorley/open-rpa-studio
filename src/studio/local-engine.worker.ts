/// <reference lib="webworker" />
import type { Project, Workflow } from './types';
import { validate, validateBindings, run } from './webEngine';
const files = new Map<string, string>();
let opened:{project:Project;root:string;workflows:Record<string,Workflow>}|undefined;
self.onmessage=async({data}:{data:{id:number;method:string;params:any}})=>{
  const {id,method,params}=data;
  try {
    let result:any;
    if(method==='project.create'){
      const root=params.path;const project:Project={format:'openrpa.project',formatVersion:1,name:params.name,main:'Main',workflows:{Main:'workflows/main.workflow.json'}};
      const workflow:Workflow={format:'openrpa.workflow',formatVersion:1,name:'Main',variables:[],arguments:[],activities:[]};files.set(`${root}/project.json`,JSON.stringify(project,null,2));files.set(`${root}/${project.workflows.Main}`,JSON.stringify(workflow,null,2));opened={project,root,workflows:{Main:workflow}};result=opened;
    } else if(method==='project.open'){
      const raw=files.get(params.path);if(!raw)throw Error('This browser preview has no filesystem access. Run the desktop application to open a saved project.');const project=JSON.parse(raw);const root=params.path.substring(0,params.path.lastIndexOf('/'));const workflows:any={};for(const [name,rel]of Object.entries(project.workflows))workflows[name]=JSON.parse(files.get(`${root}/${rel}`)||'{}');opened={project,root,workflows};result=opened;
    } else if(method==='project.save'){
      const {root,project,workflows}=params;files.set(`${root}/project.json`,JSON.stringify(project,null,2));for(const [name,wf]of Object.entries(workflows as Record<string,Workflow>))files.set(`${root}/${project.workflows[name]}`,JSON.stringify(wf,null,2));result={saved:true};
    } else if(method==='workflow.validate'){const problems=[...validate(params.workflow),...validateBindings(params.workflows??opened?.workflows??{},params.workflowName??params.workflow.name)];result={valid:problems.length===0,problems};}
    else if(method==='workflow.run'){const name=params.workflow;const wf=opened?.workflows[name]??params.project.workflows[name];result=await run(wf,params.allowNetwork,e=>self.postMessage({event:'run.event',data:e}),opened?.workflows,name);}
    else if(method==='workflow.cancel')result={cancelled:false};
    else if(method==='activity.catalog')result=CATALOG;
    else throw Error(`Unknown bridge method: ${method}`);
    self.postMessage({id,result});
  }catch(e){self.postMessage({id,error:{message:e instanceof Error?e.message:String(e)}});}
};
const CATALOG=[
  ['assign','Assign','Variables','Assign a variable value.','target','result','value',''],['log','Log Message','Workflow','Write a structured execution log.','level','info','message',''],['invoke_workflow','Invoke Workflow','Workflow','Call a reusable workflow with declared argument mappings.','workflow','Main','inputs',{},'outputs',{}],['if','If','Control Flow','Branch based on a condition.','condition','True','then',[]],['for_each','For Each','Control Flow','Repeat an activity for each item.','items','[]','itemName','item'],['while','While','Control Flow','Repeat while a safe boolean condition stays true.','condition','False','body',[]],['retry','Retry Scope','Reliability','Retry selected errors with backoff and explicit repeat-safety acknowledgement.','maxAttempts',3,'retryOn',['http-timeout'],'delaySeconds',1,'backoffFactor',2,'repeatSafe',false,'body',[]],['switch','Switch','Control Flow','Route a value to the first matching case or the default branch.','expression','value','cases',[{value:'Approved',activities:[]}],'default',[]],['file_read_text','Read Text File','Files','Read a text file.','path','input.txt','result','text'],['file_write_text','Write Text File','Files','Write a text file.','path','output.txt','text',''],['csv_read','Read CSV','Data','Read CSV rows.','path','input.csv','result','rows'],['csv_write','Write CSV','Data','Write rows as CSV.','path','output.csv','rows','rows'],['sqlite_query','Query SQLite Database','Data','Read a local SQLite database using a bounded read-only query.','path','data.sqlite','query','SELECT * FROM records LIMIT 100','parameters',[],'result','rows','maxRows',10000,'timeoutSeconds',30],['xlsx_read','Read Excel Workbook','Data','Read an .xlsx worksheet as records.','path','input.xlsx','sheetName','Sheet1','headerRow',1,'dataOnly',true,'result','rows'],['xlsx_write','Write Excel Workbook','Data','Write records to a new .xlsx workbook.','path','output.xlsx','sheetName','Sheet1','rows','rows'],['transform_field','Transform Field','Data','Trim, change case, or replace a record field.','rows','rows','field','name','operation','trim','result','rows'],['json_parse','Parse JSON','Data','Parse a JSON value.','text','{}','result','data'],['json_write','Write JSON','Data','Serialize a value as JSON.','value','data','path','output.json'],['regex_replace','Regex Replace','Text','Replace matching text.','pattern','','replacement','','result','text'],['wait','Wait','Workflow','Wait a bounded number of seconds.','seconds',1,''],
].map((r:any)=>{const [type,title,category,description,...fields]=r;const defaults:any={};for(let i=0;i<fields.length;i+=2)defaults[fields[i]]=fields[i+1];return{type,title,category,description,defaults};});
