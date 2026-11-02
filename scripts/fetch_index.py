import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# use urllib + cookiejar to avoid external deps
import urllib.request, urllib.parse, http.cookiejar

BASE = 'http://127.0.0.1:5000'

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

# login
login_data = urllib.parse.urlencode({'username': '__autotest__', 'password': 'autotest'}).encode()
resp = opener.open(BASE + '/login', login_data)
print('login status', resp.getcode())

# fetch index
r = opener.open(BASE + '/')
print('index status', r.getcode())
html = r.read().decode('utf-8')
# show snippet around select
start = html.find('<select')
end = html.find('</select>', start)
print(html[start:end+9])
# count options
print('options_count=', html.count('<option'))
