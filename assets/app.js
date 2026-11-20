(function(){var q=document.getElementById('busca');if(!q)return;var items=[].slice.call(document.querySelectorAll('[data-busca]'));
var none=document.getElementById('sem-resultado');
function n(s){return (s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();}
q.addEventListener('input',function(){var v=n(q.value.trim()),c=0;items.forEach(function(el){var ok=!v||n(el.getAttribute('data-busca')).indexOf(v)>=0;el.style.display=ok?'':'none';if(ok)c++;});if(none)none.style.display=c?'none':'';});})();