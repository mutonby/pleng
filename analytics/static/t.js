// Pleng Analytics — <1KB tracking
(function(){
  if(localStorage.getItem("pleng_optout"))return;
  var s=document.currentScript,d=s&&s.getAttribute("data-domain"),
      u=s&&s.getAttribute("data-api")||"/api/collect";
  if(!d)return;
  function t(){
    fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({d:d,p:location.pathname,r:document.referrer}),
    keepalive:true}).catch(function(){});
  }
  t();
  var h=history.pushState;
  history.pushState=function(){h.apply(this,arguments);t()};
  window.addEventListener("popstate",t);
})();
