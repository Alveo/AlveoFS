import requests
import json

api_key = "fxss5G7NxD472koixm7r"
# url = "http://alveo.local:3000/catalog/2nd_coll/kid_1/document/"
url = "http://alveo.local:3000/catalog/2nd_coll/kid_1/document/"

s = requests.Session()
s.headers.update({'X-API-Key': api_key, 'Accept': 'application/json'})

response = json.loads((s.get(url)).text)
# status = curl.getinfo(pycurl.HTTP_CODE)
# string = json.loads(response)
# print json.dumps(json.loads(response)['directories'], indent=2, sort_keys=True)

directory_arr = []

if 'collections' in response:
    directory_arr = response['collections']

if 'items' in response:
    directory_arr = response['items']

if 'documents' in response:
    directory_arr = response['documents']

if 'document_directory' in response:
    directory_arr = response['document_directory']

for d in directory_arr:
    name = d.split('/')[-1]
    print name

if 'files' in response:
    file_arr = response['files']
    for f in file_arr:
        name = f.split('/')[-1]
        print name

# print "-------------"
# buf.truncate(0)
#
# url = "http://alveo.local:3000/catalog/2nd_coll/kid_1/document"
# curl = pycurl.Curl()
# curl.setopt(curl.URL, url)
# curl.setopt(pycurl.HTTPHEADER, ['X-API-KEY: ' + api_key, 'Accept: application/json'])
# curl.setopt(curl.WRITEFUNCTION, buf.write)
# curl.perform()
# response = buf.getvalue()
# status = curl.getinfo(pycurl.HTTP_CODE)
# string = json.loads(response)
# print json.dumps(string['files'], indent=2, sort_keys=True)
