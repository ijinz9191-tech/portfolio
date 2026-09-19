import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
const assets=new Map([['/',['index.html','text/html; charset=utf-8']],['/index.html',['index.html','text/html; charset=utf-8']],['/styles.css',['styles.css','text/css; charset=utf-8']]]);
export function server(){return createServer(async(req,res)=>{
 const headers={'Content-Security-Policy':"default-src 'none'; style-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'};
 if(!['GET','HEAD'].includes(req.method)){res.writeHead(405,{...headers,Allow:'GET, HEAD'});res.end();return;}
 const asset=assets.get(req.url);if(!asset){res.writeHead(404,headers);res.end('Not found');return;}
 try{const body=await readFile(new URL(asset[0],import.meta.url));res.writeHead(200,{...headers,'Content-Type':asset[1]});res.end(req.method==='HEAD'?undefined:body);}catch{res.writeHead(503,headers);res.end('Unavailable');}
});}
if(process.argv[1]===fileURLToPath(import.meta.url)){server().listen(4189,'127.0.0.1',()=>console.log('Portfolio preview: http://127.0.0.1:4189 (local only)'));}
