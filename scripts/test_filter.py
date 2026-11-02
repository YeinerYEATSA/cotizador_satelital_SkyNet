import urllib.request, urllib.parse, http.cookiejar
BASE='http://127.0.0.1:5000'
jar=http.cookiejar.CookieJar()
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
login_data=urllib.parse.urlencode({'username':'__autotest__','password':'autotest'}).encode()
opener.open(BASE+'/login', login_data)
r=opener.open(BASE+'/?municipio=Leticia')
html=r.read().decode('utf-8')
print('status', r.getcode())
print('contains Leticia?', 'Leticia' in html)
idx=html.find('<ul class="list">')
print(html[idx:idx+400])
