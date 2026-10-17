self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET'||e.request.url.includes('/api/'))return;
  e.respondWith(fetch(e.request).then(r=>{const c=r.clone();caches.open('katia1').then(x=>x.put(e.request,c));return r}).catch(()=>caches.match(e.request)));
});
