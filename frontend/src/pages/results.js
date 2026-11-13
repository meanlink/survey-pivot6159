import {jobs} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {chart} from '../components/common/chart.js';
import {table} from '../components/common/table.js';
import {status} from '../components/common/status.js';
import {esc,fmt,date,notify} from '../utils/dom.js';

const na='<span class="cell-na">无法计算</span>';
function num(v,unit=''){return (v===null||v===undefined)?na:esc(fmt(v))+(unit?'<small>'+esc(unit)+'</small>':'');}

function periodPanel(r){
 const changes=r.changes||[],reversals=r.layer_reversals||[],trace=r.traceability||{};
 const changeRows=changes.map(c=>'<tr><td>'+esc(c.team)+'</td><td>'+num(c.early_rate,'%')+'</td><td>'+num(c.late_rate,'%')+'</td><td>'+num(c.delta,c.delta===null?'':'百分点')+'</td><td>'+(c.direction?esc(c.direction):na)+'</td><td>'+(c.direction_reversal===null?na:(c.direction_reversal?'<span class="tag tag-warn">方向反转</span>':'未反转'))+'</td>'+(c.reason?'<td class="note-cell">'+esc(c.reason)+'</td>':'<td>—</td>')+'</tr>').join('');
 const reversalRows=reversals.map(x=>'<tr><td>'+esc(x.period)+'</td><td>'+(x.reversal===null?na:(x.reversal?'<span class="tag tag-warn">辛普森反转</span>':'未发现严格反转'))+'</td><td>'+(x.raw_delta===undefined?na:num(x.raw_delta,'百分点'))+'</td><td>'+(x.weighted_delta===undefined?na:num(x.weighted_delta,'百分点'))+'</td><td class="note-cell">'+esc(x.detail||('层内A−B（百分点）：'+x.layer_deltas.map(v=>fmt(v)).join(' / ')))+'</td></tr>').join('');
 const frameRows=(trace.frame_as_of||[]).map(f=>'<tr><td>'+esc(f.zone)+'</td><td>'+esc(fmt(f.frame_size))+'</td><td>'+esc(f.registered_day)+'</td><td>'+esc(fmt(f.weight_pct))+'%</td></tr>').join('');
 const missing=(trace.missingness||[]).map(m=>'<p class="warning">'+esc(m.period+m.team+' 缺测层：'+(m.missing_zones||[]).join('、'))+'。'+esc(m.reason||'缺测不当零、不改分母，相关比较无法计算')+'。</p>').join('');
 const win=trace.periods||{};
 return '<section class="panel period-panel"><div class="section-title"><h2>两期比较与方向反转</h2><span>统一权重 · 缺测标注</span></div>'
  +'<p class="hint">早期 '+esc(win.early?.start||'')+' 至 '+esc(win.early?.end||'')+' ｜ 后期 '+esc(win.late?.start||'')+' 至 '+esc(win.late?.end||'')+' ｜ '+esc(trace.frame_rule||'')+'</p>'
  +'<div class="table-wrap"><table><thead><tr><th>采样队</th><th>早期加权合格率</th><th>后期加权合格率</th><th>变化（后−早）</th><th>方向</th><th>跨期方向反转</th><th>无法计算说明</th></tr></thead><tbody>'+changeRows+'</tbody></table></div>'
  +'<h3 class="sub-title">每期辛普森方向反转（原始合计 vs 各层内方向）</h3><div class="table-wrap"><table><thead><tr><th>期段</th><th>结论</th><th>原始A−B</th><th>加权A−B</th><th>层内方向 / 说明</th></tr></thead><tbody>'+reversalRows+'</tbody></table></div>'
  +'<h3 class="sub-title">统一目标权重（后期结束前最后登记框规模）</h3><div class="table-wrap"><table><thead><tr><th>区域层</th><th>采用框规模</th><th>框规模登记日</th><th>统一权重</th></tr></thead><tbody>'+frameRows+'</tbody></table></div>'
  +(missing?'<h3 class="sub-title">缺测说明（不当零、不改分母）</h3>'+missing:'')
  +'<p class="hint snapshot-note">'+esc(trace.snapshot_note||'')+'</p></section>';
}

