
document.documentElement.classList.add('js');
const allPapers = [...document.querySelectorAll('.paper-card')];
const search = document.getElementById('paper-search');
const category = document.getElementById('paper-category');
function filterPapers(){
  const text = search.value.trim().toLocaleLowerCase();
  let count = 0;
  allPapers.forEach(card => {
    card.hidden = !((category.value === 'all' || category.value === card.dataset.group) && card.textContent.toLocaleLowerCase().includes(text));
    if(!card.hidden) count++;
  });
  document.getElementById('paper-count').textContent = count + ' / 12 篇';
  document.getElementById('paper-empty').hidden = count > 0;
}
search.addEventListener('input',filterPapers);
category.addEventListener('change',filterPapers);
document.getElementById('expand-all').addEventListener('click',()=>allPapers.filter(c=>!c.hidden).forEach(c=>c.querySelector('details').open=true));
document.getElementById('collapse-all').addEventListener('click',()=>allPapers.filter(c=>!c.hidden).forEach(c=>c.querySelector('details').open=false));
function revealHash(){
  if(!location.hash.startsWith('#paper-')) return;
  const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
  if(!target) return;
  search.value=''; category.value='all'; filterPapers();
  target.querySelector('details').open=true;
  requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));
}
window.addEventListener('hashchange',revealHash);
revealHash();
const chartData = JSON.parse(document.getElementById('chart-data').textContent);
const chartChoice = document.getElementById('chart-choice');
function drawChart(){
  const data=chartData[chartChoice.value];
  document.getElementById('chart-title').textContent=data.title;
  document.getElementById('chart-note').textContent=data.note;
  const plot=document.getElementById('comparison-chart');
  plot.replaceChildren();
  data.rows.forEach(r=>{
    const el=document.createElement('div');el.className='chart-row'+(r.id==='current'?' current':'');
    const name=document.createElement('span');name.className='chart-label';name.textContent=r.name;
    const track=document.createElement('div');track.className='chart-track';track.setAttribute('aria-hidden','true');
    const bar=document.createElement('div');bar.className='chart-bar'+(r.kind==='direct'?' direct':'');bar.style.width=(100*r.numerator/r.denominator)+'%';track.append(bar);
    const value=document.createElement('span');value.className='chart-score';value.textContent=r.numerator+'/'+r.denominator;
    value.title=(100*r.numerator/r.denominator).toFixed(1)+'%';
    el.append(name,track,value);plot.append(el);
  });
}
chartChoice.addEventListener('change',drawChart);drawChart();
let printState=[];
let printDetails=[];
window.addEventListener('beforeprint',()=>{
  printState=allPapers.map(c=>({hidden:c.hidden,open:c.querySelector('details').open}));
  printDetails=[...document.querySelectorAll('details')].map(el=>({el,open:el.open}));
  printDetails.forEach(item=>item.el.open=true);
  allPapers.forEach(c=>{c.hidden=false;c.querySelector('details').open=true;});
  document.getElementById('paper-empty').hidden=true;
});
window.addEventListener('afterprint',()=>{
  allPapers.forEach((c,i)=>{if(printState[i]){c.hidden=printState[i].hidden;c.querySelector('details').open=printState[i].open;}});
  printDetails.forEach(item=>item.el.open=item.open);
  filterPapers();
});
document.querySelectorAll('[data-print]').forEach(b=>b.addEventListener('click',()=>window.print()));
const sections=[...document.querySelectorAll('main > section[id]')];
if('IntersectionObserver' in window){
  const observer=new IntersectionObserver(entries=>{
    const visible=entries.filter(e=>e.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top);
    if(!visible.length)return;
    document.querySelectorAll('.rail nav a').forEach(a=>{if(a.getAttribute('href')==='#'+visible[0].target.id)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});
  },{rootMargin:'-5% 0px -70% 0px',threshold:0});sections.forEach(s=>observer.observe(s));
}
