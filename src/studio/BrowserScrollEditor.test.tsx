import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {describe,expect,it} from 'vitest';
import {BrowserScrollEditor} from './BrowserScrollEditor';

describe('browser scroll editor',()=>{
  it('explains page scrolling and gradual visible progress',()=>{
    const html=renderToStaticMarkup(createElement(BrowserScrollEditor,{activity:{id:'scroll',type:'browser_scroll',direction:'down',delayMilliseconds:700,toBottom:true,maxSteps:50},onChange:()=>{}}));
    expect(html).toContain('Whole page');
    expect(html).toContain('Continue until the target end');
    expect(html).toContain('Cancellation is checked between steps');
    expect(html).not.toContain('Container CSS selector');
  });

  it('exposes a bounded unique CSS selector for scrollable feeds',()=>{
    const html=renderToStaticMarkup(createElement(BrowserScrollEditor,{activity:{id:'scroll',type:'browser_scroll',containerSelector:'#product-feed',direction:'down'},onChange:()=>{}}));
    expect(html).toContain('Scrollable element');
    expect(html).toContain('Container CSS selector');
    expect(html).toContain('value="#product-feed"');
    expect(html).toContain('Must match exactly one visible element');
  });
});