export async function results(id){
 workspace.jobs=await jobs.list();const j=id?await jobs.get(id):(workspace.jobs.find(j=>j.id===workspace.selectedJob)||workspace.jobs[0]);
 if(j&&!workspace.jobs.some(x=>x.id===j.id))workspace.jobs.push(j);
 if(!j)return heading('04 / REVIEW','结果复核','尚无分析结果。')+'<div class="empty">先到分析工作台，选择批次并提交一次计算。<a href="#/workbench">前往工作台 ↗</a></div>';
 workspace.selectedJob=j.id;const r=j.result||{};
 return heading('04 / REVIEW','结果复核与业务解释',j.name,'<button class="button" id="refresh-results">刷新结果 ↻</button>')+'<div class="result-selector"><label>分析记录<select id="select-job">'+workspace.jobs.map(x=>'<option value="'+x.id+'" '+(x.id===j.id?'selected':'')+'>'+esc(x.name)+' · '+esc(x.status)+'</option>').join('')+'</select></label>'+status(j.status)+'<span>'+date(j.created_at)+'</span><span class="approval">'+(j.approved?'已获业务批准':'待负责人复核')+'</span></div>'+(j.status==='completed'?'<section class="result-lead"><p class="eyebrow">COMPUTED FINDING</p><h2>'+esc(r.summary)+'</h2><div class="metrics">'+(r.metrics||[]).map(m=>'<div><span>'+esc(m.label)+'</span><strong>'+(m.value===null||m.value===undefined?'<span class="cell-na">无法计算</span>':esc(fmt(m.value)))+'<small>'+esc(m.unit||'')+'</small></strong></div>').join('')+'</div></section>'+(r.traceability?periodPanel(r):'')+'<section class="panel">'+chart(r.chart)+'</section><div class="two-columns"><section class="panel"><div class="section-title"><h2>业务解释</h2><span>由计算结果生成</span></div><ol class="questions">'+(r.findings||[]).map(v=>'<li>'+esc(v)+'</li>').join('')+'</ol>'+(r.notes||[]).map(v=>'<p class="warning">'+esc(v)+'</p>').join('')+(r.warnings||[]).map(v=>'<p class="warning">'+esc(v)+'</p>').join('')+'</section><section class="method-sheet compact"><p class="eyebrow">REPRODUCIBILITY</p><h3>计算口径与参数</h3><p>'+esc(r.method)+'</p><pre>'+esc(JSON.stringify(j.params,null,2))+'</pre>'+(session.user.role==='admin'&&!j.approved?'<button class="primary" id="approve-job">批准此业务结论</button>':'')+'<p class="hint">仅批准结果可进入定时分发档案。晚到记录请建立新批次重算，历史结果与附件保留原日期、原权重与原缺测说明。</p></section></div><section class="panel"><div class="section-title"><h2>结果明细（缺测层保留行并标注）</h2><span>'+(r.table?.rows?.length||0)+' 行</span></div>'+table(r.table?.columns||[],r.table?.rows||[])+'</section>':'<section class="panel empty">'+(j.status==='failed'?'计算失败：'+esc(j.error)+'。请返回工作台调整参数或数据。':'后台正在执行计算。点击刷新结果查看最新进展。')+'<a href="#/workbench">返回工作台 ↗</a></section>');
}
export function bindResults(refresh){document.querySelector('#refresh-results')?.addEventListener('click',refresh);document.querySelector('#select-job')?.addEventListener('change',e=>{workspace.selectedJob=Number(e.target.value);location.hash='#/results/'+e.target.value;});document.querySelector('#approve-job')?.addEventListener('click',async()=>{try{await jobs.approve(workspace.selectedJob);notify('已批准，可创建分发计划');await refresh();}catch(e){notify(e.message,true);}});}
