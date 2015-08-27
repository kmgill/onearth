# OnEarth Endpoint Configuration

These steps demonstrate how to create a new endpoint on the file system.  Repeat each section for multiple endpoints.

## WMTS

1) Create the endpoint directory and copy files

```Shell
mkdir -p /usr/share/onearth/demo/wmts-geo

cp -p /usr/share/onearth/apache/wmts.cgi /usr/share/onearth/demo/wmts-geo
cp -p /usr/share/onearth/apache/black.jpg /usr/share/onearth/demo/wmts-geo
cp -p /usr/share/onearth/apache/transparent.png /usr/share/onearth/demo/wmts-geo
cp -p /usr/share/onearth/apache/index.html /usr/share/onearth/demo/wmts-geo
```
2) Check permissions

## Tiled-WMS

1) Create the endpoint directory and copy files

```Shell
mkdir -p /usr/share/onearth/demo/twms-geo
cp -r /usr/share/onearth/apache/ /usr/share/onearth/demo/twms-geo
```

2) Check permissions

## KML

To create the KML endpoint, you'll need to compile the KML CGI script and specify the location of the KML endpoint.

This step requires cgicc to be installed: [http://www.gnu.org/software/cgicc]( http://www.gnu.org/software/cgicc/ ).

1) Compile the script. The WEB_HOST option must be set to the location of the KML endpoint. Default is 'localhost/twms'.

```
cd /usr/share/onearth/demo/twms-geo/kml/
make WEB_HOST=<host>:<port>/kml_endpoint
```

2) Copy the binary CGI script to the endpoint directory.

`mv kmlgen.cgi ../` 
