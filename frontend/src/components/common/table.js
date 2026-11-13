import {esc,fmt} from '../../utils/dom.js';
export function table(columns,rows,empty='暂无记录。请先导入业务数据，再创建分析任务。'){
 if(!rows.length)return '<div class="empty">'+esc(empty)+'</div>';
 const cell=(r,c)=>{
   const v=r[c.key];
   if(v===null||v===undefined)return '<span class="cell-na">无法计算（缺测）</span>';
   return esc(fmt(v));
 };
 return '<div class="table-wrap"><table><thead><tr>'+columns.map(c=>'<th>'+esc(c.label)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr class="'+(r.status==='缺测'?'row-missing':'')+'">'+columns.map(c=>'<td>'+cell(r,c)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
}
