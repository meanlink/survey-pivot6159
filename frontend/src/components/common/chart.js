import {esc} from '../../utils/dom.js';
export function chart(c){
 if(!c?.series?.length)return '<p class="empty">该分析未提供可绘制数据。</p>';
 const width=900,height=245,left=65,top=25,pw=800,ph=175;
 const series=c.series.slice(0,4),labels=c.labels||[],n=Math.max(...series.map(s=>s.values.length),1);
 // null 表示缺测无法计算：不参与量纲计算，绘图时跳过，避免被误读为零。
 const values=series.flatMap(s=>s.values).filter(v=>v!==null&&v!==undefined&&Number.isFinite(Number(v))).map(Number),low=Math.min(0,...values),high=Math.max(...values,1),span=high-low||1;
 const y=v=>top+ph-(Number(v)-low)/span*ph,x=i=>left+(i+.5)*pw/n;
 let svg='';for(let i=0;i<=4;i++){let v=low+span*i/4;svg+='<line x1="'+left+'" y1="'+y(v)+'" x2="'+(left+pw)+'" y2="'+y(v)+'" class="grid"/><text x="'+(left-10)+'" y="'+(y(v)+4)+'" text-anchor="end">'+esc(v.toFixed(Math.abs(v)>100?0:2))+'</text>';}
 series.forEach((s,j)=>{
   if(c.type==='bar')s.values.forEach((v,i)=>{if(v===null||v===undefined||!Number.isFinite(Number(v)))return;let w=pw/n/(series.length+1);svg+='<rect class="series s'+j+'" x="'+(x(i)-pw/n*.4+j*w)+'" y="'+Math.min(y(v),y(0))+'" width="'+Math.max(1,w-2)+'" height="'+Math.max(1,Math.abs(y(v)-y(0)))+'"><title>'+esc(labels[i])+' · '+esc(s.name)+': 缺测无法计算</title></rect>';});
   else if(c.type==='scatter')s.values.forEach((v,i)=>{if(v===null||v===undefined||!Number.isFinite(Number(v)))return;svg+='<circle class="series s'+j+'" cx="'+x(i)+'" cy="'+y(v)+'" r="3"><title>'+esc(labels[i])+': 缺测无法计算</title></circle>';});
   else svg+='<polyline class="line s'+j+'" points="'+s.values.map((v,i)=>v===null||v===undefined||!Number.isFinite(Number(v))?null:x(i)+','+y(v)).filter(Boolean).join(' ')+'"/>';
 });
 labels.forEach((label,i)=>{if(i%Math.max(1,Math.ceil(n/10))===0)svg+='<text x="'+x(i)+'" y="'+(top+ph+25)+'" text-anchor="middle">'+esc(String(label).slice(0,12))+'</text>';});
 return '<div class="legend">'+series.map((s,i)=>'<span class="key k'+i+'">'+esc(s.name)+'</span>').join('')+'</div><svg class="chart" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="后端分析结果图">'+svg+'</svg>';
}
