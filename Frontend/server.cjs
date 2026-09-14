const http = require('http');
const fs = require('fs');
const path = require('path');
const DIST = path.join(__dirname, 'dist');
const BACKEND_HOST = process.env.BACKEND_HOST || 'localhost';
const BACKEND_PORT = parseInt(process.env.BACKEND_PORT || '8000', 10);
const PORT = parseInt(process.env.PORT || '3000', 10);
const mime = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif','.svg':'image/svg+xml','.ico':'image/x-icon','.woff':'font/woff','.woff2':'font/woff2'};
http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname.startsWith('/api')) {
    const headers = Object.assign({}, req.headers);
    delete headers['host'];
    const proxyReq = http.request({hostname: BACKEND_HOST, port: BACKEND_PORT, path: url.pathname + url.search, method: req.method, headers}, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res);
    });
    proxyReq.on('error', (e) => { res.writeHead(502); res.end('proxy error: ' + e.message); });
    req.pipe(proxyReq);
    return;
  }
  let filePath = path.join(DIST, decodeURIComponent(url.pathname));
  if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) filePath = path.join(DIST, 'index.html');
  res.writeHead(200, {'Content-Type': mime[path.extname(filePath)] || 'application/octet-stream'});
  fs.createReadStream(filePath).pipe(res);
}).listen(PORT, () => console.log('serving on ' + PORT));
