// No financial information is read from or injected into the merchant page.
chrome.storage.session.setAccessLevel({accessLevel:'TRUSTED_CONTEXTS'});
chrome.sidePanel.setPanelBehavior({openPanelOnActionClick:true});
chrome.action.onClicked.addListener(async tab=>{
  try{
    const url=new URL(tab.url||'');
    if(url.origin!=='http://127.0.0.1:8000'||url.pathname!=='/'){
      await chrome.storage.session.remove(['flowOrder','flowApplication']);return;
    }
    const result=await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>({order:document.body.dataset.flowOrder||null})});
    const order=result[0]?.result?.order;
    const old=await chrome.storage.session.get('flowOrder');
    if(order&&/^ORDER-[A-F0-9]{12}$/.test(order)){
      if(old.flowOrder!==order)await chrome.storage.session.remove('flowApplication');
      await chrome.storage.session.set({flowOrder:order});
    }else await chrome.storage.session.remove(['flowOrder','flowApplication']);
  }catch{await chrome.storage.session.remove(['flowOrder','flowApplication'])}
});
