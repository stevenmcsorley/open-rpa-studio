import type { Activity, Flowchart, FlowNode, FlowTransition } from './types';

/** Insert an activity on the selected node's path without invalidating the graph. */
export function insertFlowchartAction(graph: Flowchart, selectedId: string, activity: Activity, label: string): Flowchart {
  const selected = graph.nodes.find(node => node.id === selectedId || node.activity?.id === selectedId);
  if (!selected) throw new Error('Select a flowchart node before adding an activity.');
  if (selected.kind === 'end' && selected.id === graph.start) throw new Error('The selected End node cannot also be the graph start.');

  const id = `node-${activity.id}`;
  if (graph.nodes.some(node => node.id === id || node.activity?.id === activity.id)) throw new Error('An activity with this id already exists in the flowchart.');
  const node: FlowNode = {
    id, kind: 'action', label, activity,
    x: selected.kind === 'end' ? Math.max(0, (selected.x ?? 360) - 330) : (selected.x ?? 40) + 330,
    y: selected.kind === 'end' ? Math.max(0, (selected.y ?? 210) - 10) : selected.y ?? 40,
  };

  let transitions: FlowTransition[];
  if (selected.kind === 'end') {
    const incoming = graph.transitions.filter(edge => edge.to === selected.id);
    if (!incoming.length) throw new Error('The selected End node has no incoming connection.');
    transitions = graph.transitions.map(edge => edge.to === selected.id ? { ...edge, to: id } : edge);
    transitions.push({ from: id, to: selected.id, when: 'always' });
  } else {
    const when = selected.kind === 'decision' ? 'true' : 'always';
    const existing = graph.transitions.find(edge => edge.from === selected.id && (edge.when ?? 'always') === when);
    if (!existing) throw new Error(selected.kind === 'decision'
      ? 'The selected Decision node has no True connection to insert into.'
      : 'The selected node has no outgoing connection to insert into.');
    transitions = graph.transitions.map(edge => edge === existing ? { ...edge, to: id } : edge);
    transitions.push({ from: id, to: existing.to, when: 'always' });
  }
  return { ...graph, nodes: [...graph.nodes, node], transitions };
}

/** Replace or remove one outgoing transition while preserving graph node identities. */
export function reconnectFlowchartTransition(graph: Flowchart, from: string, when: 'always'|'true'|'false', to: string|null): Flowchart {
  const source=graph.nodes.find(node=>node.id===from);
  if(!source)throw new Error(`Unknown flowchart source node: ${from}`);
  if(source.kind==='end')throw new Error('End nodes cannot have outgoing transitions.');
  if((source.kind==='decision'&&when==='always')||(source.kind!=='decision'&&when!=='always'))throw new Error(`${source.kind==='decision'?'Decision':'Non-decision'} nodes need a compatible transition branch.`);
  if(to!==null){
    const target=graph.nodes.find(node=>node.id===to);
    if(!target)throw new Error(`Unknown flowchart destination node: ${to}`);
    if(target.kind==='start')throw new Error('Transitions cannot target the Start node.');
  }
  const transitions=graph.transitions.filter(edge=>!(edge.from===from&&(edge.when??'always')===when));
  if(to!==null)transitions.push({from,to,when});
  return{...graph,transitions};
}
