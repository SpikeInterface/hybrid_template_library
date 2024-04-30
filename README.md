# hybrid_template_library
Library of templates to create hybrid data for spike sorting benchmarks

[click here for access to the library](https://spikeinterface.github.io/hybrid_template_library/)


## Testing locally

How to run a python server for testing zarr access


The following code makes use of the local python server to serve the zarr files. This is useful for testing the zarr files in the browser.  You can run this code in the folder where your zarr files are to start the server and make the zarr files accessible in the browser.

```python
from http.server import HTTPServer, SimpleHTTPRequestHandler
import sys

class CORSHTTPRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def log_message(self, format, *args):
        sys.stderr.write("%s - - [%s] %s\n" %
                         (self.client_address[0],
                          self.log_date_time_string(),
                          format % args))

httpd = HTTPServer(('localhost', 8000), CORSHTTPRequestHandler)
httpd.serve_forever()

```

Execute a script with this code in bash directly or save it to a file and run it with python. 

```bash
python -c "from http.server import HTTPServer, SimpleHTTPRequestHandler; import sys; class CORSHTTPRequestHandler(SimpleHTTPRequestHandler): def end_headers(self): self.send_header('Access-Control-Allow-Origin', '*'); super().end_headers(); def log_message(self, format, *args): sys.stderr.write('%s - - [%s] %s\n' % (self.client_address[0], self.log_date_time_string(), format % args)); httpd = HTTPServer(('localhost', 8000), CORSHTTPRequestHandler); httpd.serve_forever()"
```


Then you run the npm script to start the server and open the browser

```bash
export TEST_URL="http://localhost:8000/zarr_store.zarr"
npm run start
```





