# SpikeInterface Hybrid Template Library


This repo contains a set of tools to construct and interact with a library of hybrid templates for spike sorting benchmarks.

The library is made of several datasets stored a zarr file and can be accessed through the spikeinterface library. 
The library is also accessible through a web-app that allows users to browse the templates and download them for 
use in their spike sorting benchmarks.


## Template sources

The following datasets are available in the library:

- [IBL](https://dandiarchive.org/dandiset/000409?search=IBL&pos=3): Neuropixels 1.0 templates from the IBL Brain Wide Map dataset
- [Steinmetz and Ye. 2022](https://doi.org/10.6084/m9.figshare.19493588.v2): Neuropixels Ultra templates from Steinmetz and Ye. 2022

The templates have been processed and stored with the `python` scripts in the `python/scripts` folder and are stored in `zarr`
format in the `s3://spikeinterface-template-library` bucket hosted on `AWS S3` by [CatalystNeuro](https://www.catalystneuro.com/).


## Accessing the data through `SpikeInterface`

The library can be accessed through the `spikeinterface` library using the `generation` module.
The following code shows how to access the library to fetch a dataframe with the available templates
and download the templates corresponing to a specific user query:

```python
import spikeinterface.generation as sgen

templates_info = sgen.fetch_templates_database_info()

# select templates with amplitude between 200 and 250uV
templates_info_selected = templates_info.query('amplitude_uv > 200 and amplitude_uv < 250')
templates_selected = sgen.sgen.query_templates_from_database(templates_info_selected)
```

For a more comprehensive example on how to construct hybrid recordings from the template library and run spike sorting
benchmarks, please refer to the SpikeInterface tutorial on [Hybrid recordings](https://spikeinterface.readthedocs.io/en/latest/how_to/benchmark_with_hybrid_recordings.html).

## Live Web-App

The template library can be browsed through a web-app (source code included in this repo). The web-app is hosted on github pages and can be accessed through the following link: [https://spikeinterface.github.io/hybrid_template_library/](https://spikeinterface.github.io/hybrid_template_library/)


### Testing locally

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


Then you run the `npm` script to start the server and open the browser

```bash
export TEST_URL="http://localhost:8000/test_zarr.zarr"
npm run start
```





