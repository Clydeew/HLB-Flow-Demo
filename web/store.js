import {request,saveToken,token,money,esc,tag,toast} from './common.js';
const modal=document.querySelector('#login-modal');let currentOrder=sessionStorage.getItem('flow-order');
document.querySelector('#start').onclick=()=>{modal.showModal()};document.querySelector('#close-modal').onclick=()=>modal.close();
document.querySelector('#login-form').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('[type=submit]');button.disabled=true;try{
 const f=new FormData(e.target);const s=await request('/login',{method:'POST',body:{code:f.get('code'),role:'customer',persona:f.get('persona')}});saveToken(s.token);sessionStorage.setItem('flow-persona',f.get('persona'));
 const order=await request('/orders',{method:'POST',body:{sku:'phone'}});currentOrder=order.id;sessionStorage.setItem('flow-order',order.id);document.body.dataset.flowOrder=order.id;document.body.dataset.flowPersona=f.get('persona');modal.close();showOrder(order);window.open('/checkout?order='+encodeURIComponent(order.id),'flow-checkout','width=510,height=860');
 }catch(err){const box=document.querySelector('#login-error');box.textContent=err.message;box.classList.remove('hidden')}finally{button.disabled=false}};
function showOrder(o){document.body.dataset.flowOrder=o.id;const el=document.querySelector('#order-status');el.className='notice';el.innerHTML=`<div class="row between"><strong>${esc(o.id)}</strong>${tag(o.status)}</div><p class="small" style="margin-top:8px">${o.status==='CONFIRMED'?'Simulated payment complete. Your order is confirmed.':'Checkout created. Open the extension or continue in the web demo.'}</p><a class="btn" style="margin-top:12px" href="/checkout?order=${encodeURIComponent(o.id)}" target="flow-checkout">Open financing demo ↗</a>`;document.querySelector('#price').textContent=money(o.price_vnd)}
async function refresh(){if(!currentOrder||!token())return;try{const o=await request('/orders/'+currentOrder);showOrder(o)}catch{}}
refresh();setInterval(refresh,2500);
