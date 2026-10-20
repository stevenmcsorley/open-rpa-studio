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
