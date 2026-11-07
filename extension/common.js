export const API='http://127.0.0.1:8000';
export const money=n=>new Intl.NumberFormat('vi-VN',{style:'currency',currency:'VND',maximumFractionDigits:0}).format(n||0);
export const pct=n=>(100*(n||0)).toFixed(2)+'%';
export const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const readable=v=>String(v||'').replaceAll('_',' ').toLowerCase().replace(/^./,c=>c.toUpperCase());
export function token(role='customer'){return sessionStorage.getItem('flow-'+role)||''}
export function saveToken(value,role='customer'){sessionStorage.setItem('flow-'+role,value)}
export async function request(path,{method='GET',body,role='customer',key}={}){
 const headers={'Content-Type':'application/json'};if(token(role))headers.Authorization='Bearer '+token(role);if(key)headers['Idempotency-Key']=key;
 let response;try{response=await fetch(API+'/api'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)})}catch(e){throw new Error('Local server is unavailable. Run the setup script and try again.')}
 const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?readable(data.detail):'Please check the request fields.');return data;
}
export function toast(message){document.querySelector('.toast')?.remove();const el=document.createElement('div');el.className='toast';el.textContent=message;el.setAttribute('role','status');document.body.append(el);setTimeout(()=>el.remove(),5000)}
export function tag(status){let color=['APPROVED','CAPTURED','ACTIVE','CONFIRMED','RESOLVED'].includes(status)?'green':['DECLINED','BLOCKED','FAILED'].includes(status)?'red':['REFERRED','PENDING_DEPENDENCY','UNKNOWN','OPEN'].includes(status)?'amber':'blue';return `<span class="tag ${color}">${esc(readable(status))}</span>`}
export function kv(k,v){return `<div class="kv"><span>${esc(k)}</span><span class="number">${esc(v)}</span></div>`}
