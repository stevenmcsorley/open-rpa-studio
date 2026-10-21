import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ValidateRowsEditor } from './ValidateRowsEditor';

describe('ValidateRowsEditor',()=>{
  it('shows typed rules, required flags and both result variables',()=>{
    const html=renderToStaticMarkup(createElement(ValidateRowsEditor,{activity:{id:'validate',type:'validate_rows',rows:'inputRows',rules:[{field:'email',type:'text',required:true,nonEmpty:true},{field:'age',type:'number',required:false,nonEmpty:false}],validResult:'accepted',invalidResult:'rejected',maxRows:9000},onChange:()=>undefined}));
    expect(html).toContain('FIELD RULES');expect(html).toContain('email');expect(html).toContain('number');expect(html).toContain('Required');expect(html).toContain('accepted');expect(html).toContain('rejected');expect(html).toContain('9000');
  });
});
